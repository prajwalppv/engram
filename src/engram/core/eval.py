"""Scorers — deterministic where possible.

recall: ranking quality (MRR / recall@k) against harvested {query→used id} cases.
extraction: coverage of expected key terms by a prompt's extracted memory, via an
INJECTABLE extract_fn so the optimizer is testable without live LLM calls.
"""
from __future__ import annotations

from typing import Callable

from .search_backends import SearchBackend
from .store import Store

# extract_fn(prompt, transcript, repo) -> list[ {title, body, type, ...} ]
ExtractFn = Callable[[str, str, "str | None"], list[dict]]


def score_recall(store: Store, search_backend: SearchBackend,
                 cases: list[dict], *, k: int = 5) -> dict:
    if not cases:
        return {"n": 0, "mrr": 0.0, "recall_at_k": 0.0, "k": k}
    from . import ranking
    rr_sum = 0.0
    hit = 0
    for c in cases:
        hits = ranking.hybrid_recall(store, search_backend, c["query"], limit=k)
        rank = next((i + 1 for i, h in enumerate(hits) if h.id == c["expected_id"]), 0)
        if rank:
            rr_sum += 1.0 / rank
            hit += 1
    n = len(cases)
    return {"n": n, "mrr": round(rr_sum / n, 3), "recall_at_k": round(hit / n, 3), "k": k}


def score_recall_compactness(store: Store, search_backend: SearchBackend,
                             cases: list[dict], *, max_snippet: int, k: int = 8) -> dict:
    """Token-frugality of the compact index: every hit should carry a bounded,
    non-empty snippet (so the agent can judge it WITHOUT a full read) and never the
    full body. Returns snippet coverage, bounded-rate, and the longest snippet seen."""
    from . import memory
    total = with_snip = bounded = with_created = 0
    longest = 0
    for c in cases:
        for h in memory.recall(store, search_backend, c["query"], limit=k):
            total += 1
            sn = h.snippet or ""
            with_snip += int(bool(sn))
            with_created += int(bool(h.created))
            bounded += int(len(sn) <= max_snippet)
            longest = max(longest, len(sn))
            # a compact hit must NOT carry a full body field
            assert not getattr(h, "body", None), "recall hit leaked a full body"
    return {"n": total,
            "snippet_coverage": round(with_snip / total, 3) if total else 1.0,
            "created_coverage": round(with_created / total, 3) if total else 1.0,
            "bounded_rate": round(bounded / total, 3) if total else 1.0,
            "longest_snippet": longest}


def score_temporal_currency(store: Store, search_backend: SearchBackend,
                            cases: list[dict], *, k: int = 8) -> dict:
    """Temporal correctness: given a fact that SUPERSEDES an older one, recall must
    surface the current fact and drop the retired one. Each case:
    {query, current_id, stale_id}."""
    from . import memory
    if not cases:
        return {"n": 0, "currency": 1.0}
    ok = 0
    for c in cases:
        ids = [h.id for h in memory.recall(store, search_backend, c["query"], limit=k)]
        ok += int(c["current_id"] in ids and c["stale_id"] not in ids)
    return {"n": len(cases), "currency": round(ok / len(cases), 3)}


def _query_from(entry) -> str:
    """A query proxy derived from a note's BODY (not its title), so self-retrieval
    tests the embedding/index rather than a trivial title match."""
    for ln in (entry.body or "").splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", "_", "**")):
            return s[:160]
    return entry.title


def self_retrieval(store: Store, search_backend: SearchBackend, *,
                   k: int = 5, sample: int = 200) -> dict:
    """Automatic, label-free recall health: query each note with a phrase from its
    own body and check it comes back in the top-k. A healthy index scores ~1.0;
    a drop flags drift, a broken index, or an embedding regression."""
    from . import memory, ranking
    ents = [memory._read_entry(store, p) for p in store.iter_entries()][:sample]
    if not ents:
        return {"n": 0, "recall_at_k": 0.0, "mrr": 0.0, "k": k}
    rr_sum = 0.0
    hit = 0
    for e in ents:
        hits = ranking.hybrid_recall(store, search_backend, _query_from(e), limit=k)
        rank = next((i + 1 for i, h in enumerate(hits) if h.rel_path == e.rel_path), 0)
        if rank:
            rr_sum += 1.0 / rank
            hit += 1
    n = len(ents)
    return {"n": n, "recall_at_k": round(hit / n, 3), "mrr": round(rr_sum / n, 3), "k": k}


def run(store: Store, search_backend: SearchBackend, *, k: int = 5) -> dict:
    """The recall scorecard: labeled recall@k/MRR (your feedback + golden cases)
    plus the automatic self-retrieval health metric. One number to optimize."""
    from . import evalset
    labeled = evalset.load_all_recall_cases(store)
    return {
        "labeled_recall": score_recall(store, search_backend, labeled, k=k),
        "self_retrieval": self_retrieval(store, search_backend, k=k),
    }


