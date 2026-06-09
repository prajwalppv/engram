"""Self-improvement: turn feedback signals into better prompts and prune params.

Two optimizers:
  1. tune_prune_params — DETERMINISTIC controller. Reads the prune resurrection rate
     (archived-then-restored = false positive) and nudges prune aggressiveness toward
     a target. This learns engram's safe removal fraction instead of borrowing
     bonsai's ⅓ by analogy (the deep-research open question).
  2. optimize_extraction_prompt — GATED, VERSIONED prompt search. An (injectable)
     proposer suggests a new extraction prompt from failing eval cases; it is accepted
     ONLY if it beats the current prompt on a held-out split. Prior versions are kept
     for rollback. Proposer + extract_fn are injectable so this is testable offline.
"""
from __future__ import annotations

import datetime
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from . import eval as ev
from . import evalset, prune, summarizer
from . import roles as role_engine

if TYPE_CHECKING:
    from ..config import Settings
    from .proposer import Proposer
    from .store import Store

TUNED_REL = ".state/tuned.json"
PROMPT_REL = ".state/prompts/extraction.md"
HIST_DIR = ".state/prompts/history"


# ---------------------------------------------------------- tuned params I/O
def load_tuned(store: "Store") -> dict:
    p = store.root / TUNED_REL
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_tuned(store: "Store", d: dict) -> None:
    p = store.root / TUNED_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


# ---------------------------------------------------------- 1. prune self-tuner
def tune_prune_params(store: "Store", settings: "Settings", *,
                      target_resurrection: float = 0.05, step: float = 0.05,
                      min_frac: float = 0.05, max_frac: float = 0.5) -> dict:
    eff = prune.effectiveness(store)
    rate, cycles = eff["resurrection_rate"], eff["cycles"]
    tuned = load_tuned(store)
    cur = float(tuned.get("prune_max_fraction", settings.prune_max_fraction))
    if cycles == 0:
        return {"changed": False, "reason": "no prune cycles yet", "prune_max_fraction": cur}
    if rate > target_resurrection:
        new = round(max(min_frac, cur - step), 3)
        reason = f"resurrection_rate {rate} > target {target_resurrection} → prune less"
    elif rate == 0.0 and cycles >= 3:
        new = round(min(max_frac, cur + step), 3)
        reason = f"0 resurrections over {cycles} cycles → prune a little more"
    else:
        new, reason = cur, "within target band"
    tuned["prune_max_fraction"] = new
    _save_tuned(store, tuned)
    return {"changed": new != cur, "old": cur, "new": new, "reason": reason,
            "resurrection_rate": rate, "cycles": cycles}


# ---------------------------------------------------------- prompt versioning
def active_prompt(store: "Store") -> str:
    return summarizer._load_prompt(store)


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%dT%H%M%S")


def save_prompt(store: "Store", text: str, meta: dict) -> None:
    cur = store.root / PROMPT_REL
    histd = store.root / HIST_DIR
    histd.mkdir(parents=True, exist_ok=True)
    if cur.exists():  # archive the prompt we're replacing
        shutil.copy2(cur, histd / f"{_stamp()}.md")
    cur.parent.mkdir(parents=True, exist_ok=True)
    cur.write_text(text, encoding="utf-8")
    with open(histd / "versions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": _stamp(), **meta}, ensure_ascii=False) + "\n")


def rollback_prompt(store: "Store") -> dict:
    histd = store.root / HIST_DIR
    cur = store.root / PROMPT_REL
    versions = sorted(histd.glob("*.md")) if histd.exists() else []
    if not versions:
        if cur.exists():
            cur.unlink()  # revert to the shipped default
            return {"rolled_back": "default"}
        return {"rolled_back": None, "reason": "no history"}
    last = versions[-1]
    shutil.move(str(last), str(cur))
    return {"rolled_back": last.name}


def prompt_history(store: "Store") -> list[dict]:
    p = store.root / HIST_DIR / "versions.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# ---------------------------------------------------------- 2. prompt optimizer
def _default_extract_fn(store: "Store", settings: "Settings") -> ev.ExtractFn:
    role = role_engine.current_role(store, settings.role)

    def fn(prompt: str, transcript: str, repo: str | None) -> list[dict]:
        try:
            return summarizer.extract_with_prompt(
                prompt, transcript, role=role, repo=repo,
                timeout=settings.summarizer_timeout)
        except Exception:
            return []
    return fn


def optimize_extraction_prompt(
    store: "Store", settings: "Settings", *,
    proposer: "Proposer", extract_fn: ev.ExtractFn | None = None,
    min_cases: int = 4, dry_run: bool = False,
) -> dict:
    cases = evalset.load_extraction_cases(store)
    if len(cases) < min_cases:
        return {"changed": False,
                "reason": f"need >= {min_cases} extraction eval cases, have {len(cases)}"}
    extract_fn = extract_fn or _default_extract_fn(store, settings)
    # deterministic interleaved train/holdout split
    train = cases[::2]
    holdout = cases[1::2] or cases[:1]

    current = active_prompt(store)
    base = ev.score_extraction(current, holdout, extract_fn)
    failures = ev.extraction_failures(current, train, extract_fn)
    candidate = proposer.propose(current, failures)

    if not candidate or candidate.strip() == current.strip():
        return {"changed": False, "reason": "no new candidate proposed",
                "base_score": base}
    for ph in ("{transcript}", "{existing_memory}"):  # safety: must keep placeholders
        if ph not in candidate:
            return {"changed": False, "reason": f"candidate dropped {ph} placeholder",
                    "base_score": base}

    cand = ev.score_extraction(candidate, holdout, extract_fn)
    accepted = cand > base  # GATE: must beat baseline on held-out
    result = {"base_score": base, "candidate_score": cand, "accepted": accepted,
              "dry_run": dry_run, "train_failures": len(failures),
              "holdout": len(holdout)}
    if accepted and not dry_run:
        save_prompt(store, candidate, {"base": base, "candidate": cand})
        result["version_saved"] = True
    return result
