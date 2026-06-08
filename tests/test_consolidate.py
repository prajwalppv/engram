"""Lever 2 — near-duplicate consolidation (the noisy-heart fix). Deterministic on
the text backend via token-Jaccard; no model download."""
from __future__ import annotations

from engram.config import Settings
from engram.core import capture, consolidate, memory, summarizer


# ---------------------------------------------------------------- jaccard
def test_jaccard():
    assert consolidate.jaccard(set(), {"a"}) == 0.0
    assert consolidate.jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert 0.3 < consolidate.jaccard({"a", "b", "c"}, {"a", "b", "d"}) < 0.6


# ---------------------------------------------------------------- detection
def test_near_duplicate_detects_restatement(store, generic, text_backend):
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis as the session cache layer", search_backend=text_backend)
    dup = consolidate.near_duplicate(
        store, text_backend, type_="Decision",
        title="Cache with Redis",
        body="we use redis as the session cache layer for sessions")
    assert dup is not None and dup.title == "Use Redis for cache"


def test_near_duplicate_rejects_distinct(store, generic, text_backend):
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis as the session cache layer", search_backend=text_backend)
    dup = consolidate.near_duplicate(
        store, text_backend, type_="Decision",
        title="Postgres for billing",
        body="store money as integer cents in postgres with row-level transactions")
    assert dup is None


def test_near_duplicate_respects_type(store, generic, text_backend):
    memory.save(store, generic, type_="Gotcha", title="Redis eviction",
                body="we use redis as the session cache layer", search_backend=text_backend)
    # same content but probing for a Decision → must NOT match the Gotcha
    dup = consolidate.near_duplicate(
        store, text_backend, type_="Decision",
        title="Cache with Redis", body="we use redis as the session cache layer")
    assert dup is None


def test_exact_title_is_not_a_near_dup(store, generic, text_backend):
    # exact-title restatement is memory.save's append path, not a near-dup
    memory.save(store, generic, type_="Decision", title="Use Redis",
                body="redis session cache layer", search_backend=text_backend)
    dup = consolidate.near_duplicate(store, text_backend, type_="Decision",
                                     title="Use Redis", body="redis session cache layer again")
    assert dup is None


# ---------------------------------------------------------------- capture merges
def test_capture_merges_near_duplicate(store, generic, text_backend, monkeypatch):
    # seed an existing decision
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis as the session cache layer", search_backend=text_backend)
    before = sum(1 for _ in store.iter_entries())

    # summarizer yields a RESTATEMENT (different title, same fact) + a DISTINCT fact
    def fake_items(store_, settings_, text_, *, role, repo):
        return [
            {"type": "Decision", "title": "Cache via Redis",
             "body": "we use redis as the session cache layer for sessions"},
            {"type": "Decision", "title": "Blue-green deploys",
             "body": "ship releases with blue-green to avoid downtime"},
        ]
    monkeypatch.setattr(summarizer, "summarize_session", fake_items)

    capture.capture_session(store, Settings(), transcript_text="user: stuff\n\nassistant: ok",
                            repo="svc", search_backend=text_backend)
    after = sum(1 for _ in store.iter_entries())
    # restatement merged into the existing node; only the DISTINCT fact is new (+1)
    assert after == before + 1, (before, after)
    merged = memory.read(store, "Use Redis for cache")
    assert "for sessions" in merged.body          # restatement appended
    assert memory.read(store, "Blue-green deploys") is not None


# ---------------------------------------------------------------- auto-linking
def test_related_links_related_not_unrelated(store, generic, text_backend):
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis for the session cache layer", search_backend=text_backend)
    # related (shares topic, below dedup) → linked
    rel = consolidate.related(store, text_backend, title="Redis eviction",
                              body="redis cache eviction policy for sessions")
    assert "Use Redis for cache" in rel
    # unrelated → no link
    none = consolidate.related(store, text_backend, title="Billing",
                               body="store money as integer cents in postgres")
    assert none == []


def test_related_excludes_self_and_near_dups(store, generic, text_backend):
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis for the session cache layer", search_backend=text_backend)
    # a near-DUP (very high overlap) is not a "related" link — it would merge instead
    rel = consolidate.related(store, text_backend, title="Cache via Redis",
                              body="we use redis for the session cache layer")
    assert "Use Redis for cache" not in rel


def test_capture_autolinks_new_node(store, generic, text_backend, monkeypatch):
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis for the session cache layer", search_backend=text_backend)

    def fake_items(store_, settings_, text_, *, role, repo):
        return [{"type": "Gotcha", "title": "Redis eviction surprises",
                 "body": "redis cache eviction can drop session keys unexpectedly"}]
    monkeypatch.setattr(summarizer, "summarize_session", fake_items)

    capture.capture_session(store, Settings(), transcript_text="user: x\n\nassistant: y",
                            repo="svc", search_backend=text_backend)
    g = memory.read(store, "Redis eviction surprises")
    assert "Use Redis for cache" in (g.links or [])   # cross-type relatedness link


def test_capture_dedup_can_be_disabled(store, generic, text_backend, monkeypatch):
    memory.save(store, generic, type_="Decision", title="Use Redis for cache",
                body="we use redis as the session cache layer", search_backend=text_backend)
    before = sum(1 for _ in store.iter_entries())

    def fake_items(store_, settings_, text_, *, role, repo):
        return [{"type": "Decision", "title": "Cache via Redis",
                 "body": "we use redis as the session cache layer for sessions"}]
    monkeypatch.setattr(summarizer, "summarize_session", fake_items)

    capture.capture_session(store, Settings(dedup_on_capture=False),
                            transcript_text="user: x\n\nassistant: y", repo="svc",
                            search_backend=text_backend)
    after = sum(1 for _ in store.iter_entries())
    assert after == before + 1  # dedup off → a near-dup node IS created
