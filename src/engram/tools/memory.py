"""Memory tools: save, recall, ingest-session, read, mark-used."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ..core import capture, feedback, ingest, memory, preferences
from ..core import roles as role_engine
from ..core.errors import CoreError
from . import Deps


def register(mcp: FastMCP, deps: Deps) -> None:
    def _role():
        return role_engine.current_role(deps.store, deps.settings.role)

    @mcp.tool()
    def memory_save(
        type: str,
        title: str,
        body: str,
        repo: str | None = None,
        tags: list[str] | None = None,
        links: list[str] | None = None,
        scope: str | None = None,
        horizon: str = "semantic",
        area: str | None = None,
        supersedes: list[str] | None = None,
    ) -> dict:
        """Save a durable memory (a graph node). Appends a dated block if the title
        already exists (memory accumulates; nothing is overwritten).

        Args:
            type: Node type (role-specific, e.g. "Decision", "Gotcha", "Requirement").
            title: Short, unique title — also the wikilink target.
            body: The memory content (markdown).
            repo: Project this relates to (sets repo applicability).
            tags: Optional tags.
            links: Titles of related memories to link to ([[wikilinks]]).
            scope: Applicability — global | role | area | repo | session. Default:
                global, or repo if a repo is given (preference→global, working→session).
            horizon: working | episodic | procedural | semantic | preference.
            area: Cross-repo domain for area-scoped memories (e.g. "python").
            supersedes: Titles of older memories this one replaces (retires them
                from recall — how a more-specific rule overrides a general one).
        """
        try:
            return memory.save(
                deps.store, _role(), type_=type, title=title, body=body, repo=repo,
                tags=tags, links=links, scope=scope, horizon=horizon, area=area,
                supersedes=supersedes, search_backend=deps.search_backend,
            ).model_dump()
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_list_preferences() -> list[dict]:
        """List the standing preferences engram has learned (the always-on layer).

        These apply across every session/repo and are injected automatically.
        Use memory_forget to remove one.
        """
        return [{"id": e.id, "title": e.title, "preference": e.body.strip(),
                 "created": str(e.frontmatter.get("created") or "")}
                for e in preferences.list_preferences(deps.store)]

    @mcp.tool()
    def memory_forget(identifier: str) -> dict:
        """Forget ANY memory — preference, decision, gotcha, note, etc. (easy undo).
        Archives it (recoverable) and drops it from recall + the index; if it was a
        preference, also removes it from the managed CLAUDE.md block on next session.

        Args:
            identifier: The memory's id, title, or relative path.
        """
        res = preferences.forget(deps.store, identifier, search_backend=deps.search_backend)
        if deps.settings.claude_md_path:
            try:
                preferences.sync_claude_md(deps.store, str(deps.settings.claude_md_path))
            except Exception:
                pass
        return res

    @mcp.tool()
    def memory_recall(
        query: str, repo: str | None = None, type: str | None = None, limit: int = 8
    ) -> list[dict]:
        """Recall memories relevant to a query (semantic when enabled).

        Call this at the start of work to surface prior decisions/gotchas/context.

        Returns a COMPACT INDEX — each hit has a bounded `snippet` and a `created`
        date, but NOT the full body. Judge relevance from the snippet and fetch the
        full body with `memory_read(id)` only for the hits you actually need
        (progressive disclosure — keeps recall token-cheap). `created` is an age
        signal: prefer the most recent when two hits seem to contradict.

        Args:
            query: What you're working on / looking for.
            repo: Restrict to a project.
            type: Restrict to a node type.
            limit: Max results.
        """
        hits = memory.recall(deps.store, deps.search_backend, query,
                             repo=repo, type_=type, role=_role().name,
                             area=deps.settings.area, limit=limit,
                             hybrid=deps.settings.recall_hybrid,
                             expand_graph=deps.settings.recall_graph_expand)
        feedback.record_recall(deps.store, query, [h.id for h in hits if h.id])
        return [h.model_dump() for h in hits]

    @mcp.tool()
    def memory_ingest_session(
        transcript_path: str | None = None,
        text: str | None = None,
        repo: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Distill a finished session into memory and update the inferred role.

        Used by the SessionEnd hook. Provide either a transcript path or raw text.
        Returns the saved summary and the updated role status.
        """
        if transcript_path:
            content = ingest.transcript_text(transcript_path)
        elif text:
            content = text
        else:
            raise ToolError("Provide transcript_path or text.")
        try:
            results = capture.capture_session(
                deps.store, deps.settings, transcript_text=content,
                repo=repo, session_id=session_id, search_backend=deps.search_backend,
            )
            return {
                "saved": [r.model_dump() for r in results],
                "count": len(results),
                "role": role_engine.status(deps.store, deps.settings.role),
            }
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_read(identifier: str) -> dict:
        """Read a memory by id, title, or relative path."""
        try:
            entry = memory.read(deps.store, identifier)
        except CoreError as e:
            raise ToolError(str(e)) from e
        # Fetching a full body after the compact recall index is an implicit
        # usefulness vote — feed it back into ranking/pruning. Best-effort.
        try:
            feedback.record_read(deps.store, [entry.id])
        except Exception:
            pass
        return entry.model_dump()

    @mcp.tool()
    def memory_mark_used(ids: list[str], roles: list[str] | None = None) -> dict:
        """Record that recalled memories were actually useful (feedback signal).

        Reinforces the producing role(s) and logs the signal for later tuning.
        This is ALSO a recall-eval label — a (query → useful memory) positive.
        """
        feedback.record_signal(deps.store, "used", ids, roles_used=roles)
        return {"recorded": "used", "count": len(ids)}

    @mcp.tool()
    def memory_reindex() -> dict:
        """Rebuild/repair the semantic index from the store, healing any drift
        (memories present on disk but missing from the index — i.e. un-recallable).
        Reports what was out of sync before and after. No-op for the text backend.
        """
        sb = deps.search_backend
        before = sb.verify(deps.store) if hasattr(sb, "verify") else None
        result = sb.reindex_all(deps.store)
        after = sb.verify(deps.store) if hasattr(sb, "verify") else None
        return {"before": before, "reindex": result, "after": after}

    @mcp.tool()
    def memory_backfill(dry_run: bool = True) -> dict:
        """Heal an existing store's graph: link related orphans together and remove
        dangling links (edges to notes that no longer exist). Useful on a store that
        predates auto-linking. ``dry_run=True`` (default) reports what WOULD change
        without writing — review it, then call with dry_run=False to apply."""
        from engram.core import consolidate
        links = consolidate.backfill_links(deps.store, deps.search_backend, dry_run=dry_run)
        dangling = consolidate.prune_dangling_links(deps.store, dry_run=dry_run)
        if not dry_run:
            try:
                deps.search_backend.reindex_all(deps.store)
            except Exception:
                pass
        return {"backfill_links": links, "prune_dangling": dangling, "dry_run": dry_run}
