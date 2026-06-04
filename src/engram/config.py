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

    # --- role ----------------------------------------------------------------
    # "auto" = infer from sessions (soft weights). Or pin: "swe" | "pm" | "em".
    role: str = Field(default="auto")

    # --- recall / semantic ---------------------------------------------------
    search_backend: str = Field(default="text")  # "text" | "semantic"
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
