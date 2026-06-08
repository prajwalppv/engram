"""Automatic maintenance — prune + tune actually RUN at SessionEnd (not just as
manual tools). Safe: archived/recoverable, bounded, lifelines preserved."""
from __future__ import annotations

import datetime

from engram.config import Settings
from engram.core import maintenance, memory


def _settings(**kw):
    base = dict(prune_min_age_days=0, prune_min_cluster=2, prune_max_fraction=1.0)
    base.update(kw)
    return Settings(**base)


def test_is_due_gating(store):
    assert maintenance.is_due(store, 24) is True          # never run → due
    maintenance.run_maintenance(store, _settings(auto_prune=False))
    assert maintenance.is_due(store, 24) is False         # just ran → not due
    future = datetime.datetime.now() + datetime.timedelta(hours=25)
    assert maintenance.is_due(store, 24, now=future) is True
    assert maintenance.is_due(store, 0) is True           # interval 0 → always due


def test_disabled_returns_none(store):
    assert maintenance.maybe_maintain(store, _settings(auto_maintain=False)) is None


def test_maintenance_prunes_and_preserves_lifelines(store, generic, text_backend):
    # a lifeline + a stale ephemeral cluster eligible for consolidation
    memory.save(store, generic, type_="Preference", title="Always uv",
                body="standing rule", horizon="preference")
    memory.save(store, generic, type_="Decision", title="Use Postgres", body="db choice")
    for i in range(3):
        memory.save(store, generic, type_="SessionSummary", title=f"S{i}",
                    body=f"chatter {i}", repo="svc")
    before = sum(1 for _ in store.iter_entries())

    rep = maintenance.maybe_maintain(store, _settings(maintain_interval_hours=0),
                                     text_backend)
    assert rep is not None and "prune" in rep
    # lifeline + durable decision survive; ephemeral cluster consolidated (archived)
    assert memory.read(store, "Always uv") is not None
    assert memory.read(store, "Use Postgres") is not None
    after = sum(1 for _ in store.iter_entries())
    assert after < before  # the stale session notes were folded away


def test_interval_gate_skips_second_run(store, generic, text_backend):
    s = _settings(maintain_interval_hours=24)
    assert maintenance.maybe_maintain(store, s, text_backend) is not None
    assert maintenance.maybe_maintain(store, s, text_backend) is None  # within interval
