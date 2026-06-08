from __future__ import annotations

import json

from engram.core import export, graph, ingest, memory


# --- graph ---------------------------------------------------------------
def test_graph_links_and_backlinks(store, swe):
    memory.save(store, swe, type_="Decision", title="Auth design", body="see [[Use Postgres]]",
                links=["Use Postgres"])
    memory.save(store, swe, type_="Decision", title="Use Postgres", body="db")
    out = {l.target for l in graph.outgoing_links(store, "Auth design")}
    assert "Use Postgres" in out
    back = graph.backlinks(store, "Use Postgres")
    assert any("Auth design" in (b.source_rel_path or "") for b in back)


def test_neighborhood(store, swe):
    memory.save(store, swe, type_="Decision", title="A", body="[[B]]", links=["B"])
    memory.save(store, swe, type_="Decision", title="B", body="leaf")
    assert "B" in graph.neighborhood(store, "A", depth=1)


# --- ingest --------------------------------------------------------------
def test_read_transcript_and_distill(tmp_path):
    tpath = tmp_path / "t.jsonl"
    rows = [
        {"message": {"role": "user", "content": [{"type": "text", "text": "Add retry to the API client"}]}},
        {"message": {"role": "assistant", "content": [{"type": "text", "text": "Added exponential backoff; capped at 5 retries."}]}},
    ]
    tpath.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    events = ingest.read_transcript(tpath)
    assert len(events) == 2 and events[0]["role"] == "user"
    d = ingest.distill(events, repo="client")
    assert "retry" in d["title"].lower() or "Add retry" in d["full_text"]
    assert "Intent" in d["body"] and "Outcome" in d["body"]


def test_hookcli_ingest_and_recall(tmp_path, monkeypatch, capsys):
    store_dir = tmp_path / "store"
    monkeypatch.setenv("ENGRAM_STORE_DIR", str(store_dir))
    monkeypatch.setenv("ENGRAM_SUMMARIZER", "heuristic")  # never call claude in tests
    tpath = tmp_path / "t.jsonl"
    tpath.write_text(json.dumps({"message": {"role": "user", "content": "Fix the deploy script"}}) + "\n",
                     encoding="utf-8")

    from engram import hookcli
    # ingest: feed SessionEnd payload on stdin
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(
        {"transcript_path": str(tpath), "cwd": "/work/myrepo", "session_id": "s1"})))
    assert hookcli.cmd_ingest() == 0
    # a SessionSummary memory now exists for repo "myrepo"
    from engram.core.store import FileSystemBackend, Store
    st = Store(FileSystemBackend(store_dir))
    ents = memory.list_recent(st, repo="myrepo")
    assert ents and ents[0].type == "SessionSummary"

    # recall: SessionStart payload → emits additionalContext JSON
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps({"cwd": "/work/myrepo"})))
    assert hookcli.cmd_recall() == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "myrepo" in payload["hookSpecificOutput"]["additionalContext"]


# --- export (dormant) ----------------------------------------------------
def test_export_is_dormant(store, swe):
    # eligibility is now the `visibility` axis (export), separate from `scope`
    memory.save(store, swe, type_="Decision", title="X", body="b", visibility="team")
    res = export.export(store, scope="team")  # `scope` here names a visibility level
    assert res["status"] == "not_implemented"
    assert res["eligible_count"] == 1


class _Stdin:
    def __init__(self, data: str):
        self._data = data

    def read(self) -> str:
        return self._data


def test_provenance_origin_and_temporal_lineage(store, swe, text_backend):
    memory.save(store, swe, type_="Decision", title="DB choice",
                body="we use sqlite for storage", session_id="sess-1",
                search_backend=text_backend)
    new = memory.save(store, swe, type_="Decision", title="DB choice current",
                      body="we moved to postgres now", supersedes=["DB choice"],
                      links=["DB choice"], session_id="sess-2",
                      search_backend=text_backend)
    assert new.action == "created"

    # current fact: origin + what it retired, not itself retired
    cur = graph.provenance(store, "DB choice current")
    assert cur["created"] and cur["source_session"] == "sess-2"
    assert "DB choice" in cur["supersedes"]
    assert cur["retired"] is False

    # retired fact: dated back-reference to its replacement
    old = graph.provenance(store, "DB choice")
    assert old["retired"] is True
    assert old["superseded_by"] == "DB choice current"
    assert old["superseded_on"]
