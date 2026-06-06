"""Eval harness: a runnable recall metric with real data (golden cases) + an
automatic, label-free self-retrieval health score. Uses the text backend so no
model download is needed."""
from __future__ import annotations

from engram.core import eval as ev
from engram.core import evalset, memory


def _seed(store, generic):
    for t, b in [
        ("Use Postgres", "we chose multi-row transactions for the cart flow"),
        ("Stripe webhook idempotency", "dedupe on the event id to avoid a double charge"),
        ("Money in cents", "store currency as integer cents, never floats"),
    ]:
        memory.save(store, generic, type_="Decision", title=t, body=b)


def test_self_retrieval_healthy(store, generic, text_backend):
    _seed(store, generic)
    r = ev.self_retrieval(store, text_backend, k=3)
    assert r["n"] == 3 and r["recall_at_k"] == 1.0 and r["mrr"] > 0


def test_golden_case_resolves_title_to_id(store, generic, text_backend):
    _seed(store, generic)
    n = evalset.add_recall_case(store, "multi-row transactions database", "Use Postgres")
    assert n == 1
    cases = evalset.load_all_recall_cases(store)
    assert len(cases) == 1
    # title was resolved to the stable id
    assert cases[0]["expected_id"] == memory.read(store, "Use Postgres").id


def test_run_scorecard_includes_both_metrics(store, generic, text_backend):
    _seed(store, generic)
    evalset.add_recall_case(store, "multi-row transactions", "Use Postgres")
    out = ev.run(store, text_backend, k=5)
    assert set(out) == {"labeled_recall", "self_retrieval"}
    assert out["labeled_recall"]["n"] == 1
    # the labeled query shares terms with the body → the text backend should rank it
    assert out["labeled_recall"]["recall_at_k"] == 1.0


def test_load_all_dedups(store, generic, text_backend):
    _seed(store, generic)
    evalset.add_recall_case(store, "cents", "Money in cents")
    evalset.add_recall_case(store, "cents", "Money in cents")  # duplicate
    assert len(evalset.load_all_recall_cases(store)) == 1
