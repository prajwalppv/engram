"""Entry point: build the local store + search backend, register tools, run.

Default transport is stdio (the plugin spawns this locally). Everything is
on-device; there is no network/auth path.
"""
from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from .config import Settings, load_settings
from .core import roles as role_engine
from .core.search_backends import TextSearchBackend
from .core.store import FileSystemBackend, Store
from .roles import available_roles
from .tools import Deps
from .tools import export as t_export
from .tools import graph as t_graph
from .tools import memory as t_memory
from .tools import role as t_role


def _build_search_backend(settings: Settings, store: Store):
    if settings.search_backend.lower() == "semantic":
        import importlib.util
        missing = [m for m in ("fastembed", "numpy") if importlib.util.find_spec(m) is None]
        if missing:
            print(f"[engram] semantic recall needs {', '.join(missing)} "
                  f"(install the 'semantic' extra); using text recall", file=sys.stderr)
        else:
            from .core.search_backends import SemanticSearchBackend
            return SemanticSearchBackend(
                store, index_dir=settings.resolved_index_dir(),
                model_name=settings.embedding_model,
            )
    return TextSearchBackend(store)


def build_server(settings: Settings) -> FastMCP:
    store = Store(FileSystemBackend(settings.resolved_store()))
    search_backend = _build_search_backend(settings, store)

    mcp = FastMCP(
        name="engram",
        host=settings.host,
        port=settings.port,
        instructions=(
            "On-device, private memory for Claude Code. Use memory_recall at the "
            "start of work to surface prior decisions/gotchas, and memory_save to "
            "remember durable facts. memory_ingest_session is called automatically "
            "at session end. Memory is role-aware and never leaves this machine."
        ),
    )

    deps = Deps(store=store, search_backend=search_backend, settings=settings)
    for module in (t_memory, t_graph, t_role, t_export):
        module.register(mcp, deps)

    @mcp.tool()
    def engram_info() -> dict:
        """Report engram status: store path, role, search backend, memory count."""
        try:
            search_info = search_backend.stats()
        except Exception as e:  # pragma: no cover
            search_info = {"backend": "unknown", "error": str(e)}
        return {
            "store": str(settings.resolved_store()),
            "role": role_engine.status(store, settings.role),
            "available_roles": available_roles(),
            "search": search_info,
            "memory_count": sum(1 for _ in store.iter_entries()),
            "privacy": "on-device only; nothing leaves this machine",
        }

    return mcp


def main() -> None:
    settings = load_settings()
    mcp = build_server(settings)
    transport = settings.transport.lower()
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("http", "streamable-http"):
        print(f"[engram] streamable-http on http://{settings.host}:{settings.port}/mcp",
              file=sys.stderr)
        mcp.run(transport="streamable-http")
    else:
        raise SystemExit(f"Unknown ENGRAM_TRANSPORT='{settings.transport}'.")


if __name__ == "__main__":
    main()
