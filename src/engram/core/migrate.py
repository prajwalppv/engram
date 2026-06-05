"""One-time, best-effort migration into the unified ``~/.engram/store``.

Before v0.3.1 the store defaulted to ``$CLAUDE_PLUGIN_DATA/store`` — a path that
differs per install identity/host. When an existing user auto-updates to >=0.3.1
the default store path changes, which would *appear* to wipe their memory. This
shim closes that gap: if the new store is empty and a legacy store with content
exists, it copies the richest one over — once.

Safe by construction: it COPIES (never moves or deletes), only runs when the
target is empty, is idempotent (a populated target is a no-op), and never raises
(a failed migration must never break startup).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_SKIP_PARTS = {".archive", ".backups"}


def _note_count(store: Path) -> int:
    if not store.exists():
        return 0
    return sum(1 for p in store.rglob("*.md")
               if not _SKIP_PARTS.intersection(p.parts))


def _legacy_candidates(target: Path) -> list[Path]:
    """Legacy stores that actually contain memory, excluding the target itself."""
    cands: list[Path] = []
    pd = os.environ.get("CLAUDE_PLUGIN_DATA")
    if pd:
        cands.append(Path(pd) / "store")
    data = Path.home() / ".claude" / "plugins" / "data"
    if data.exists():
        for d in sorted(data.iterdir()):
            if d.is_dir() and d.name.startswith("engram"):
                cands.append(d / "store")
    out: list[Path] = []
    seen: set[Path] = set()
    try:
        tgt = target.resolve()
    except Exception:
        tgt = target
    for c in cands:
        try:
            rc = c.resolve()
        except Exception:
            rc = c
        if rc in seen or rc == tgt:
            continue
        seen.add(rc)
        if _note_count(c) > 0:
            out.append(c)
    return out


def maybe_migrate(target: Path) -> dict | None:
    """Populate an empty ``target`` from the richest legacy store, once.

    Returns a small report if it migrated, else None. Never raises.
    """
    try:
        target = Path(target).expanduser()
        if _note_count(target) > 0:
            return None  # already populated — nothing to do
        cands = _legacy_candidates(target)
        if not cands:
            return None
        src = max(cands, key=_note_count)
        target.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            dest = target / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif not dest.exists():
                shutil.copy2(item, dest)
        report = {"migrated_from": str(src), "notes": _note_count(target)}
        print(f"[engram] migrated memory from {src} → {target} "
              f"({report['notes']} notes). Your old store is left untouched.",
              file=sys.stderr)
        return report
    except Exception as e:  # best-effort: never break startup
        print(f"[engram] store migration skipped: {e}", file=sys.stderr)
        return None
