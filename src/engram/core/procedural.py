"""Procedural memory — runbooks / workflows ("how we do X").

The "how", as opposed to episodic ("what happened") or semantic ("what's true").
Detection is deliberately HIGH-PRECISION: a procedure is only captured when the
user introduces a process (a runbook/"how we…/the steps to…/to <verb>…" lead-in)
AND lays out at least two ordered or bulleted steps. Runbooks you can't trust are
worse than none, so we err toward missing one over inventing one. Procedures are
durable (never auto-pruned) and update by append (supersede-with-history).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from . import memory

if TYPE_CHECKING:
    from ..roles.base import Role
    from .search_backends import SearchBackend

PROCEDURE_TYPE = "Procedure"
PROCEDURE_HORIZON = "procedural"
_MAX_PER_SESSION = 3
_MIN_STEPS = 2

_VERBS = (r"deploy|releas\w*|set ?up|build|run|configure|install|reproduce|"
          r"provision|publish|migrat\w*|roll ?back|test|bootstrap|onboard")
# Searched ANYWHERE in a line (a runbook intro often follows other text on the same
# line). To stay precise we additionally require the intro to end with ":" OR be
# immediately followed by step lines.
_LEADIN = re.compile(
    rf"(?i)(here'?s how (?:we|i|you)\b|how (?:we|to) (?:{_VERBS})\b|"
    rf"the (?:steps|process|runbook)\s+(?:to|for|is)\b|to (?:{_VERBS})\b|"
    rf"runbook\b|workflow\b)")
_STEP = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+\S")
_USER_TURN_RE = re.compile(r"(?:^|\n)user:\s*(.*?)(?=\n(?:assistant|user):|\Z)",
                           re.I | re.S)


def _user_turns(transcript_text: str) -> list[str]:
    turns = _USER_TURN_RE.findall(transcript_text or "")
    return turns if turns else ([transcript_text] if transcript_text else [])


def detect(transcript_text: str) -> list[dict]:
    """Return [{title, body}] for runbooks the user spelled out (lead-in + steps)."""
    out: list[dict] = []
    for turn in _user_turns(transcript_text):
        lines = turn.splitlines()
        i = 0
        while i < len(lines) and len(out) < _MAX_PER_SESSION:
            line = lines[i]
            m = _LEADIN.search(line)
            # index of the next non-blank line (the first candidate step)
            k = i + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            next_is_step = k < len(lines) and bool(_STEP.match(lines[k]))
            if not (m and (line.rstrip().endswith(":") or next_is_step)):
                i += 1
                continue
            # gather contiguous step lines (tolerating a single blank between)
            steps, j, blanks = [], k, 0
            while j < len(lines):
                ln = lines[j]
                if not ln.strip():
                    blanks += 1
                    if blanks > 1 and steps:
                        break
                    j += 1
                    continue
                if _STEP.match(ln):
                    steps.append(ln.strip())
                    blanks = 0
                    j += 1
                    continue
                break
            if len(steps) >= _MIN_STEPS:
                lead = line[m.start():].strip()  # drop any preface before the intro
                out.append({"title": _title(lead),
                            "body": lead.rstrip(":") + ":\n" + "\n".join(steps)})
                i = j
            else:
                i += 1
    return out


def _title(leadin: str) -> str:
    t = re.sub(r"(?i)^here'?s\s+", "", leadin).strip().rstrip(":").strip()
    t = re.sub(r"\s+", " ", t)
    return "Runbook: " + (t if len(t) <= 60 else t[:57].rstrip() + "…")


def add(store: "Store", role: "Role", title: str, body: str, *, repo: str | None = None,
        search_backend: "SearchBackend | None" = None):
    """Store a procedure. Auto-capture skips one whose title already exists (so we
    don't append the same runbook every session); explicit updates append history."""
    if memory.find_path(store, title) is not None:
        return None
    return memory.save(
        store, role, type_=PROCEDURE_TYPE, title=title, body=body, repo=repo,
        horizon=PROCEDURE_HORIZON, search_backend=search_backend)


def capture_from_session(store: "Store", role: "Role", transcript_text: str, *,
                         repo: str | None = None,
                         search_backend: "SearchBackend | None" = None) -> list:
    saved = []
    for proc in detect(transcript_text):
        res = add(store, role, proc["title"], proc["body"], repo=repo,
                  search_backend=search_backend)
        if res:
            saved.append(res)
    return saved


if TYPE_CHECKING:
    from .store import Store
