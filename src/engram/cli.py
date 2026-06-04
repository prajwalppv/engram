"""Unified `engram` entry point — one binary, dispatched by subcommand.

  engram mcp                 → run the MCP server (stdio)
  engram hook recall|ingest  → the SessionStart/SessionEnd hook worker

This lets us ship ONE self-contained binary (PyInstaller) so the plugin needs
neither uv nor a Python install on the machine.
"""
from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("usage: engram {mcp|hook} [...]", file=sys.stderr)
        raise SystemExit(2)
    cmd, rest = args[0], args[1:]
    if cmd == "mcp":
        from .server import main as server_main
        server_main()
    elif cmd == "hook":
        from .hookcli import main as hook_main
        sys.argv = ["engram-hook", *rest]  # hookcli reads argv[1] = recall|ingest
        hook_main()
    else:
        print(f"engram: unknown command '{cmd}' (use mcp|hook)", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
