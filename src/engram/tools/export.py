"""Export tool — the dormant team-sharing seam (intentionally not enabled)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..core import export as _export
from . import Deps


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool()
    def memory_export(scope: str = "team", redact: bool = True) -> dict:
        """Reserved for a future opt-in, sanitized team export. Not enabled — memory
        is local and private. Reports which memories *would* be eligible (those not
        marked private). Sharing will always be explicit and redacted, never automatic.
        """
        return _export.export(deps.store, scope=scope, redact=redact)
