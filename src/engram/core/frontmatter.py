"""YAML frontmatter + wikilinks. Round-trip (ruamel) so edits don't reflow files."""
from __future__ import annotations

import re
from io import StringIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

_FM_RE = re.compile(r"^(---\n.*?\n)---\n?(.*)$", re.S)
_ILLEGAL = re.compile(r'[\\/:*?"<>|]')
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def sanitize_title(title: str) -> str:
    return re.sub(r"\s+", " ", _ILLEGAL.sub("", title)).strip()


def wikilink(title: str) -> DoubleQuotedScalarString:
    return DoubleQuotedScalarString(f"[[{sanitize_title(title)}]]")


def link_target(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    m = _WIKILINK.search(value)
    return m.group(1).strip() if m else None


def split(text: str) -> tuple[str, str]:
    m = _FM_RE.match(text)
    return (m.group(1), m.group(2)) if m else ("", text)


def parse(text: str) -> tuple[CommentedMap, str]:
    fm_text, body = split(text)
    if not fm_text:
        return CommentedMap(), text
    data = _yaml().load(fm_text)
    return (data or CommentedMap()), body


def dump(meta: Any, body: str) -> str:
    if not meta:
        return body
    buf = StringIO()
    _yaml().dump(meta, buf)
    body_part = body.lstrip("\n")
    sep = "\n" if body_part else ""
    return f"---\n{buf.getvalue()}---\n{sep}{body_part}"


def iter_wikilinks(text: str):
    for m in _WIKILINK.finditer(text):
        yield m.group(1).strip(), (m.group(2).strip() if m.group(2) else None)


def build(meta: dict[str, Any], links: list[str] | None = None,
          tags: list[str] | None = None) -> CommentedMap:
    fm = CommentedMap()
    for k, v in meta.items():
        if v in (None, "", []):
            continue
        fm[k] = v
    if tags:
        seq = CommentedSeq([t for t in tags if t])
        if len(seq):
            fm["tags"] = seq
    if links:
        vals = [t for t in links if t]
        if vals:
            fm["links"] = CommentedSeq([wikilink(t) for t in vals])
    return fm
