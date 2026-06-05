"""Phase 3 — procedural memory (runbooks): detection, durability, supersede."""
from __future__ import annotations

from engram.config import Settings
from engram.core import memory, procedural, prune, vigor

_RUNBOOK = (
    "user: Here's how we deploy the service:\n"
    "1. run the migration\n"
    "2. push to main\n"
    "3. tag the release\n\n"
    "assistant: got it"
)


# ---------------------------------------------------------------- detection
def test_detect_runbook_with_steps():
    procs = procedural.detect(_RUNBOOK)
    assert len(procs) == 1
    assert "deploy the service" in procs[0]["title"].lower()
    assert "migration" in procs[0]["body"] and "tag the release" in procs[0]["body"]


def test_detect_ignores_lists_without_process_leadin():
    text = "user: here are my questions:\n- what is X?\n- what is Y?\n\nassistant: ok"
    assert procedural.detect(text) == []


def test_detect_requires_two_steps():
    text = "user: to deploy:\n1. only one step\n\nassistant: ok"
    assert procedural.detect(text) == []


def test_detect_ignores_assistant_turns():
    text = "user: thanks\n\nassistant: here's how we deploy:\n1. a\n2. b"
    assert procedural.detect(text) == []


# ---------------------------------------------------------------- capture
def test_capture_stores_repo_scoped_procedure_and_dedupes(store, swe, text_backend):
    saved = procedural.capture_from_session(store, swe, _RUNBOOK, repo="svc",
                                            search_backend=text_backend)
    assert len(saved) == 1
    e = memory.read(store, saved[0].rel_path)
    assert e.type == "Procedure" and e.horizon == "procedural"
    assert e.repo == "svc" and e.scope == "repo"
    # auto-capture again must NOT append a duplicate runbook
    assert procedural.capture_from_session(store, swe, _RUNBOOK, repo="svc",
                                           search_backend=text_backend) == []


# ---------------------------------------------------------------- supersede-with-history
def test_explicit_update_keeps_history(store, swe):
    memory.save(store, swe, type_="Procedure", title="Runbook: deploy",
                body="1. step a", horizon="procedural")
    memory.save(store, swe, type_="Procedure", title="Runbook: deploy",
                body="1. step b", horizon="procedural")
    e = memory.read(store, "Runbook: deploy")
    assert "step a" in e.body and "step b" in e.body  # prior version preserved


# ---------------------------------------------------------------- durability
def test_procedures_are_durable_and_never_pruned(store, swe):
    assert vigor.TYPE_DURABILITY["Procedure"] >= 2.0
    r = memory.save(store, swe, type_="Procedure", title="Runbook: x",
                    body="1. a\n2. b", horizon="procedural", repo="r")
    plan = prune.analyze(store, Settings())["plan"]
    targeted = {rp for grp in plan for rp in grp["rel_paths"]}
    assert r.rel_path not in targeted
