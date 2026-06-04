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
    scope: str = "private"        # DORMANT export seam: private | team | repo
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