def score_guardrail(store: Store, cases: list[dict], *, min_score: float = 1.0) -> dict:
    """Proactive-guardrail quality. Each case: {tool_name, tool_input, repo?,
    expected: <memory title> | None}. Reports precision (of fires, how many right),
    recall (of should-fires, how many caught), and silence_rate (benign actions left
    alone) — the anti-noise number."""
    from . import proactive
    if not cases:
        return {"n": 0, "precision": 1.0, "recall": 1.0, "silence_rate": 1.0}
    fires = correct = should = silent_total = silent_ok = 0
    for c in cases:
        adv = proactive.guardrail(store, tool_name=c["tool_name"], tool_input=c["tool_input"],
                                  repo=c.get("repo"), session="eval", min_score=min_score)
        exp = c.get("expected")
        if exp:
            should += 1
            if adv:
                fires += 1
                correct += int(adv["title"] == exp)
        else:
            silent_total += 1
            if adv:
                fires += 1
            else:
                silent_ok += 1
    return {
        "n": len(cases),
        "precision": round(correct / fires, 3) if fires else 1.0,
        "recall": round(correct / should, 3) if should else 1.0,
        "silence_rate": round(silent_ok / silent_total, 3) if silent_total else 1.0,
        "fires": fires, "correct": correct, "should_fire": should,
    }


def score_preference_detection(cases: list[dict]) -> dict:
    """Auto-preference detection quality. Each case: {text, is_preference: bool}.
    Precision matters most — a false positive pollutes every session's always-on layer."""
    from . import preferences
    if not cases:
        return {"n": 0, "precision": 1.0, "recall": 1.0}
    tp = fp = fn = tn = 0
    for c in cases:
        detected = bool(preferences.detect("user: " + c["text"]))
        label = bool(c["is_preference"])
        tp += int(label and detected)
        fn += int(label and not detected)
        fp += int(not label and detected)
        tn += int(not label and not detected)
    return {
        "n": len(cases),
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else 1.0,
        "recall": round(tp / (tp + fn), 3) if (tp + fn) else 1.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def score_role_inference(cases: list[dict]) -> dict:
    """Role-inference accuracy. Each case: {text, expected_role}. Uses the signal
    distribution (argmax), so it grades the role ontologies' signal terms statelessly."""
    from . import roles as role_engine
    if not cases:
        return {"n": 0, "accuracy": 1.0}
    correct = 0
    for c in cases:
        sig = role_engine.infer_signals(c["text"])
        pred = max(sig, key=sig.get) if sig else "generic"
        correct += int(pred == c["expected_role"])
    return {"n": len(cases), "accuracy": round(correct / len(cases), 3), "correct": correct}


def prune_safety(store: Store, settings) -> dict:
    """Pruning must never plan a LIFELINE (preference) or durable type for removal —
    only ephemeral session notes get consolidated. Returns any violations."""
    from . import memory, prune
    planned: set[str] = set()
    for grp in prune.analyze(store, settings).get("plan", []):
        planned.update(grp.get("titles", []))
    protected = {"Decision", "Gotcha", "Constraint", "Convention", "Requirement", "Preference"}
    violations = []
    for p in store.iter_entries():
        ent = memory._read_entry(store, p)
        if (ent.horizon == "preference" or ent.type in protected) and ent.title in planned:
            violations.append(ent.title)
    return {"planned": len(planned), "lifeline_violations": violations, "safe": not violations}


def _coverage(items: list[dict], expected_terms: list[str]) -> float:
    if not expected_terms:
        return 1.0
    hay = " ".join((it.get("title", "") + " " + it.get("body", "")) for it in items).lower()
    found = sum(1 for t in expected_terms if t.lower() in hay)
    return found / len(expected_terms)


def score_extraction(prompt: str, cases: list[dict], extract_fn: ExtractFn) -> float:
    """Mean expected-term coverage of the memory a prompt extracts. 0..1."""
    if not cases:
        return 0.0
    total = 0.0
    for c in cases:
        items = extract_fn(prompt, c["transcript"], c.get("repo"))
        total += _coverage(items, c.get("expected_terms", []))
    return round(total / len(cases), 3)


def extraction_failures(prompt: str, cases: list[dict], extract_fn: ExtractFn,
                        *, threshold: float = 0.8) -> list[dict]:
    """Cases the current prompt covers poorly — fuel for the optimizer."""
    out = []
    for c in cases:
        items = extract_fn(prompt, c["transcript"], c.get("repo"))
        cov = _coverage(items, c.get("expected_terms", []))
        if cov < threshold:
            out.append({"transcript": c["transcript"][:1500],
                        "expected_terms": c.get("expected_terms", []),
                        "coverage": round(cov, 3)})
    return out
