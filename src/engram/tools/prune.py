"""Pruning tools: prune (dry-run by default), restore, effectiveness."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..core import prune as _prune
from . import Deps


def register(mcp: FastMCP, deps: Deps) -> None:
    @mcp.tool()
    def memory_prune(dry_run: bool = True) -> dict:
        """Bonsai-prune the memory graph: fold stale, low-vigor, unreferenced
        session leaves into per-repo digests (consolidate, never delete). Durable
        memories are kept; pruned items are archived (recoverable). Bounded per
        cycle. DRY-RUN by default — returns the plan + before/after metrics.

        Args:
            dry_run: If true (default), only report what would be pruned.
        """
        return _prune.prune(deps.store, deps.settings, deps.search_backend, dry_run=dry_run)

    @mcp.tool()
    def memory_restore(identifier: str) -> dict:
        """Restore a pruned memory from the archive (also logs it as a pruning
        mistake — a 'resurrection' signal used to measure prune quality)."""
        return _prune.restore(deps.store, identifier)

    @mcp.tool()
    def memory_prune_effectiveness() -> dict:
        """Report pruning effectiveness over time: per-cycle node/ephemeral/vigor
        deltas and the resurrection rate (the key quality signal to minimize)."""
        return _prune.effectiveness(deps.store)
