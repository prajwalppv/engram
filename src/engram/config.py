"""Runtime configuration, environment-driven. All paths are local to this machine.

There is intentionally NO network/server/auth config — engram is on-device only.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_store() -> Path:
    # Prefer the Claude Code plugin data dir (survives plugin updates) when run
    # as a plugin; otherwise a per-user dir. Always local.
    pd = os.environ.get("CLAUDE_PLUGIN_DATA")
    return (Path(pd) / "store") if pd else (Path.home() / ".engram" / "store")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENGRAM_", extra="ignore")

    # --- local store ---------------------------------------------------------
    store_dir: Path = Field(default_factory=_default_store)
    index_dir: Path | None = Field(default=None)  # defaults to <store_dir>/.index

    # --- role / area ---------------------------------------------------------
    # "auto" = infer from sessions (soft weights). Or pin: "swe" | "pm" | "em".
    role: str = Field(default="auto")
    # Optional cross-repo domain for the scope ladder (e.g. "python", "frontend").
    # Memories scoped to a different area won't surface here when this is set.
    area: str | None = Field(default=None)

    # --- pruning (bonsai) ----------------------------------------------------
    prune_min_age_days: int = Field(default=14)   # only fold sessions older than this
    prune_max_fraction: float = Field(default=0.25)  # <= this share pruned per cycle (⅓-rule)
    prune_min_cluster: int = Field(default=2)     # min stale sessions per repo to consolidate

    # --- incremental capture (multi-trigger) ---------------------------------
    # Capture is incremental + idempotent (a per-session high-water mark): it
    # fires at end-of-turn (Stop), before context compaction (PreCompact), and at
    # session end (SessionEnd), each folding only the new delta into memory.
    capture_on_stop: bool = Field(default=True)        # end-of-turn incremental capture
    capture_every_turns: int = Field(default=13)       # min new user turns before a Stop capture

    # --- summarization -------------------------------------------------------
    # "claude" = LLM extraction via `claude -p` (best quality, falls back to
    # heuristic if unavailable); "heuristic" = no-LLM distillation.
    # --- preferences / always-on layer (Phase 1 horizons) -------------------
    # Auto-detect standing preferences ("always use uv", "I prefer terse…") from
    # sessions and deliver them every session via the hybrid always-on layer.
    detect_preferences: bool = Field(default=True)
    manage_claude_md: bool = Field(default=True)     # write the managed CLAUDE.md block
    claude_md_path: Path | None = Field(default=None)  # override; else <cwd>/CLAUDE.md

    summarizer: str = Field(default="claude")
    # Kept comfortably under the hook timeout (120s) so the summarizer subprocess
    # is reaped by us, never by the harness killing the hook mid-call.
    summarizer_timeout: int = Field(default=60)

    # --- recall / semantic ---------------------------------------------------
    # Semantic (local embeddings) is the DEFAULT — highest-quality recall. Falls
    # back to "text" automatically if fastembed/numpy aren't importable.
    search_backend: str = Field(default="semantic")  # "semantic" | "text"
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")
    similarity_threshold: float = Field(default=0.55)  # recall floor (graph recall)
    recall_limit: int = Field(default=8)

    # --- transport (local only) ---------------------------------------------
    transport: str = Field(default="stdio")  # "stdio" (default) | "http"
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8799)

    def resolved_store(self) -> Path:
        return self.store_dir.expanduser().resolve()

    def resolved_index_dir(self) -> Path:
        if self.index_dir:
            return self.index_dir.expanduser().resolve()
        return self.resolved_store() / ".index"


def load_settings() -> Settings:
    return Settings()
