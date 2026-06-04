"""Eval datasets — harvested from real feedback (the system labels its own data).

Two kinds:
  * recall cases  {query, expected_id}  — harvested automatically: when a recalled
    memory is later marked USED, that (query → used id) is a labeled positive.
  * extraction cases  {transcript, expected_terms}  — opt-in seed cases (a sample
    transcript + key phrases a good extraction must capture). Used to optimize the
    extraction prompt offline.

All local, under <store>/.state/eval/.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import Store

_RECALL_REL = ".state/eval/recall.jsonl"
_EXTRACT_REL = ".state/eval/extraction.jsonl"
_FEEDBACK_REL = ".state/feedback.jsonl"


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def harvest_recall_cases(store: Store) -> list[dict]:
    """Pair each 'used' memory with the query from the most recent prior 'recall'."""
    events = _read_jsonl(store.root / _FEEDBACK_REL)
    cases: dict[tuple, dict] = {}
    last_recall: dict | None = None
    for ev in events:
        kind = ev.get("kind")
        if kind == "recall":
            last_recall = ev
        elif kind == "used" and last_recall:
            rec_ids = set(last_recall.get("ids", []))
            for mid in ev.get("ids", []):
                if mid in rec_ids:
                    key = (last_recall.get("query", ""), mid)
                    cases[key] = {"query": last_recall.get("query", ""), "expected_id": mid}
    out = list(cases.values())
    # persist harvested set for inspection / reuse
    p = store.root / _RECALL_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in out), encoding="utf-8")
    return out


def load_recall_cases(store: Store) -> list[dict]:
    return _read_jsonl(store.root / _RECALL_REL) or harvest_recall_cases(store)


def load_extraction_cases(store: Store) -> list[dict]:
    return _read_jsonl(store.root / _EXTRACT_REL)


def add_extraction_case(store: Store, transcript: str, expected_terms: list[str],
                        repo: str | None = None) -> int:
    p = store.root / _EXTRACT_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"transcript": transcript, "expected_terms": expected_terms,
                            "repo": repo}, ensure_ascii=False) + "\n")
    return len(load_extraction_cases(store))
