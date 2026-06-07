"""Proactive guardrails — surface the right remembered gotcha/decision/preference
at the MOMENT of a risky action (a PreToolUse hook), not just at session start.

Design constraints (decided + measured):
  * Trigger is PreToolUse on mutating tools only (Bash/Edit/Write/MultiEdit).
  * Lookup is LEXICAL, not embedding — instant, no model cold-start (PreToolUse is
    synchronous and blocks the tool). Guardrails are keyword-triggered anyway
    (a flag, a path, "force", "payment").
  * Conservative + high precision: IDF-lite scoring (rare shared tokens weigh more,
    so common words don't trigger), a score threshold, guardrail-types only, and
    per-session dedup (each memory fires at most once a session).
  * Advisory ONLY: the caller injects additionalContext; it never changes the
    permission decision (no auto-approve), and fails open (no match → nothing).
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from . import scoping

if TYPE_CHECKING:
    from .store import Store

# The memory types that act as guardrails (skip episodic session noise).
GUARD_TYPES = {"Gotcha", "Constraint", "Preference", "Decision", "Convention",
               "Requirement", "Tradeoff"}

_STOP = {"the", "and", "for", "with", "this", "that", "from", "your", "into",
         "you", "use", "using", "have", "has", "are", "was", "were", "will",
         "not", "but", "all", "any", "can", "via", "per", "out", "get", "set",
         "run", "new", "old", "now", "one", "two", "let", "its", "it's", "they"}

_DIR_REL = ".state/proactive"


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z0-9_.\-/]+", (text or "").lower())
            if len(w) > 3 and w not in _STOP}


def query_from_tool(tool_name: str, tool_input: dict) -> str:
    """Distill the action a tool is about to take into a matchable string."""
    ti = tool_input or {}
    if tool_name == "Bash":
        return str(ti.get("command", ""))
    if tool_name in ("Edit", "MultiEdit"):
        parts = [str(ti.get("file_path", "")), str(ti.get("old_string", ""))]
        for e in (ti.get("edits") or []):
            parts.append(str(e.get("old_string", "")))
        return " ".join(parts)[:800]
    if tool_name == "Write":
        return (str(ti.get("file_path", "")) + " " + str(ti.get("content", "")))[:800]
    return json.dumps(ti)[:800]


def _excerpt(body: str, n: int = 150) -> str:
    for ln in (body or "").splitlines():
        s = ln.strip()
        if s and not s.startswith(("#", "_", "**")):
            return s if len(s) <= n else s[: n - 1].rstrip() + "…"
    return ""


def _shown_path(store: "Store", session: str | None):
    sid = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (session or "default"))[:128]
    return store.root / _DIR_REL / f"{sid}.json"


def _load_shown(store: "Store", session: str | None) -> set[str]:
    try:
        return set(json.loads(_shown_path(store, session).read_text(encoding="utf-8")))
    except Exception:
        return set()


def mark_shown(store: "Store", session: str | None, rel_path: str) -> None:
    p = _shown_path(store, session)
    p.parent.mkdir(parents=True, exist_ok=True)
    shown = _load_shown(store, session)
    shown.add(rel_path)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sorted(shown)), encoding="utf-8")
    tmp.replace(p)


def guardrail(store: "Store", *, tool_name: str, tool_input: dict,
              repo: str | None = None, role: str | None = None,
              area: str | None = None, session: str | None = None,
              min_score: float = 1.0) -> dict | None:
    """Return the single most-relevant guardrail memory for an action, or None.

    IDF-lite: a token shared with a memory contributes 1/df (rarer = stronger), so
    distinctive matches fire and common words don't. Title matches get a small bonus.
    """
    from . import memory

    qtoks = _tokens(query_from_tool(tool_name, tool_input))
    if not qtoks:
        return None

    shown = _load_shown(store, session)
    df: dict[str, int] = {}
    mems: list[tuple] = []
    for p in store.iter_entries():
        ent = memory._read_entry(store, p)
        if ent.type not in GUARD_TYPES and ent.horizon != "preference":
            continue
        if not scoping.applies(ent, repo=repo, role=role, area=area, session=session):
            continue
        toks = _tokens(ent.title + " " + ent.body)
        for t in toks:
            df[t] = df.get(t, 0) + 1
        mems.append((ent, toks, _tokens(ent.title)))

    best, best_score = None, 0.0
    for ent, toks, title_toks in mems:
        if ent.rel_path in shown:
            continue
        overlap = qtoks & toks
        if not overlap:
            continue
        score = sum(1.0 / df[t] for t in overlap) + 0.5 * len(qtoks & title_toks)
        if score > best_score:
            best, best_score = ent, score

    if best is not None and best_score >= min_score:
        return {"rel_path": best.rel_path, "title": best.title, "type": best.type,
                "excerpt": _excerpt(best.body), "score": round(best_score, 3)}
    return None
