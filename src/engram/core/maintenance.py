"""Automatic maintenance — make the self-maintenance machinery actually RUN.

engram has bonsai pruning, a deterministic prune-param tuner, and recall-case
harvesting, but historically nothing drove them: they were manual tools. The
README promises a system that "keeps itself sharp" and "self-improves over time" —
this is what makes that literally true.

Run at SessionEnd (the async capture hook, off the critical path), gated to at most
once per ``maintain_interval_hours`` via a timestamp so it's cheap and idempotent.
Everything it does is SAFE: pruning archives (never deletes), is bounded by the
⅓-rule, and guards lifelines (preferences/durable types); the tuner is deterministic.
The LLM-cost extraction-prompt search is deliberately NOT here — it stays a gated,
explicit tool.
"""
from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings
    from .search_backends import SearchBackend
    from .store import Store

_STATE_REL = ".state/maintenance.json"


def _state_path(store: "Store"):
    return store.root / _STATE_REL


def _last_run(store: "Store") -> datetime.datetime | None:
    p = _state_path(store)
    if not p.exists():
        return None
    try:
        return datetime.datetime.fromisoformat(
            json.loads(p.read_text(encoding="utf-8")).get("last_run", ""))
    except Exception:
        return None


def is_due(store: "Store", interval_hours: float, *, now: datetime.datetime | None = None) -> bool:
    now = now or datetime.datetime.now()
    last = _last_run(store)
    if last is None:
        return True
    return (now - last).total_seconds() >= interval_hours * 3600


def _mark_run(store: "Store", report: dict, now: datetime.datetime) -> None:
    p = _state_path(store)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_run": now.isoformat(timespec="seconds"),
                             "last_report": report}, indent=2), encoding="utf-8")


def run_maintenance(store: "Store", settings: "Settings",
                    search_backend: "SearchBackend | None" = None, *,
                    now: datetime.datetime | None = None) -> dict:
    """Run the safe, deterministic maintenance steps once. Best-effort; never raises.

    Order matters: prune first (generates resurrection data), then tune the prune
    fraction from that data — so the controller actually has a signal to learn from.
    """
    now = now or datetime.datetime.now()
    report: dict = {}
    # 1) Bonsai prune — conservative, archived (recoverable), bounded, lifeline-safe.
    if getattr(settings, "auto_prune", True):
        try:
            from . import prune
            report["prune"] = prune.prune(store, settings, search_backend, dry_run=False)
        except Exception as e:
            report["prune_error"] = str(e)
    # 2) Deterministic prune-param self-tuning from the resurrection signal.
    try:
        from . import optimize
        report["tune"] = optimize.tune_prune_params(store, settings)
    except Exception as e:
        report["tune_error"] = str(e)
    _mark_run(store, report, now)
    return report


def maybe_maintain(store: "Store", settings: "Settings",
                   search_backend: "SearchBackend | None" = None, *,
                   now: datetime.datetime | None = None) -> dict | None:
    """Run maintenance iff enabled and due. Returns the report, or None if skipped."""
    if not getattr(settings, "auto_maintain", True):
        return None
    if not is_due(store, getattr(settings, "maintain_interval_hours", 24), now=now):
        return None
    try:
        return run_maintenance(store, settings, search_backend, now=now)
    except Exception:
        return None
