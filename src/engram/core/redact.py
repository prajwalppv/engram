"""Redact content the user explicitly marked as not-for-memory.

Anything wrapped in ``<private>…</private>`` (case-insensitive, across lines) is
stripped BEFORE capture — so secrets / PII / throwaway scratch never reach the
store, the summarizer, the embedding index, or working memory. A privacy primitive
for engram's whole reason to exist: on-device *and* selective.

Fail-safe: an UNCLOSED ``<private>`` (the user forgot the close tag) redacts to
end-of-text rather than leaking the tail.
"""
from __future__ import annotations

import re

_PLACEHOLDER = "[redacted]"
# Non-greedy, dotall, case-insensitive: each closed span individually.
_PRIVATE = re.compile(r"<private>.*?</private>", re.I | re.S)
# A dangling opener with no matching close → redact through the end.
_OPEN = re.compile(r"<private>.*\Z", re.I | re.S)


def has_private(text: str | None) -> bool:
    return bool(text) and "<private>" in text.lower()


def strip_private(text: str | None) -> str:
    """Remove every ``<private>…</private>`` span (and a dangling opener)."""
    if not has_private(text):
        return text or ""
    out = _PRIVATE.sub(f" {_PLACEHOLDER} ", text)
    out = _OPEN.sub(f" {_PLACEHOLDER} ", out)
    return out
