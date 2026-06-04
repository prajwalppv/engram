from __future__ import annotations

import json
from pathlib import Path

from engram.config import Settings
from engram.core import capture, checkpoint


def _append(path: Path, role: str, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"message": {"role": role, "content": text}}) + "\n")


def _settings() -> Settings:
    return Settings(summarizer="heuristic", role="auto")


def test_delta_advances_high_water_mark(store, tmp_path):
    t = tmp_path / "transcript.jsonl"
    _append(t, "user", "add retry logic to the http client")
    _append(t, "assistant", "added exponential backoff and a unit test")

    r1 = capture.capture_delta(store, _settings(), transcript_path=str(t),
                               repo="svc", session_id="s1", force=True)
    assert r1, "first flush should capture the delta"
    assert checkpoint.load(store, "s1")["processed_events"] == 2

    # No new events → nothing to do (idempotent re-run).
    r2 = capture.capture_delta(store, _settings(), transcript_path=str(t),
                               repo="svc", session_id="s1", force=True)
    assert r2 == []
    assert checkpoint.load(store, "s1")["processed_events"] == 2

    # New turns → only the delta is captured, mark advances.
    _append(t, "user", "now cache responses for 60 seconds")
    _append(t, "assistant", "added an LRU cache with a TTL")
    r3 = capture.capture_delta(store, _settings(), transcript_path=str(t),
                               repo="svc", session_id="s1", force=True)
    assert r3, "second flush should capture the new delta"
    assert checkpoint.load(store, "s1")["processed_events"] == 4
    assert checkpoint.load(store, "s1")["captures"] == 2


def test_stop_throttle_holds_then_flushes(store, tmp_path):
    t = tmp_path / "transcript.jsonl"
    _append(t, "user", "first small question")
    _append(t, "assistant", "a short answer")

    # Below the min_turns gate → held, mark NOT advanced.
    held = capture.capture_delta(store, _settings(), transcript_path=str(t),
                                 repo="svc", session_id="s2", force=False, min_turns=3)
    assert held == []
    assert checkpoint.load(store, "s2")["processed_events"] == 0

    # Accumulate up to the gate (3 user turns) → fires on the whole delta.
    _append(t, "user", "second question")
    _append(t, "assistant", "answer two")
    _append(t, "user", "third question")
    _append(t, "assistant", "answer three")
    fired = capture.capture_delta(store, _settings(), transcript_path=str(t),
                                  repo="svc", session_id="s2", force=False, min_turns=3)
    assert fired, "should fire once the turn gate is reached"
    assert checkpoint.load(store, "s2")["processed_events"] == 6


def test_force_flush_below_gate_after_stop_held(store, tmp_path):
    """PreCompact/SessionEnd (force=True) flush a delta the Stop gate held back."""
    t = tmp_path / "transcript.jsonl"
    _append(t, "user", "just one quick thing before I close the terminal")
    _append(t, "assistant", "done")

    held = capture.capture_delta(store, _settings(), transcript_path=str(t),
                                 repo="svc", session_id="s3", force=False, min_turns=3)
    assert held == [] and checkpoint.load(store, "s3")["processed_events"] == 0

    flushed = capture.capture_delta(store, _settings(), transcript_path=str(t),
                                    repo="svc", session_id="s3", force=True)
    assert flushed, "forced flush must not lose the held delta"
    assert checkpoint.load(store, "s3")["processed_events"] == 2
