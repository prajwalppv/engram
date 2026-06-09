"""LLM-quality session summarization — the pluggable Summarizer seam.

Turns a raw session transcript into STRUCTURED, typed memory nodes (Decisions,
Gotchas, Conventions…) with suggested links — far richer than a flat blob, and
the foundation for the future graph KB + multi-hop reasoning.

Pluggable + privacy-aware:
  * ``ClaudeHeadlessSummarizer`` — best quality via ``claude -p``. The transcript
    already passed through Claude during the live session, so this is no new
    exposure; the resulting memory is written 100% locally.
  * ``HeuristicSummarizer`` — no-LLM fallback (intent + outcome).
  * (future) a local-model summarizer drops in behind the same protocol.

The extraction PROMPT is externalized + versioned (a default constant here, plus a
per-machine override the feedback→optimizer will write to
``<store>/.state/prompts/extraction.md``). That externalization is what makes the
optimizer possible: it tunes this prompt and can roll back.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from . import ingest

if TYPE_CHECKING:
    from ..config import Settings
    from ..roles.base import Role
    from .store import Store

PROMPT_VERSION = "2026-06-04.1"

DEFAULT_EXTRACTION_PROMPT = """\
You distill a developer's Claude Code session into durable MEMORY for next time.
Role context: {role_name} — {role_description}
Extraction focus: {extraction_hint}
Memory node types available for this role: {node_types}
Current project (repo): {repo}

EXISTING MEMORY already held for this project:
{existing_memory}
If a fact you extract makes one of those EXISTING memories factually OBSOLETE or
FALSE (a corrected decision, a changed convention, a reversed gotcha), put that
memory's EXACT title into the new fact's "supersedes" array. Be conservative — only
supersede a clear contradiction/correction, NEVER a memory that is merely related
or still true.

From the transcript below, extract the FEW most durable, reusable facts worth
remembering in a future session. Prefer "why we did X", non-obvious gotchas,
conventions, and key context over transient chatter. Skip anything ephemeral.

Output ONLY a JSON array (no prose) of 1-8 objects, each:
  {{"type": "<one of the node types>",
    "title": "<short, specific, unique — also the graph link target>",
    "body": "<1-5 sentences, durable and self-contained>",
    "links": ["<title of a related memory, if any>"],
    "supersedes": ["<exact title of an EXISTING memory this fact makes obsolete, if any>"],
    "tags": ["<short tag>"]}}
If nothing is worth remembering, output [].

