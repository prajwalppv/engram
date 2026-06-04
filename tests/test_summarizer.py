from __future__ import annotations

from engram.config import Settings
from engram.core import capture, memory, summarizer
from engram.core import roles as R


def test_parse_items_tolerates_surrounding_prose():
    raw = 'Sure! Here:\n[{"type":"Decision","title":"Use X","body":"because Y","links":[],"tags":["t"]}]\nDone.'
    items = summarizer._parse_items(raw)
    assert len(items) == 1 and items[0]["type"] == "Decision" and items[0]["title"] == "Use X"


def test_parse_items_skips_incomplete():
    raw = '[{"title":"no body"},{"type":"Gotcha","title":"Real","body":"b"}]'
    items = summarizer._parse_items(raw)
    assert [i["title"] for i in items] == ["Real"]


def test_heuristic_summarizer(swe):
    items = summarizer.HeuristicSummarizer().summarize(
        "user: add retries\nassistant: added backoff", role=swe, repo="client")
    assert items and items[0]["type"] == "SessionSummary"


def test_capture_session_heuristic_saves_and_updates_role(store):
    settings = Settings(summarizer="heuristic", role="auto")
    text = ("user: fixed a null pointer exception in the API endpoint, added a unit "
            "test and opened a PR to deploy")
    results = capture.capture_session(store, settings, transcript_text=text, repo="svc")
    assert results and results[0].action == "created"
    # role inference ran from the (swe-flavored) session
    assert R.current_role_name(store) == "swe"


def test_capture_session_llm_saves_multiple_typed_nodes(store, monkeypatch):
    settings = Settings(summarizer="claude", role="swe")

    def fake_summarize(self, transcript_text, *, role, repo):
        return [
            {"type": "Decision", "title": "Adopt feature flags", "body": "Ship dark.",
             "links": [], "tags": ["release"]},
            {"type": "Gotcha", "title": "Flag cache TTL", "body": "Stale for 60s.",
             "links": ["Adopt feature flags"], "tags": []},
        ]

    monkeypatch.setattr(summarizer.ClaudeHeadlessSummarizer, "available", lambda self: True)
    monkeypatch.setattr(summarizer.ClaudeHeadlessSummarizer, "summarize", fake_summarize)

    results = capture.capture_session(store, settings, transcript_text="...", repo="svc")
    assert len(results) == 2
    types = {memory.read(store, r.rel_path).type for r in results}
    assert types == {"Decision", "Gotcha"}
    # the typed link survived
    gotcha = memory.read(store, "Flag cache TTL")
    assert "Adopt feature flags" in gotcha.links


def test_capture_falls_back_to_heuristic_when_llm_unavailable(store, monkeypatch):
    settings = Settings(summarizer="claude", role="auto")
    monkeypatch.setattr(summarizer.ClaudeHeadlessSummarizer, "available", lambda self: False)
    text = "user: refactored the deploy script\nassistant: done, tested the build"
    results = capture.capture_session(store, settings, transcript_text=text, repo="svc")
    assert results and memory.read(store, results[0].rel_path).type == "SessionSummary"
