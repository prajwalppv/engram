"""Per-session high-water mark for incremental, idempotent memory capture.

A single Claude Code session is captured many times over its life — at the end of
each turn (``Stop``), right before context compaction (``PreCompact``), and at
session end (``SessionEnd``). Yet every transcript message must be folded into
memory *exactly once*. This module records, per session, how many transcript
events have already been captured, so each trigger only processes the **delta**.

Combined with content-hash + semantic dedup downstream, overlapping or repeated
triggers (including ``--resume`` re-reading an old transcript) are safe: at worst
the same delta is re-summarized and deduped, never double-stored.

All on-device, under ``<store>/.state/sessions/<session_id>.json``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Store

_DIR_REL = ".state/sessions"


def _safe_id(session_id: str | None) -> str:
    sid = (session_id or "default").strip() or "default"
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in sid)[:128]


def _path(store: "Store", session_id: str | None) -> Path:
    return store.root / _DIR_REL / f"{_safe_id(session_id)}.json"


def load(store: "Store", session_id: str | None) -> dict:
    """Return the marker for a session, or a fresh zeroed one."""
    try:
        return json.loads(_path(store, session_id).read_text(encoding="utf-8"))
    except Exception:
        return {"processed_events": 0, "captures": 0}


def save(store: "Store", session_id: str | None, marker: dict) -> None:
    """Persist the marker atomically (temp file + replace)."""
    p = _path(store, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(marker), encoding="utf-8")
    tmp.replace(p)