TRANSCRIPT:
{transcript}
"""


def _load_prompt(store: "Store | None") -> str:
    """Per-machine override (optimizer-written) wins over the shipped default."""
    if store is not None:
        override = Path(store.root) / ".state" / "prompts" / "extraction.md"
        if override.exists():
            try:
                return override.read_text(encoding="utf-8")
            except Exception:
                pass
    return DEFAULT_EXTRACTION_PROMPT


def render_prompt(template: str, *, role: "Role", repo: str | None,
                  transcript: str, candidates: list[dict] | None = None,
                  max_chars: int = 24000) -> str:
    existing = "\n".join(f"- {c['title']}: {c.get('snippet', '')}"
                         for c in (candidates or [])[:8]) or "(none yet)"
    return template.format(
        role_name=role.name, role_description=role.description,
        extraction_hint=role.extraction_hint(),
        node_types=", ".join(role.node_types), repo=repo or "general",
        existing_memory=existing,
        transcript=transcript[-max_chars:],
    )


def run_claude(prompt: str, *, timeout: int = 60) -> str:
    """Invoke `claude -p` headless. Raises if unavailable, times out, or fails.

    Two safety properties matter here because this is reached from the capture
    hooks:
      * Recursion guard — the nested `claude -p` is itself a Claude Code session
        that would fire engram's Stop/SessionEnd hooks, which call this again.
        We set ENGRAM_DISABLE_HOOKS=1 in the child env so those nested hooks
        no-op (see scripts/engram-launch + hookcli.main).
      * Reaping — the child runs in its own session/process group so that on
        timeout we can kill it AND any grandchildren, never leaving a `claude`
        lingering past the hook's budget.
    """
    if shutil.which("claude") is None:
        raise RuntimeError("`claude` CLI not found")
    env = {**os.environ, "ENGRAM_DISABLE_HOOKS": "1"}
    proc = subprocess.Popen(
        ["claude", "-p", prompt, "--output-format", "text"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env, start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise RuntimeError(f"claude -p timed out after {timeout}s")
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {(err or '')[:200]}")
    return out


def extract_with_prompt(prompt_template: str, transcript: str, *, role: "Role",
                        repo: str | None, timeout: int = 120) -> list[dict]:
    """Run extraction with an EXPLICIT prompt (used by the optimizer to score
    candidate prompts without persisting them)."""
    out = run_claude(render_prompt(prompt_template, role=role, repo=repo,
                                   transcript=transcript), timeout=timeout)
    return _parse_items(out)


def _parse_items(text: str) -> list[dict]:
    s, e = text.find("["), text.rfind("]")
    if s < 0 or e < 0 or e < s:
        raise ValueError("no JSON array in summarizer output")
    items = json.loads(text[s:e + 1])
    out = []
    for it in items[:8]:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        body = str(it.get("body") or "").strip()
        if not title or not body:
            continue
        out.append({
            "type": str(it.get("type") or "Note").strip() or "Note",
            "title": title,
            "body": body,
            "links": [str(x) for x in (it.get("links") or []) if x],
            "supersedes": [str(x) for x in (it.get("supersedes") or []) if x],
            "tags": [str(x) for x in (it.get("tags") or []) if x],
        })
    return out


class HeuristicSummarizer:
    name = "heuristic"

    def summarize(self, transcript_text: str, *, role: "Role", repo: str | None,
                  candidates: list[dict] | None = None) -> list[dict]:
        events = [{"role": "user", "text": transcript_text}]
        d = ingest.distill(events, repo=repo, full_text=transcript_text)
        if not d:
            return []
        return [{"type": "SessionSummary", "title": d["title"], "body": d["body"],
                 "links": [], "tags": []}]


class ClaudeHeadlessSummarizer:
    name = "claude"

    def __init__(self, *, store: "Store | None" = None, timeout: int = 120,
                 max_chars: int = 24000) -> None:
        self.store = store
        self.timeout = timeout
        self.max_chars = max_chars

    def available(self) -> bool:
        return shutil.which("claude") is not None

    def summarize(self, transcript_text: str, *, role: "Role", repo: str | None,
                  candidates: list[dict] | None = None) -> list[dict]:
        prompt = render_prompt(_load_prompt(self.store), role=role, repo=repo,
                               transcript=transcript_text, candidates=candidates,
                               max_chars=self.max_chars)
        return _parse_items(run_claude(prompt, timeout=self.timeout))


def summarize_session(
    store: "Store", settings: "Settings", transcript_text: str, *,
    role: "Role", repo: str | None, candidates: list[dict] | None = None,
) -> list[dict]:
    """Run the configured summarizer with a safe heuristic fallback. Never raises.
    ``candidates`` = related existing memories injected into the prompt so the LLM
    can mark `supersedes` on a fact that makes one obsolete (auto-contradiction)."""
    heuristic = HeuristicSummarizer()
    if settings.summarizer == "claude":
        primary = ClaudeHeadlessSummarizer(store=store, timeout=settings.summarizer_timeout)
        try:
            items = primary.summarize(transcript_text, role=role, repo=repo,
                                      candidates=candidates)
            if items:
                return items
        except Exception:
            pass  # fall back
    try:
        return heuristic.summarize(transcript_text, role=role, repo=repo)
    except Exception:
        return []
