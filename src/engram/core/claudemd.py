"""Maintain an engram-managed block inside a CLAUDE.md file — the persistent half
of the hybrid always-on layer. We ONLY ever touch content between our markers, so
the rest of the user's CLAUDE.md is never disturbed. Atomic (temp + rename)."""
from __future__ import annotations

import os
from pathlib import Path

START = "<!-- engram:preferences:start -->"
END = "<!-- engram:preferences:end -->"


def _strip_block(text: str) -> str:
    if START in text and END in text:
        pre = text.split(START, 1)[0].rstrip("\n")
        post = text.split(END, 1)[1].lstrip("\n")
        return (pre + ("\n\n" if pre and post else "") + post).rstrip()
    return text.rstrip()


def update_managed_block(path: Path, content: str) -> bool:
    """Create/replace engram's block in CLAUDE.md at ``path`` (append on first
    write). Empty ``content`` removes the block. Returns True if the file changed."""
    path = Path(path).expanduser()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    base = _strip_block(existing)
    if content.strip():
        block = f"{START}\n{content.rstrip()}\n{END}"
        new = (base + "\n\n" + block + "\n") if base else (block + "\n")
    else:
        new = (base + "\n") if base else ""
    if new == existing:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.engram.tmp")
    tmp.write_text(new, encoding="utf-8")
    os.replace(tmp, path)
    return True
