"""Role tools: inspect inferred role, or pin it."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..core import roles as role_engine
from . import Deps


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool()
    def role_status() -> dict:
        """Show the active role (inferred or pinned), the soft weights over roles,
        and how many sessions have been observed. All local."""
        return role_engine.status(deps.store, deps.settings.role)

    @mcp.tool()
    def role_set(role: str) -> dict:
        """Pin the active role (persists), or pass "auto" to return to inference.

        Args:
            role: One of the available roles (e.g. "swe", "pm", "em"), or "auto".
        """
        role_engine.set_pinned(deps.store, None if role == "auto" else role)
        return role_engine.status(deps.store, deps.settings.role)
