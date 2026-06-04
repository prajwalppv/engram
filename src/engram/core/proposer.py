"""Prompt proposers — given the current extraction prompt + failing eval cases,
propose an improved prompt. Pluggable so the optimizer is testable with a fake.
"""
from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

from . import summarizer

_META_PROMPT = """\
You are improving the EXTRACTION PROMPT used to distill developer sessions into
memory. Here is the current prompt (a Python .format template):

<<<CURRENT_PROMPT>>>
{current}
<<<END>>>

It under-performs on these cases (low expected-term coverage):
{failures}

Rewrite the prompt to better capture the expected information, while keeping it
general (do not overfit to these examples). You MUST preserve every placeholder
exactly: {{role_name}} {{role_description}} {{extraction_hint}} {{node_types}}
{{repo}} {{transcript}}. Output ONLY the new prompt text, no commentary.
"""


@runtime_checkable
class Proposer(Protocol):
    def propose(self, current_prompt: str, failures: list[dict]) -> str | None: ...


class ClaudeHeadlessProposer:
    name = "claude"

    def __init__(self, *, timeout: int = 120) -> None:
        self.timeout = timeout

    def propose(self, current_prompt: str, failures: list[dict]) -> str | None:
        meta = _META_PROMPT.format(
            current=current_prompt,
            failures=json.dumps(failures, ensure_ascii=False)[:4000],
        )
        try:
            out = summarizer.run_claude(meta, timeout=self.timeout).strip()
        except Exception:
            return None
        # strip accidental code fences
        if out.startswith("```"):
            out = out.split("\n", 1)[-1].rsplit("```", 1)[0]
        return out.strip() or None
