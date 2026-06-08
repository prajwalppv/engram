"""`<private>` redaction — secrets the user marks must never reach memory."""
from __future__ import annotations

import json

from engram.config import Settings
from engram.core import capture, redact, working


def test_strip_private_closed_case_insensitive_and_passthrough():
    assert redact.strip_private("a <private>secret</private> b") == "a  [redacted]  b"
    # case-insensitive + spans newlines
    out = redact.strip_private("x <PRIVATE>line1\nsecret\nline2</private> y")
    assert "secret" not in out and out.startswith("x ") and out.endswith(" y")
    # multiple spans on one line
    assert "a1" not in redact.strip_private("p <private>a1</private> q <private>a2</private> r")
    # no tag → unchanged; empty → empty
    assert redact.strip_private("nothing here") == "nothing here"
    assert redact.strip_private("") == ""
    assert redact.strip_private(None) == ""


def test_strip_private_unclosed_redacts_to_end():
    # fail-safe: a forgotten close tag must not leak the tail
    out = redact.strip_private("keep this <private>secret tail with no close")
    assert "secret" not in out and out.startswith("keep this")


def test_capture_does_not_persist_private_content(store):
    settings = Settings(summarizer="heuristic", redact_private=True)
    capture.capture_session(
        store, settings,
        transcript_text="user: we chose postgres for transactions. "
                        "db password <private>p@ss-w0rd-77</private> remember the db choice")
    bodies = " ".join(__import__("engram").core.memory._read_entry(store, p).body
                       for p in store.iter_entries())
    assert "p@ss-w0rd-77" not in bodies
    assert bodies.strip(), "nothing captured — test would be vacuous"


def test_working_memory_is_redacted(tmp_path, store):
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"type": "user", "message": {
        "role": "user", "content": "note <private>SEKRET-9</private> end"}}) + "\n",
        encoding="utf-8")
    capture.capture_delta(store, Settings(summarizer="heuristic"),
                          transcript_path=str(t), session_id="s1", force=True)
    snap = working.load(store, "s1")
    assert "SEKRET-9" not in json.dumps(snap)


def test_redaction_can_be_disabled(store):
    # opt-out path still works (some users may not want it)
    settings = Settings(summarizer="heuristic", redact_private=False)
    out = redact.strip_private("a <private>x</private> b")  # the helper still redacts
    assert "x" not in out
    # but with the flag off, capture leaves content untouched
    capture.capture_session(store, settings,
                            transcript_text="user: always keep <private>VISIBLE-1</private> visible")
    bodies = " ".join(__import__("engram").core.memory._read_entry(store, p).body
                      for p in store.iter_entries())
    assert "VISIBLE-1" in bodies
