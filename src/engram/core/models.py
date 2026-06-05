"""Data models for memory entries (graph nodes) and recall hits."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """A single memory = a graph node, persisted as a markdown note."""

    id: str
    rel_path: str
    type: str
    title: str
    body: str = ""
    # horizon = the KIND of memory: working | episodic | procedural | semantic |
    # preference. Orthogonal to `type` (which is the fine-grained category within
    # a horizon). Defaults to "semantic" for backward compatibility.
    horizon: str = "semantic"
    scope: str = "private"        # session | repo | area | role | global (export seam)
    repo: str | None = None
    role: str | None = None       # role (or blend) at capture time
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class MemoryHit(BaseModel):
    id: str | None = None
    rel_path: str
    title: str
    type: str | None = None
    score: float = 0.0
    snippet: str | None = None
    repo: str | None = None


class SaveResult(BaseModel):
    id: str
    rel_path: str
    action: str  # created | appended
    backup_rel_path: str | None = None


class LinkRef(BaseModel):
    target: str
    alias: str | None = None
    source_rel_path: str | None = None
