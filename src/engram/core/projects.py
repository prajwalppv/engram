"""Project (repo) attribution — answer "which project does this memory belong to?"

The cwd is a weak proxy: you often edit project A from project B's directory (a
plugin, a worktree, a monorepo subdir). The ground truth is the git repository of
the FILES actually being worked on. This resolves a path (or set of paths) to a
stable repo name, generically — no per-project configuration.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

_VERSION_RE = re.compile(r"^v?\d+(\.\d+)+$")  # "0.1.6", "v1.2.3" — a version, not a repo


@lru_cache(maxsize=512)
def repo_name(path: str | None) -> str | None:
    """Stable repo label for a file/dir path: the git repository root's basename.
    Rejects version-string garbage (plugin-cache dirs). ``stat``-gated so the common
    case (the path's own dir is a git root) costs no subprocess. Cached per path."""
    if not path:
        return None
    p = Path(path)
    # A real file → resolve from its directory; a directory or a non-existent path
    # → use the path itself (so a cwd like ".../0.1.6" version-rejects, not its parent).
    base = p.parent if p.is_file() else p
    name = base.name
    needs_resolve = bool(_VERSION_RE.match(name or ""))
    try:
        needs_resolve = needs_resolve or not (base / ".git").exists()
    except Exception:
        needs_resolve = True
    if needs_resolve:
        try:
            r = subprocess.run(["git", "-C", str(base), "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True, timeout=2)
            if r.returncode == 0 and r.stdout.strip():
                name = Path(r.stdout.strip()).name
        except Exception:
            pass
    name = (name or "").strip()
    if not name or _VERSION_RE.match(name):
        return None
    return name


def dominant_repo(paths) -> str | None:
    """The most common repo among ``paths`` (the project a session mostly edited).
    Ties broken by first-seen. None if no path resolves to a repo."""
    names = [repo_name(p) for p in (paths or [])]
    counts = Counter(n for n in names if n)
    if not counts:
        return None
    top = max(counts.values())
    for n in names:  # first-seen among the top-count names (stable)
        if n and counts[n] == top:
            return n
    return None
