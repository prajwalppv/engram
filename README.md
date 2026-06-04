# 🧠 engram — give Claude Code a memory

**Claude Code forgets everything when a session ends. engram fixes that — privately, on your machine, and it gets sharper over time.**

engram is a Claude Code **plugin** that remembers the durable facts from each session
(decisions, gotchas, conventions) and recalls the relevant ones the moment you start
working again. It's **role-aware** (it remembers differently for an engineer vs a PM
vs a manager, learned automatically), it keeps itself sharp with **bonsai-style
pruning**, and it **self-improves** from your feedback.

**🔒 Absolute privacy by construction:** everything is stored locally on your own
laptop. No server, no account, no auth, no telemetry — **zero bytes leave your machine.**

## Install (Claude Code)
```
/plugin marketplace add prajwalppv/engram
/plugin install engram@engram
```
Restart Claude Code. That's it — on a platform with a prebuilt binary you need **nothing
else installed** (no Python, no uv). Then just work: engram recalls your repo's memory at
session start and captures the session at the end. Commands: `/engram:recall`,
`/engram:remember`, `/engram:status`, `/engram:prune`, `/engram:optimize`.

> A future, opt-in, sanitized *export* could let teammates share selected learnings; it
> does not exist yet and is never automatic.

## How it works
- Memory is a **local knowledge graph** of markdown notes (wikilinks + backlinks),
  searched semantically (local embeddings, no cloud).
- A Claude Code **plugin** captures and recalls memory across the session lifecycle —
  **not just at the end**, so nothing is lost to compaction or an abrupt terminal close:
  - `SessionStart` → **recall** context relevant to your current repo/task (also after a compaction).
  - `Stop` (end of every turn) → **incremental capture**, throttled so it only distills once a few new turns accumulate.
  - `PreCompact` → **flush before compaction** — captures detail right before Claude summarizes it away.
  - `SessionEnd` → **final flush** of anything remaining.
- Every capture is **incremental and idempotent**: a per-session high-water mark means
  each trigger folds only the *new* delta into memory, and content-hash + semantic dedup
  prevent duplicates. See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.
- A **role profile** (SWE / PM / EM / …) shapes what gets extracted and recalled.
  Your role is inferred as soft weights from your sessions and is overridable.
- A **feedback loop** (was a recalled memory used? edited? rejected?) tunes the
  role weights and the extraction/recall prompts over time.

## Architecture
Memory is captured at multiple points in the session lifecycle and recalled at the
start of the next one — all on-device. ([full diagrams + component view →](docs/ARCHITECTURE.md))

```mermaid
flowchart TD
    subgraph CC["Claude Code session"]
        S0(["SessionStart"])
        STOP(["Stop · every turn"])
        PC(["PreCompact"])
        SE(["SessionEnd"])
    end
    S0 -->|recall| R[["recall: memory for this repo"]]
    R -->|additionalContext| CC
    STOP -->|"capture (throttled)"| CAP
    PC -->|"capture (forced flush)"| CAP
    SE -->|"capture (forced flush)"| CAP
    CAP["capture_delta()<br/>new events since high-water mark"]
    CAP --> HWM[("high-water mark<br/>.state/sessions")]
    CAP --> SUM["summarize → typed, linked nodes"]
    SUM --> STORE[("local store<br/>markdown graph + index")]
    STORE -.->|next session| R

    classDef hook fill:#1f2937,stroke:#60a5fa,color:#e5e7eb;
    classDef work fill:#0f172a,stroke:#34d399,color:#e5e7eb;
    classDef data fill:#111827,stroke:#fbbf24,color:#e5e7eb;
    class S0,STOP,PC,SE hook;
    class R,CAP,SUM work;
    class HWM,STORE data;
```

## Status
Working MVP — single-user, local-only. **Semantic recall on by default** (local
embeddings); automatic text fallback when embeddings aren't available. **Durable
multi-trigger capture** (Stop / PreCompact / SessionEnd) so memory survives
compaction and abrupt exits.

## Requirements
- [uv](https://docs.astral.sh/uv/) for the full **semantic** experience. On first
  run, the plugin pulls fastembed + a small embedding model (~160 MB once, from
  PyPI + HuggingFace), then runs fully offline. Nothing is committed to the repo.
- **No uv? Still works.** The plugin falls back to a committed ~16 MB self-contained
  binary that gives fast **text** recall with zero setup.

Either way, everything stays on your machine.

### Self-contained binary (the no-uv text fallback)
The plugin runs via `scripts/engram-launch`, which prefers `uv` (semantic) and
falls back to the bundled binary (text). Build the binary per platform (ideally CI):
```bash
bash scripts/build_binary.sh      # → bin/<os>_<arch>/engram (~16 MB, PyInstaller)
```
It's lean by design — the heavy embedding deps are pulled on demand via uv, never
bundled or committed.

## Install as a Claude Code plugin (the few-click path)
From a private/internal git repo (recommended for a team):
```
/plugin marketplace add prajwalppv/engram
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
- adds lifecycle hooks that recall memory at **SessionStart** and capture it
  incrementally at **Stop** / **PreCompact** / **SessionEnd** (durable across
  compaction and abrupt exits);
- adds commands: `/engram:recall`, `/engram:remember`, `/engram:status`.

**Zero-click for a shared repo:** commit a `.claude/settings.json` with
`extraKnownMarketplaces` + `enabledPlugins` so teammates get it on clone+trust.

## Semantic recall (default)
Semantic recall is **on by default** — local embeddings via fastembed (ONNX, no
PyTorch). The deps come from PyPI and the model from HuggingFace, **pulled once on
first use** (~160 MB), then it's fully offline. No cloud, no API. To force plain
keyword recall instead, set `ENGRAM_SEARCH_BACKEND=text`.

## Dev
```bash
uv sync --extra dev
uv run pytest -q
```

## Configuration (env, prefix `ENGRAM_`)
| Var | Default | Meaning |
|-----|---------|---------|
| `ENGRAM_STORE_DIR` | `~/.engram/store` (or `$CLAUDE_PLUGIN_DATA/store`) | Local memory store. |
| `ENGRAM_SEARCH_BACKEND` | `semantic` | `semantic` (local embeddings) or `text`. |
| `ENGRAM_ROLE` | `auto` | Pin a role (`swe`/`pm`/`em`) or infer. |
| `ENGRAM_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model. |
| `ENGRAM_CAPTURE_ON_STOP` | `true` | Incremental end-of-turn (`Stop`) capture. Set `false` to capture only at PreCompact/SessionEnd. |
| `ENGRAM_CAPTURE_EVERY_TURNS` | `13` | Min new user turns before a `Stop` capture fires (lower = more durable + more frequent distillation; higher = less overhead). PreCompact/SessionEnd flush the remainder regardless. |

## Design seams
- `core/` — vendor-neutral, no MCP imports.
- `roles/` — the Profile seam applied to *people*; discoverable via the
  `engram.roles` entry-point group.
- `core/search_backends.py` — `Text` (default) + lazy `Semantic` (fastembed).
- A dormant `scope`/`export` seam so future opt-in team sharing is a flip, not a rewrite.
