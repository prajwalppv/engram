"""MCP tool adapters — thin glue over the on-device core. The only layer that
imports `mcp`. The active role is resolved dynamically (it's inferred), so tools
compute it per-call from the store + the pin/override.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..core.search_backends import SearchBackend
from ..core.store import Store


@dataclass
class Deps:
    store: Store
    search_backend: SearchBackend
    settings: Settings
