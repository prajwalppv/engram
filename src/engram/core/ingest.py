"""Distill a Claude Code session transcript into a memory entry.

MVP uses a robust heuristic (no LLM call): the user's opening intent + the final
assistant conclusion + light signal extraction. Summary QUALITY is the obvious
tunable to improve later (swap in an LLM summarizer guided by the role's
extraction_hint, and let the eval/feedback loop optimize it).
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                # Tool output (file reads, command stdout, search results) arrives
                # as a tool_result block inside a USER-role message. It is NOT human
                # prose — mining it for preferences/decisions pulls in line-numbered
                # file dumps and "…by default…" doc text as bogus standing rules.
                if b.get("type") in ("tool_result", "tool_use"):
                    continue
                if b.get("type") == "text" and b.get("text"):
                    parts.append(b["text"])
                elif "content" in b and isinstance(b["content"], str):
                    parts.append(b["content"])
        return "\n".join(parts)
    return ""


def read_transcript(path: str | Path) -> list[dict]:
    """Return [{role, text}] best-effort from a transcript jsonl."""
    out: list[dict] = []
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
        role = msg.get("role") or obj.get("type")
        text = _text_of(msg.get("content"))
        if role in ("user", "assistant") and text and text.strip():
            out.append({"role": role, "text": text.strip()})
    return out


def _truncate(s: str, n: int) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def distill(events: list[dict], *, repo: str | None = None,
            full_text: str = "") -> dict | None:
    """Produce {title, body, full_text} or None if nothing substantive."""
    users = [e["text"] for e in events if e["role"] == "user"]
    assistants = [e["text"] for e in events if e["role"] == "assistant"]
    if not users and not assistants:
        return None
    intent = users[0] if users else ""
    outcome = assistants[-1] if assistants else ""
    date = datetime.date.today().isoformat()
    short = _truncate(intent or outcome, 60) or "session"
    title = f"Session {date} — {repo or 'general'}: {short}"

    body_lines = [f"_Auto-captured session summary ({repo or 'general'}, {date})._", ""]
    if intent:
        body_lines += ["## Intent", _truncate(intent, 600), ""]
    if outcome:
        body_lines += ["## Outcome", _truncate(outcome, 900), ""]
    body_lines += [f"_({len(users)} user / {len(assistants)} assistant turns.)_"]
    return {
        "title": title,
        "body": "\n".join(body_lines),
        "full_text": full_text or "\n".join(e["text"] for e in events),
    }


def distill_path(path: str | Path, *, repo: str | None = None) -> dict | None:
    events = read_transcript(path)
    return distill(events, repo=repo)


def transcript_text(path: str | Path) -> str:
    """Flatten a transcript into role-tagged text for the summarizer."""
    return "\n\n".join(f"{e['role']}: {e['text']}" for e in read_transcript(path))
