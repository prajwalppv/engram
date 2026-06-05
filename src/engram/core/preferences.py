"""Preference / guidance memory — the always-on horizon.

Standing operating rules the user states ("always use uv", "never force-push to
main", "I prefer terse answers"). These are GLOBAL (apply across every repo) and
the most powerful memory engram holds, so they're delivered every session via the
hybrid always-on layer (a managed CLAUDE.md block + SessionStart context). They
are pruning LIFELINES — never auto-removed; only the user forgets them.

Detection is deterministic and conservative (offline, no LLM): we only fire on a
strong standing-instruction cue or an imperative sentence start, scoped to the
user's own turns — auto-store, with one-tap undo via `forget`.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from . import memory
from .models import MemoryEntry

if TYPE_CHECKING:
    from ..roles.base import Role
    from .models import SaveResult
    from .search_backends import SearchBackend
    from .store import Store

PREFERENCE_TYPE = "Preference"
PREFERENCE_HORIZON = "preference"
_MAX_PER_SESSION = 5

# High-precision signals that a sentence is a STANDING instruction to the assistant.
_STRONG_CUE = re.compile(
    r"\b(from now on|going forward|as a rule|by default|i'?d? ?(?:would )?prefer|"
    r"i want you to|i'?d like you to|please (?:always|never)|make sure to always|"
    r"remember to always|stick to|default to|whenever you)\b", re.I)
# Imperative sentence starts that read as a rule, not a one-off ask.
_IMPERATIVE_START = re.compile(r"^\s*(always|never|prefer|avoid|don'?t|do not)\b", re.I)

_USER_TURN_RE = re.compile(r"(?:^|\n)user:\s*(.*?)(?=\n(?:assistant|user):|\Z)",
                           re.I | re.S)
_SENT_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


def _user_text(transcript_text: str) -> str:
    turns = _USER_TURN_RE.findall(transcript_text or "")
    return "\n".join(turns) if turns else (transcript_text or "")


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.lower()).strip()


def detect(transcript_text: str) -> list[str]:
    """Distinct standing-preference statements found in the user's turns."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in _SENT_SPLIT.split(_user_text(transcript_text)):
        s = raw.strip().lstrip("-*•").strip()
        if not (8 <= len(s) <= 240):
            continue
        if not (_STRONG_CUE.search(s) or _IMPERATIVE_START.match(s)):
            continue
        key = _norm(s)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= _MAX_PER_SESSION:
            break
    return out


def _title_for(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip().rstrip(".!?")
    return "Pref: " + (t if len(t) <= 60 else t[:57].rstrip() + "…")


def list_preferences(store: "Store") -> list[MemoryEntry]:
    out = [memory._read_entry(store, p) for p in store.iter_entries()]
    out = [e for e in out if e.horizon == PREFERENCE_HORIZON or e.type == PREFERENCE_TYPE]
    out.sort(key=lambda e: str(e.frontmatter.get("created") or ""), reverse=True)
    return out


def _exists(store: "Store", text: str) -> bool:
    key = _norm(text)
    return any(key and key in _norm(e.body or "") for e in list_preferences(store))


def add(store: "Store", role: "Role", text: str, *,
        search_backend: "SearchBackend | None" = None) -> "SaveResult | None":
    """Store a global preference (skips near-duplicates). Returns its SaveResult."""
    text = text.strip()
    if not text or _exists(store, text):
        return None
    return memory.save(
        store, role, type_=PREFERENCE_TYPE, title=_title_for(text), body=text,
        scope="global", horizon=PREFERENCE_HORIZON, search_backend=search_backend)


def capture_from_session(store: "Store", role: "Role", transcript_text: str, *,
                         search_backend: "SearchBackend | None" = None) -> list:
    saved = []
    for stmt in detect(transcript_text):
        res = add(store, role, stmt, search_backend=search_backend)
        if res:
            saved.append(res)
    return saved


def forget(store: "Store", identifier: str, *,
           search_backend: "SearchBackend | None" = None) -> dict:
    """Easy undo: archive a preference (recoverable) and drop it from the index."""
    try:
        ent = memory.read(store, identifier)
    except Exception:
        return {"forgot": None, "reason": "not found"}
    rel = ent.rel_path
    dest = store.root / ".archive" / "preferences" / Path(rel).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(store.resolve(rel)), str(dest))
    if search_backend is not None:
        try:
            search_backend.remove(rel)
        except Exception:
            pass
    return {"forgot": rel, "title": ent.title}


def _first_line(body: str) -> str:
    for ln in (body or "").splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", "_", "**")):
            return s
    return ""


def render_block(store: "Store") -> str:
    """The CLAUDE.md managed-block body (empty string if there are no prefs)."""
    prefs = list_preferences(store)
    if not prefs:
        return ""
    lines = ["## Your preferences — remembered by engram", ""]
    for e in prefs:
        lines.append(f"- {_first_line(e.body) or e.title}")
    lines += ["", "_engram learned these from how you work. Remove any with "
              "`/engram:status` → forget, or just delete this block._"]
    return "\n".join(lines)


def sync_claude_md(store: "Store", path: str | Path) -> bool:
    """Write/refresh engram's preference block into the CLAUDE.md at ``path``."""
    from . import claudemd
    return claudemd.update_managed_block(Path(path), render_block(store))
