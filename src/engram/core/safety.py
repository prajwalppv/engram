"""Safety: path containment + backup-before-overwrite + optional git snapshot.

Hard guarantees: never escape the store, back up before any
overwrite, never delete. (git_snapshot is here so an opt-in personal encrypted
backup can reuse it later — off by default.)
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .errors import StoreSafetyError


def resolve_in_store(store_root: Path, rel_or_abs: str | Path) -> Path:
    root = store_root.resolve()
    cand = Path(rel_or_abs)
    target = cand if cand.is_absolute() else (root / cand)
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        raise StoreSafetyError(f"Refusing to touch '{rel_or_abs}': outside the store.")
    return resolved


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_file(store_root: Path, target: Path, backup_dir_name: str) -> Path:
    root = store_root.resolve()
    rel = target.resolve().relative_to(root)
    dest = root / backup_dir_name / _stamp() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, dest)
    return dest


def git_snapshot(store_root: Path, message: str) -> bool:
    root = str(store_root)
    base = ["git", "-c", f"safe.directory={root}", "-C", root]

    def g(*a):
        return subprocess.run([*base, *a], capture_output=True, text=True)

    try:
        if g("rev-parse", "--git-dir").returncode != 0:
            return False
        ident = []
        if g("config", "user.email").returncode != 0:
            ident = ["-c", "user.name=engram", "-c", "user.email=engram@local"]
        g("add", "-A")
        r = subprocess.run(["git", "-c", f"safe.directory={root}", *ident, "-C", root,
                            "commit", "-q", "-m", message], capture_output=True, text=True)
        return r.returncode == 0 or "nothing to commit" in (r.stdout + r.stderr).lower()
    except (OSError, FileNotFoundError):
        return False
