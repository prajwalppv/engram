"""Feedback capture — the online signal that tunes role weights (and, later, the
extraction/recall prompts via an eval harness). Append-only, local, private.

Signals: which memories were RECALLED, which were USED (referenced/kept), which
were REJECTED (dismissed/edited). For now we log them and let "used" reinforce
the role that produced the memory; the optimizer that consumes this log is future
work, but the data starts accumulating from day one.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from . import roles as role_engine
from .store import Store

_LOG_REL = ".state/feedback.jsonl"


def _log_path(store: Store) -> Path:
    return store.root / _LOG_REL


def record(store: Store, event: dict) -> None:
    p = _log_path(store)
    p.parent.mkdir(parents=True, exist_ok=True)
    event = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), **event}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def record_recall(store: Store, query: str, ids: list[str]) -> None:
    record(store, {"kind": "recall", "query": query, "ids": ids})


def record_signal(store: Store, signal: str, ids: list[str],
                  roles_used: list[str] | None = None) -> None:
    """signal in {'used','rejected'}. 'used' reinforces the producing role(s)."""
    record(store, {"kind": signal, "ids": ids, "roles": roles_used or []})
    if signal == "used":
        for r in (roles_used or []):
            role_engine.reinforce(store, r, amount=0.05)


def aggregate(store: Store) -> dict:
    """Coarse counts for introspection/eval bootstrapping."""
    p = _log_path(store)
    counts: dict[str, int] = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                counts[json.loads(line).get("kind", "?")] = counts.get(
                    json.loads(line).get("kind", "?"), 0) + 1
            except Exception:
                continue
    return counts
