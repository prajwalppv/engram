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
    rr_sum = 0.0
    hit = 0
    for c in cases:
        hits = search_backend.query(c["query"], limit=k)
        rank = next((i + 1 for i, h in enumerate(hits) if h.id == c["expected_id"]), 0)
        if rank:
            rr_sum += 1.0 / rank
            hit += 1
    n = len(cases)
    return {"n": n, "mrr": round(rr_sum / n, 3), "recall_at_k": round(hit / n, 3), "k": k}


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
