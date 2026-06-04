"""Memory tools: save, recall, ingest-session, read, mark-used."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ..core import feedback, ingest, memory
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
        scope: str = "private",
    ) -> dict:
        """Save a durable memory (a graph node). Appends a dated block if the title
        already exists (memory accumulates; nothing is overwritten).

        Args:
            type: Node type (role-specific, e.g. "Decision", "Gotcha", "Requirement").
            title: Short, unique title — also the wikilink target.
            body: The memory content (markdown).
            repo: Project this relates to (for scoped recall).
            tags: Optional tags.
            links: Titles of related memories to link to ([[wikilinks]]).
            scope: "private" (default). The dormant team-export seam reads this.
        """
        try:
            return memory.save(
                deps.store, _role(), type_=type, title=title, body=body, repo=repo,
                tags=tags, links=links, scope=scope, search_backend=deps.search_backend,
            ).model_dump()
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_recall(
        query: str, repo: str | None = None, type: str | None = None, limit: int = 8
    ) -> list[dict]:
        """Recall memories relevant to a query (semantic when enabled).

        Call this at the start of work to surface prior decisions/gotchas/context.

        Args:
            query: What you're working on / looking for.
            repo: Restrict to a project.
            type: Restrict to a node type.
            limit: Max results.
        """
        hits = memory.recall(deps.store, deps.search_backend, query,
                             repo=repo, type_=type, limit=limit)
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
        try:
            if transcript_path:
                distilled = ingest.distill_path(transcript_path, repo=repo)
            elif text:
                events = [{"role": "user", "text": text}]
                distilled = ingest.distill(events, repo=repo, full_text=text)
            else:
                raise ToolError("Provide transcript_path or text.")
            if not distilled:
                return {"saved": None, "reason": "nothing substantive to capture"}

            role_engine.update_from_session(deps.store, distilled["full_text"])
            res = memory.save(
                deps.store, _role(), type_="SessionSummary",
                title=distilled["title"], body=distilled["body"],
                repo=repo, session_id=session_id, search_backend=deps.search_backend,
            )
            return {
                "saved": res.model_dump(),
                "role": role_engine.status(deps.store, deps.settings.role),
            }
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_read(identifier: str) -> dict:
        """Read a memory by id, title, or relative path."""
        try:
            return memory.read(deps.store, identifier).model_dump()
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_mark_used(ids: list[str], roles: list[str] | None = None) -> dict:
        """Record that recalled memories were actually useful (feedback signal).

        Reinforces the producing role(s) and logs the signal for later tuning.
        """
        feedback.record_signal(deps.store, "used", ids, roles_used=roles)
        return {"recorded": "used", "count": len(ids)}
