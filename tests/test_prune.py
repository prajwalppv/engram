from __future__ import annotations

import datetime

from engram.config import Settings
from engram.core import memory, prune, vigor
from engram.core.store import Store


def _old_session(store, swe, title, body, repo, days_ago):
    """Save a SessionSummary then backdate its `created` to simulate age."""
    res = memory.save(store, swe, type_="SessionSummary", title=title, body=body, repo=repo)
    p = store.resolve(res.rel_path)
    old = (datetime.date.today() - datetime.timedelta(days=days_ago)).isoformat()
    txt = store.read(p).replace(f"created: '{datetime.date.today().isoformat()}'", f"created: '{old}'")
    p.write_text(txt, encoding="utf-8")
    return res


def test_vigor_durable_beats_ephemeral(store, swe):
    memory.save(store, swe, type_="Decision", title="Keep Me", body="durable decision")
    memory.save(store, swe, type_="SessionSummary", title="Throwaway", body="chatter")
    scored = vigor.score_all(store)
    by_title = {d["entry"].title: d["vigor"] for d in scored.values()}
    assert by_title["Keep Me"] > by_title["Throwaway"]


def test_prune_dry_run_plans_but_does_not_change(store, swe):
    for i in range(3):
        _old_session(store, swe, f"S{i}", "stale chatter", "alpha", days_ago=40)
    settings = Settings(prune_min_age_days=14, prune_min_cluster=2, prune_max_fraction=1.0)
    before = sum(1 for _ in store.iter_entries())
    rep = prune.prune(store, settings, dry_run=True)
    assert rep["dry_run"] and rep["candidate_count"] == 3
    assert sum(1 for _ in store.iter_entries()) == before  # unchanged


def test_prune_consolidates_and_archives(store, swe):
    for i in range(3):
        _old_session(store, swe, f"Sess {i}", f"did thing {i}", "alpha", days_ago=40)
    memory.save(store, swe, type_="Decision", title="Important", body="keep me")  # durable, fresh
    settings = Settings(prune_min_age_days=14, prune_min_cluster=2, prune_max_fraction=1.0)

    rep = prune.prune(store, settings, dry_run=False)
    assert rep["applied"] and rep["archived"] == 3
    titles = {memory._read_entry(store, p).title for p in store.iter_entries()}
    assert "Consolidated Sessions — alpha" in titles   # ramification: folded into a digest
    assert "Important" in titles                        # durable kept
    assert not any(t.startswith("Sess ") for t in titles)  # originals removed from live set
    # archived (recoverable), not deleted
    assert list((store.root / ".archive").rglob("Sess 0.md"))


def test_restore_and_effectiveness(store, swe):
    for i in range(2):
        _old_session(store, swe, f"R{i}", "stale", "beta", days_ago=40)
    settings = Settings(prune_min_age_days=14, prune_min_cluster=2, prune_max_fraction=1.0)
    prune.prune(store, settings, dry_run=False)

    out = prune.restore(store, "R0")
    assert out["restored"] and memory.read(store, "R0")  # back in the live set

    eff = prune.effectiveness(store)
    assert eff["cycles"] == 1 and eff["resurrections"] == 1
    assert eff["resurrection_rate"] > 0  # the mistake is measured


def test_durable_types_never_auto_pruned(store, swe):
    # an old, unused, unreferenced Decision must NOT be pruned (jin/shari: keep trunk)
    res = memory.save(store, swe, type_="Decision", title="Old Decision", body="why we chose X")
    p = store.resolve(res.rel_path)
    old = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    p.write_text(store.read(p).replace(f"created: '{datetime.date.today().isoformat()}'",
                                       f"created: '{old}'"), encoding="utf-8")
    settings = Settings(prune_min_age_days=14, prune_min_cluster=1, prune_max_fraction=1.0)
    rep = prune.prune(store, settings, dry_run=True)
    assert rep["candidate_count"] == 0
