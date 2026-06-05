from __future__ import annotations

from engram.core import memory


def test_save_creates_routed_by_role(store, swe):
    res = memory.save(store, swe, type_="Decision", title="Use Postgres",
                      body="Chose Postgres over Mongo for relational integrity.",
                      repo="payments", tags=["db"])
    assert res.action == "created"
    assert res.rel_path == "Decisions/Use Postgres.md"
    ent = memory.read(store, "Use Postgres")
    assert ent.type == "Decision" and ent.repo == "payments"
    # scope is now the applicability ladder (repo, since a repo was given);
    # the dormant export axis lives on `visibility` (default private).
    assert ent.role == "swe" and ent.scope == "repo" and ent.visibility == "private"
    assert "Postgres" in ent.body


def test_save_again_appends_not_overwrites(store, swe):
    memory.save(store, swe, type_="Gotcha", title="Flaky auth test",
                body="It fails under parallel runs.")
    res = memory.save(store, swe, type_="Gotcha", title="Flaky auth test",
                      body="Root cause: shared fixture state.", session_id="s2")
    assert res.action == "appended"
    ent = memory.read(store, "Flaky auth test")
    assert "parallel runs" in ent.body and "shared fixture state" in ent.body


def test_links_merge_on_append(store, swe):
    memory.save(store, swe, type_="Decision", title="Auth design", body="v1",
                links=["Use Postgres"])
    memory.save(store, swe, type_="Decision", title="Auth design", body="v2",
                links=["Session Store"])
    ent = memory.read(store, "Auth design")
    assert "Use Postgres" in ent.links and "Session Store" in ent.links


def test_recall_text(store, swe, text_backend):
    memory.save(store, swe, type_="Decision", title="Use Postgres", body="relational db choice")
    hits = memory.recall(store, text_backend, "postgres database", limit=5)
    assert any(h.title == "Use Postgres" for h in hits)


def test_recall_repo_filter(store, swe, text_backend):
    memory.save(store, swe, type_="Gotcha", title="A", body="x", repo="alpha")
    memory.save(store, swe, type_="Gotcha", title="B", body="x", repo="beta")
    hits = memory.recall(store, text_backend, "x", repo="alpha", limit=5)
    titles = [h.title for h in hits]
    assert "A" in titles and "B" not in titles


def test_list_recent(store, swe):
    memory.save(store, swe, type_="Decision", title="One", body="...", repo="r")
    memory.save(store, swe, type_="Decision", title="Two", body="...", repo="r")
    recent = memory.list_recent(store, repo="r", limit=5)
    assert {e.title for e in recent} == {"One", "Two"}
