"""Phase 5 — per-horizon pruning policies wired into bonsai."""
from __future__ import annotations

import datetime
import json

from engram.config import Settings
from engram.core import memory, preferences, prune, vigor, working
from engram.core.models import MemoryEntry


def test_recency_decays_per_horizon():
    today = datetime.date.today()
    old = (today - datetime.timedelta(days=10)).isoformat()
    w = MemoryEntry(id="w", rel_path="w.md", type="Note", title="w",
                    horizon="working", frontmatter={"created": old})
    s = MemoryEntry(id="s", rel_path="s.md", type="Note", title="s",
                    horizon="semantic", frontmatter={"created": old})
    # same type (same durability) → the only difference is horizon half-life:
    # working scratch has nearly decayed at 10 days; semantic has barely.
    sw = vigor.score(w, used=0, recall=0, indeg=0, today=today)
    ss = vigor.score(s, used=0, recall=0, indeg=0, today=today)
    assert ss > sw
    assert vigor.HORIZON_HALFLIFE["preference"] > vigor.HORIZON_HALFLIFE["episodic"] \
        > vigor.HORIZON_HALFLIFE["working"]


def test_metrics_break_down_by_horizon(store, swe):
    memory.save(store, swe, type_="Decision", title="D", body="x", repo="r")
    preferences.add(store, swe, "Always use uv.")
    m = prune.metrics(store)
    assert m["by_horizon"].get("semantic", 0) >= 1
    assert m["by_horizon"].get("preference", 0) >= 1


def _backdate_working(store, sid, hours):
    p = store.root / ".state" / "working" / f"{sid}.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["updated_ts"] -= hours * 3600
    p.write_text(json.dumps(s), encoding="utf-8")


def test_prune_apply_cleans_stale_working_memory(store, swe):
    working.update(store, "old", [{"role": "user", "text": "x"}], "r")
    working.update(store, "fresh", [{"role": "user", "text": "y"}], "r")
    _backdate_working(store, "old", 100)
    rep = prune.prune(store, Settings(), dry_run=False)  # no note plan → still cleans working
    assert rep["applied"] is True and rep.get("working_pruned", 0) >= 1
    assert working.load(store, "old") is None
    assert working.load(store, "fresh") is not None


def test_prune_dry_run_reports_but_keeps_working(store):
    working.update(store, "old2", [{"role": "user", "text": "x"}], "r")
    _backdate_working(store, "old2", 100)
    rep = prune.prune(store, Settings(), dry_run=True)
    assert rep.get("working_expirable", 0) >= 1
    assert working.load(store, "old2") is not None  # dry-run never deletes
