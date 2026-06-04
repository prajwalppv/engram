"""engram — a private, on-device memory layer for Claude Code.

Architecture (seams mirrored from obsidian-mcp, rebuilt for the memory domain):
  * ``core/``  — vendor-neutral memory engine. No MCP imports. Filesystem-backed
                 markdown graph + local semantic recall + safety.
  * ``roles/`` — the Profile seam applied to PEOPLE. A role (SWE/PM/EM/…) defines
                 the memory ontology and extraction/recall behaviour. Discoverable
                 via the ``engram.roles`` entry-point group.
  * ``tools/`` + ``server.py`` — a thin MCP adapter (stdio) over ``core``.

Everything is local and per-user. Nothing leaves the machine.
"""

__version__ = "0.1.0"
