"""Auto-contradiction detection (mem0/Zep pattern): the extraction LLM is shown the
project's related memories and marks `supersedes` on a fact that makes one obsolete;
capture retires it (recoverably, never deleted). Deterministic via a stub LLM."""
from __future__ import annotations

from engram.config import Settings
from engram.core import capture, memory, summarizer
from engram.roles import get_role


def test_render_prompt_injects_candidates_and_supersede_instruction():
    role = get_role("generic")
    p = summarizer.render_prompt(
        summarizer.DEFAULT_EXTRACTION_PROMPT, role=role, repo="svc", transcript="hi",
        candidates=[{"title": "Old fact", "snippet": "the old way"}])
    assert "Old fact" in p                # candidate injected
    assert "supersedes" in p and "OBSOLETE" in p   # the instruction is present


def test_render_prompt_no_candidates_is_safe():
    role = get_role("generic")
    p = summarizer.render_prompt(summarizer.DEFAULT_EXTRACTION_PROMPT, role=role,
                                 repo=None, transcript="hi")
    assert "(none yet)" in p              # no KeyError, graceful empty


def test_parse_items_reads_supersedes():
    out = summarizer._parse_items(
        '[{"type":"Decision","title":"T","body":"B","supersedes":["Old"]}]')
    assert out[0]["supersedes"] == ["Old"]


def test_capture_auto_supersedes_contradicted_memory(store, generic, text_backend, monkeypatch):
    memory.save(store, generic, type_="Decision", title="Deploy from staging",
                body="we deploy the billing service from the staging branch",
                repo="svc", search_backend=text_backend)

    def fake(store_, settings_, text_, *, role, repo, candidates=None):
        # the candidate retrieval must have surfaced the contradicted memory
        assert any(c["title"] == "Deploy from staging" for c in (candidates or [])), candidates
        return [{"type": "Decision", "title": "Deploy from main",
                 "body": "deploy from the main branch now via blue-green",
                 "supersedes": ["Deploy from staging"]}]
    monkeypatch.setattr(summarizer, "summarize_session", fake)

    capture.capture_session(store, Settings(manage_claude_md=False),
                            transcript_text="user: we now deploy from main not staging\n\nassistant: ok",
                            repo="svc", search_backend=text_backend)
    assert memory.read(store, "Deploy from main") is not None
    old = memory.read(store, "Deploy from staging")
    assert old.frontmatter.get("superseded_by") == "Deploy from main"  # retired, not deleted
    assert old.frontmatter.get("superseded_on")                        # dated


def test_capture_supersede_guard_rejects_uninjected_title(store, generic, text_backend, monkeypatch):
    # a hallucinated supersede target the LLM was NOT shown must be ignored (safety).
    # Vocabulary is disjoint from the transcript so candidate retrieval can't surface it.
    memory.save(store, generic, type_="Decision", title="Quokka telemetry",
                body="quokka exports grpc streaming spans", repo="svc",
                search_backend=text_backend)

    def fake(store_, settings_, text_, *, role, repo, candidates=None):
        assert not any(c["title"] == "Quokka telemetry" for c in (candidates or []))
        return [{"type": "Decision", "title": "Pagination size",
                 "body": "list endpoints return twenty items", "supersedes": ["Quokka telemetry"]}]
    monkeypatch.setattr(summarizer, "summarize_session", fake)

    capture.capture_session(store, Settings(manage_claude_md=False),
                            transcript_text="user: list endpoints should return twenty items\n\nassistant: ok",
                            repo="svc", search_backend=text_backend)
    untouched = memory.read(store, "Quokka telemetry")
    assert not untouched.frontmatter.get("superseded_by")  # guard held — not retired
