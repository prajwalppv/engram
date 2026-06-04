# engram

A **private, on-device memory layer for Claude Code**. It lets Claude remember
across your sessions — decisions, gotchas, conventions, context — and it's
**role-aware**: what it remembers for a software engineer differs from a PM or a
manager, and it learns your role automatically from how you work.

**Absolute privacy by construction:** everything is stored locally on your own
laptop. No server, no account, no auth, no telemetry — **zero bytes leave your
machine.** (A future, opt-in, sanitized *export* could let teammates share
selected learnings; it does not exist yet and is never automatic.)

> Separate project from `obsidian-mcp`. It reuses the *patterns* proven there
> (pluggable seams, local fastembed semantic search, filesystem safety) but is
> its own clean codebase.

## How it works
- Memory is a **local knowledge graph** of markdown notes (wikilinks + backlinks),
  searched semantically (local embeddings, no cloud).
- A Claude Code **plugin** wires two hooks:
  - `SessionStart` → **recall** context relevant to your current repo/task.
  - `SessionEnd` → **save** a distilled summary (decisions, gotchas) of the session.
- A **role profile** (SWE / PM / EM / …) shapes what gets extracted and recalled.
  Your role is inferred as soft weights from your sessions and is overridable.
- A **feedback loop** (was a recalled memory used? edited? rejected?) tunes the
  role weights and the extraction/recall prompts over time.

## Status
Working MVP — single-user, local-only. Text recall by default; semantic recall opt-in.

## Requirements
- [uv](https://docs.astral.sh/uv/) (the plugin spawns the server via `uv run`)
- Python 3.13 (uv will fetch it)

## Install as a Claude Code plugin (the few-click path)
From a private/internal git repo (recommended for a team):
```
/plugin marketplace add your-org/engram
/plugin install engram@engram
```
Or from this local checkout, to try it now:
```
/plugin marketplace add /Users/vibestar/dev/engram
/plugin install engram@engram
```
Then restart Claude Code. The plugin:
- spawns the local `engram-mcp` server (stdio) over a per-user store at
  `${CLAUDE_PLUGIN_DATA}/store`;
- adds a **SessionStart** hook that recalls memory for your current repo, and a
  **SessionEnd** hook that distills the session into memory;
- adds commands: `/engram:recall`, `/engram:remember`, `/engram:status`.

**Zero-click for a shared repo:** commit a `.claude/settings.json` with
`extraKnownMarketplaces` + `enabledPlugins` so teammates get it on clone+trust.

## Semantic recall (opt-in)
Default is fast, dependency-free **text** recall. To enable local embeddings:
```bash
uv sync --extra semantic        # adds fastembed (ONNX, no PyTorch)
export ENGRAM_SEARCH_BACKEND=semantic
```
(or set it in the plugin's `.mcp.json` env). Still 100% on-device.

## Dev
```bash
uv sync --extra dev --extra semantic
uv run pytest -q
```

## Configuration (env, prefix `ENGRAM_`)
| Var | Default | Meaning |
|-----|---------|---------|
| `ENGRAM_STORE_DIR` | `~/.engram/store` (or `$CLAUDE_PLUGIN_DATA/store`) | Local memory store. |
| `ENGRAM_SEARCH_BACKEND` | `text` | `text` or `semantic`. |
| `ENGRAM_ROLE` | `auto` | Pin a role (`swe`/`pm`/`em`) or infer. |
| `ENGRAM_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model. |

## Design seams (stolen from obsidian-mcp, kept clean)
- `core/` — vendor-neutral, no MCP imports.
- `roles/` — the Profile seam applied to *people*; discoverable via the
  `engram.roles` entry-point group.
- `core/search_backends.py` — `Text` (default) + lazy `Semantic` (fastembed).
- A dormant `scope`/`export` seam so future opt-in team sharing is a flip, not a rewrite.
