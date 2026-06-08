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


# ---------------------------------------------------------------- usefulness math
def test_usefulness_ratio():
    assert vigor.usefulness(used=0, read=0, recall=0) == 0.0          # no data
    assert vigor.usefulness(used=0, read=0, recall=10) < 0.1          # pure noise
    assert vigor.usefulness(used=3, read=0, recall=3) > 0.6           # demonstrated
    assert vigor.usefulness(used=0, read=4, recall=4) > vigor.usefulness(0, 0, 4)
    assert vigor.usefulness(used=99, read=0, recall=1) == 1.0         # clamped to 1


# ---------------------------------------------------------------- vigor decays noise
def test_vigor_rewards_use_and_decays_noise(store, generic):
    today = datetime.date.today()
    e = memory.read(store, memory.save(store, generic, type_="SessionSummary",
                                       title="S", body="x", repo="r").rel_path)
    used_v = vigor.score(e, used=3, recall=3, read=0, indeg=0, today=today)
    noise_v = vigor.score(e, used=0, recall=10, read=0, indeg=0, today=today)
    neutral_v = vigor.score(e, used=0, recall=0, read=0, indeg=0, today=today)
    # acted-on beats untouched beats recalled-but-never-used noise
    assert used_v > neutral_v > noise_v


# ---------------------------------------------------------------- ranking reweight
def test_recall_prefers_used_over_recalled_but_unused(store, generic, text_backend):
    for t in ("Cache choice A", "Cache choice B"):
        memory.save(store, generic, type_="Decision", title=t,
                    body="use redis for the session cache layer",
                    search_backend=text_backend)
    a = memory.read(store, "Cache choice A").id
    b = memory.read(store, "Cache choice B").id
    # both surfaced; only A acted on
    feedback.record_recall(store, "redis cache", [a, b])
    feedback.record_signal(store, "used", [a])
    feedback.record_read(store, [a])

    order = [h.id for h in ranking.hybrid_recall(store, text_backend,
                                                 "redis session cache", limit=5)]
    assert a in order and b in order
    assert order.index(a) < order.index(b), order


def test_recall_unaffected_without_feedback(store, generic, text_backend):
    # No feedback log → no usage boost → behaves exactly as before (regression guard).
    memory.save(store, generic, type_="Decision", title="Solo",
                body="postgres multi-row transactions", search_backend=text_backend)
    hits = ranking.hybrid_recall(store, text_backend, "postgres transactions", limit=5)
    assert any(h.title == "Solo" for h in hits)
