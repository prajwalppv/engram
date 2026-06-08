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
    # scope = APPLICABILITY ladder: global | role | area | repo | session.
    scope: str = "global"
    # visibility = the dormant export axis (private | team), separate from scope.
    visibility: str = "private"
    repo: str | None = None
    area: str | None = None       # cross-repo domain (e.g. "python", "frontend")
    role: str | None = None       # role (or blend) at capture time
    supersedes: list[str] = Field(default_factory=list)  # titles this memory retires
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    frontmatter: dict[str, Any] = Field(default_factory=dict)


class MemoryHit(BaseModel):
    id: str | None = None
    rel_path: str
    title: str
    type: str | None = None
    score: float = 0.0
    snippet: str | None = None       # bounded preview so the agent can judge a hit
    created: str | None = None       # capture date — an age signal for staleness
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
