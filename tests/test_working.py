"""Phase 4 — working memory (session scratch, resume-aware, TTL)."""
from __future__ import annotations

import datetime
import json

from engram.config import Settings
from engram.core import capture, working


def test_summarize_and_update_roundtrip(store):
    events = [{"role": "user", "text": "start the parser rewrite"},
              {"role": "assistant", "text": "ok"},
              {"role": "user", "text": "now refactor the auth module"}]
    st = working.update(store, "s1", events, "svc")
    assert st["summary"].endswith("auth module") or "auth module" in st["summary"]
    loaded = working.load(store, "s1")
    assert loaded["repo"] == "svc" and loaded["turns"] == 2


def test_update_is_noop_without_user_intent(store):
    assert working.update(store, "s2", [{"role": "assistant", "text": "hi"}], "r") is None
    assert working.load(store, "s2") is None


def test_freshness_window():
    now = datetime.datetime.now()
    assert working.is_fresh({"updated_ts": now.timestamp(), "summary": "x"}, 18)
    assert not working.is_fresh({"updated_ts": now.timestamp() - 100 * 3600}, 18)
    assert not working.is_fresh(None, 18)


def test_prune_expired_removes_only_stale(store):
    working.update(store, "fresh", [{"role": "user", "text": "hi"}], "r")
    working.update(store, "old", [{"role": "user", "text": "old"}], "r")
    p = store.root / ".state" / "working" / "old.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["updated_ts"] -= 100 * 3600
    p.write_text(json.dumps(s), encoding="utf-8")

    assert working.prune_expired(store, ttl_hours=18) == 1
    assert working.load(store, "fresh") is not None
    assert working.load(store, "old") is None
    assert working.count(store) == 1


def test_capture_delta_refreshes_working(store, text_backend, tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text(
        '{"type":"user","message":{"role":"user","content":"refactor the auth module please"}}\n'
        '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"ok"}]}}\n',
        encoding="utf-8")
    capture.capture_delta(store, Settings(summarizer="heuristic"),
                          transcript_path=str(t), session_id="sess1", repo="svc",
                          search_backend=text_backend, force=True)
    st = working.load(store, "sess1")
    assert st and "auth module" in st["summary"] and st["repo"] == "svc"
