"""The feedback loop (lever 1): recall → used/read → reweight ranking + decay
noise in vigor. All deterministic on the text backend / stateless math."""
from __future__ import annotations

import datetime

from engram.core import feedback, memory, ranking, vigor


# ---------------------------------------------------------------- signal capture
def test_record_read_and_counts(store, generic):
    r = memory.save(store, generic, type_="Note", title="N", body="body text")
    mid = memory.read(store, r.rel_path).id
    feedback.record_recall(store, "q", [mid])
    feedback.record_read(store, [mid])
    feedback.record_signal(store, "used", [mid])
    c = vigor.feedback_counts(store)[mid]
    assert c == {"recall": 1, "used": 1, "read": 1}


def test_record_read_ignores_empty():
    # never raise / never log junk
    from engram.core.store import FileSystemBackend, Store
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    s = Store(FileSystemBackend(d))
    feedback.record_read(s, [])
    feedback.record_read(s, [None, ""])
    assert vigor.feedback_counts(s) == {}


# ---------------------------------------------------------------- access model (mem0)
def test_access_decay_and_boost():
    now = datetime.datetime.now()
    fresh = {"count": 5, "used": 0, "read": 0, "last": now.isoformat()}
    old = {"count": 5, "used": 0, "read": 0,
           "last": (now - datetime.timedelta(days=28)).isoformat()}  # 2 half-lives
    # recall IS the access signal; recency decays it (Ebbinghaus)
    assert vigor.decayed_access(fresh, now) > vigor.decayed_access(old, now)
    assert abs(vigor.decayed_access(old, now) - 5 * 0.25) < 0.3       # ~2 half-lives → ×0.25
    assert vigor.decayed_access(None, now) == 0.0                      # no data
    assert vigor.decayed_access({"count": 0, "used": 0, "read": 0, "last": None}, now) == 0.0
    # explicit use weighs MORE than a bare recall
    assert (vigor.decayed_access({"count": 1, "used": 1, "read": 0, "last": now.isoformat()}, now)
            > vigor.decayed_access({"count": 1, "used": 0, "read": 0, "last": now.isoformat()}, now))
    # boost saturates in [0, 1) — rich-get-richer guard
    assert 0 < vigor.recall_boost(fresh, now) < 1
    assert vigor.recall_boost(None, now) == 0.0


def test_vigor_rewards_access(store, generic):
    today = datetime.date.today()
    e = memory.read(store, memory.save(store, generic, type_="SessionSummary",
                                       title="S", body="x", repo="r").rel_path)
    # an actively-recalled memory scores higher than one nobody recalls
    assert vigor.score(e, access=8.0, indeg=0, today=today) > \
           vigor.score(e, access=0.0, indeg=0, today=today)


# ---------------------------------------------------------------- ranking reweight
def test_recall_access_alone_reweights(store, generic, text_backend):
    # THE fix: with NO explicit used/read — just more recall ACCESS — the more-
    # accessed memory ranks higher. This is the signal that actually fires.
    for t in ("Cache A", "Cache B"):
        memory.save(store, generic, type_="Decision", title=t,
                    body="use redis for the session cache layer", search_backend=text_backend)
    a = memory.read(store, "Cache A").id
    b = memory.read(store, "Cache B").id
    for _ in range(3):
        feedback.record_recall(store, "redis", [a])   # A accessed 3×
    feedback.record_recall(store, "redis", [b])        # B accessed 1×
    order = [h.id for h in ranking.hybrid_recall(store, text_backend,
                                                 "redis session cache", limit=5)]
    assert order.index(a) < order.index(b), order


def test_recall_prefers_explicit_use(store, generic, text_backend):
    for t in ("Cache choice A", "Cache choice B"):
        memory.save(store, generic, type_="Decision", title=t,
                    body="use redis for the session cache layer", search_backend=text_backend)
    a = memory.read(store, "Cache choice A").id
    b = memory.read(store, "Cache choice B").id
    feedback.record_recall(store, "redis cache", [a, b])
    feedback.record_signal(store, "used", [a])   # explicit use is a stronger access
    feedback.record_read(store, [a])
    order = [h.id for h in ranking.hybrid_recall(store, text_backend,
                                                 "redis session cache", limit=5)]
    assert order.index(a) < order.index(b), order


def test_recall_unaffected_without_feedback(store, generic, text_backend):
    # No feedback log → no usage boost → behaves exactly as before (regression guard).
    memory.save(store, generic, type_="Decision", title="Solo",
                body="postgres multi-row transactions", search_backend=text_backend)
    hits = ranking.hybrid_recall(store, text_backend, "postgres transactions", limit=5)
    assert any(h.title == "Solo" for h in hits)
