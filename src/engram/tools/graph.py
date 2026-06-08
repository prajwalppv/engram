"""Graph tools: backlinks and neighborhood (graph-aware recall)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from ..core import graph
from ..core.errors import CoreError
from . import Deps


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool()
    def memory_backlinks(identifier: str) -> list[dict]:
        """List memories that link to the given one (by id, title, or path)."""
        try:
            return [r.model_dump() for r in graph.backlinks(deps.store, identifier)]
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_neighborhood(identifier: str, depth: int = 1) -> list[str]:
        """Titles of memories within `depth` link-hops of the given one — the
        connected context around a node."""
        try:
            return graph.neighborhood(deps.store, identifier, depth=depth)
        except CoreError as e:
            raise ToolError(str(e)) from e

    @mcp.tool()
    def memory_why(identifier: str) -> dict:
        """Provenance of a memory: WHY it's here and whether it's still current.

        Returns its origin (created date, source session, role/scope), its temporal
        lineage (`supersedes` = what it retired; `superseded_by`/`superseded_on` +
        `retired` = whether a newer fact replaced it), and its graph context
        (`links`, `backlinks`). Use it to trust or discount a recalled fact.
        """
        try:
            return graph.provenance(deps.store, identifier)
        except CoreError as e:
            raise ToolError(str(e)) from e
