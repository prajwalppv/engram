"""Working memory — the shortest horizon: "where was I right now".

Session-scoped, ephemeral operational state — deliberately NOT a markdown note (we
don't want transient scratch polluting the knowledge graph or the semantic index).
It lives as small per-session JSON under ``<store>/.state/working/<id>.json``,
refreshes on every capture tick, is injected at SessionStart only when you RESUME a
recent session, and expires by TTL (Phase 5 prunes it).
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import Store

_DIR_REL = ".state/working"


def _safe_id(session_id: str | None) -> str:
    sid = (session_id or "default").strip() or "default"
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in sid)[:128]


def _path(store: "Store", session_id: str | None) -> Path:
    return store.root / _DIR_REL / f"{_safe_id(session_id)}.json"


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _truncate(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def summarize(events: list[dict]) -> str:
    """A compact 'current focus' from the latest user intent in the events."""
    users = [e["text"] for e in events if e.get("role") == "user" and e.get("text")]
    return _truncate(users[-1], 240) if users else ""


def update(store: "Store", session_id: str | None, events: list[dict],
           repo: str | None = None) -> dict | None:
    """Refresh the working snapshot for a session (atomic). No-op if there's no
    user intent to record. Cheap: no LLM, no embedding."""
    summary = summarize(events)
    if not summary:
        return None
    now = _now()
    state = {
        "session_id": _safe_id(session_id),
        "repo": repo,
        "summary": summary,
        "turns": sum(1 for e in events if e.get("role") == "user"),
        "updated": now.isoformat(timespec="seconds"),
        "updated_ts": now.timestamp(),
    }
    p = _path(store, session_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(p)
    return state


def load(store: "Store", session_id: str | None) -> dict | None:
    try:
        return json.loads(_path(store, session_id).read_text(encoding="utf-8"))
    except Exception:
        return None


def age_hours(state: dict, *, now: datetime.datetime | None = None) -> float:
    try:
        ts = float(state.get("updated_ts", 0))
    except Exception:
        return 1e9
    return ((now or _now()).timestamp() - ts) / 3600.0


def is_fresh(state: dict | None, ttl_hours: float) -> bool:
    return bool(state) and age_hours(state) <= ttl_hours


def prune_expired(store: "Store", ttl_hours: float) -> int:
    """Delete working snapshots older than the TTL. Returns the count removed."""
    root = store.root / _DIR_REL
    if not root.exists():
        return 0
    removed = 0
    for p in root.glob("*.json"):
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            p.unlink(missing_ok=True)
            removed += 1
            continue
        if age_hours(state) > ttl_hours:
            p.unlink(missing_ok=True)
            removed += 1
    return removed


def count(store: "Store") -> int:
    root = store.root / _DIR_REL
    return sum(1 for _ in root.glob("*.json")) if root.exists() else 0
