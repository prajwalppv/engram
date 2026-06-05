# Changelog

All notable changes to **engram** are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]
- Team sharing (opt-in, redacted) over the dormant `visibility` axis.

## [0.3.2] — 2026-06-05
### Added
- **Safe auto-updates.** Updates can now land silently without losing memory: on
  first run a new version **auto-migrates** any legacy store (the pre-0.3.1
  `$CLAUDE_PLUGIN_DATA/store`, or sibling `engram-*/store`) into `~/.engram/store`
  — copy-only, never destructive, idempotent, and never fatal to startup.
- **Team auto-update recipe** (`examples/team-settings.json`) + a README
  "Staying up to date" section: community-marketplace installs auto-update by
  default; a committed `.claude/settings.json` with `autoUpdate: true` gives a
  team zero-touch install + updates on clone + trust.

## [0.3.1] — 2026-06-05
### Fixed
- **Unified, stable store (memory no longer fragments across hosts).** The store
  defaulted to `$CLAUDE_PLUGIN_DATA/store`, which resolves to a *different*
  directory per install identity and per host (e.g. `engram-engram` in one editor
  vs `engram-inline` in Claude Desktop) — so the same user ended up with multiple
  disconnected memories and preferences seeded in one weren't visible in another.
  The store now defaults to a single per-user path, `~/.engram/store`, shared
  across every editor/host/session and surviving updates/reinstalls. `.mcp.json`
  no longer pins `ENGRAM_STORE_DIR`; override it explicitly if you want a custom
  location. Existing stores can be merged into `~/.engram/store`.

## [0.3.0] — 2026-06-05
### Added — memory horizons, Phases 2–5
- **Scope ladder + precedence (P2).** Every memory has a `scope` —
  `global → role → area → repo → session`. Recall and the always-on layer are
  applicability-filtered, so one repo/role/area's memory never leaks into another.
  Precedence is most-specific-wins; a memory can `supersede` ones it replaces
  (retiring them from recall). The dormant export concept moved to a separate
  `visibility` field (private | team), no longer conflated with scope. New
  `core/scoping.py`; `area` config; legacy notes read correctly (no migration).
- **Procedural memory (P3).** Runbooks / "how we do X" — high-precision
  auto-capture (a process lead-in + ≥2 steps, even mid-line), durable, never
  auto-pruned, **supersede-with-history** on update. New `/engram:howto` skill.
- **Working memory (P4).** Per-session "where was I" as lightweight JSON (kept out
  of the knowledge graph/index), refreshed every tick, injected at SessionStart
  only when **resuming** a recent session, TTL-bounded.
- **Per-horizon pruning (P5).** Bonsai is now horizon-aware: per-horizon recency
  half-life (working ~1d … preferences ~never), working-memory TTL cleanup wired
  into both the prune cycle and the recall lifecycle, and metrics + `engram_info`
  broken down by horizon.
### Notes
- Backward compatible: existing memories default to `semantic`/derived scope.
  +25 tests since 0.2.0 (76 total).

## [0.2.0] — 2026-06-05
### Added — memory horizons, Phase 1: preferences / always-on layer
- **Learned preferences.** engram now auto-detects standing rules you state
  ("from now on…", "always…", "I prefer…", "never…") from your own turns and
  stores them as a new **preference** horizon (global scope) — deterministic,
  offline, conservative (no LLM, low false-positive).
- **Hybrid always-on delivery.** Preferences are applied every session two ways:
  a managed block in your project's `CLAUDE.md` (persistent; only content between
  engram's markers is touched), and `SessionStart` injection (immediate).
- **Easy undo.** New tools `memory_list_preferences` and `memory_forget`; surfaced
  in `/engram:status`. Removal archives the note (recoverable) and de-indexes it.
- **Lifelines.** Preferences are never auto-pruned.
- **Model:** new `horizon` field (working | episodic | procedural | semantic |
  preference), orthogonal to `type`; `memory_save` accepts `horizon`/`scope`.
  Fully backward compatible — existing notes default to `semantic`.
- New config: `ENGRAM_DETECT_PREFERENCES`, `ENGRAM_MANAGE_CLAUDE_MD`,
  `ENGRAM_CLAUDE_MD_PATH`.

## [0.1.8] — 2026-06-04
### Fixed (pre-submission robustness audit)
- **Recursion guard (P0).** The capture hooks run the `claude` summarizer; a
  headless `claude -p` is itself a Claude Code session that would fire engram's
  hooks again. We now set `ENGRAM_DISABLE_HOOKS=1` in the child env and bail
  immediately in both the launcher and `hookcli` when it's set — breaking any
  summarizer→hook→summarizer cascade.
- **Subprocess reaping + timeout (P0).** `claude -p` now runs in its own process
  group and is killed (group-wide) on timeout; `summarizer_timeout` lowered to
  60s (under the 120s hook budget) so the harness never kills the hook mid-call.
- **Async capture (P0).** `PreCompact` and `SessionEnd` hooks are now `async` (as
  `Stop` already was) so capture never blocks compaction or session teardown.
- **Atomic memory writes (P1).** Memory notes are written via temp file + rename,
  so a hook killed mid-write can't leave a truncated/corrupt node.
- **SessionStart recall is fully fail-safe (P1).** The entire `recall` path is
  guarded so a failure emits no stdout (protecting the hook's JSON contract)
  and exits 0.
### Notes
- No behavior change on the happy path; this hardens the failure modes.

## [0.1.7] — 2026-06-04
### Added
- `CHANGELOG.md` (this file).
- `author.email` in `plugin.json` and the marketplace entry.
- README **Demo** section + a reproducible [VHS](https://github.com/charmbracelet/vhs)
  tape (`demo/engram.tape`) to record the recall/capture loop as a GIF.
### Notes
- Pre-submission polish for the community plugin marketplace. No behavior change.

## [0.1.6] — 2026-06-04
### Changed
- Raised the default `ENGRAM_CAPTURE_EVERY_TURNS` from `3` to `13`, so the
  end-of-turn `Stop` capture runs the summarizer less often mid-session (lower
  overhead). Durability is unchanged — `PreCompact` and `SessionEnd` still flush
  the remaining unprocessed turns.

## [0.1.5] — 2026-06-04
### Added
- **Multi-trigger incremental capture.** Memory is no longer captured only at
  session end:
  - `Stop` — throttled, async capture at the end of a turn (every N new turns).
  - `PreCompact` — a forced flush right before context is compacted, so
    auto-compaction no longer silently loses information.
  - `SessionEnd` — retained as a final backstop.
- **Per-session high-water mark** so each capture processes only new transcript
  messages (no reprocessing, safe on resume, idempotent with content-hash +
  semantic dedup).
- **Architecture diagram** (`docs/ARCHITECTURE.md`) and a README overview.

## [0.1.4] — 2026-06-04
### Fixed
- CI release pipeline: dropped the deprecated `macos-13` (Intel) runner that
  queued indefinitely and blocked the binary-commit job; fixed artifact
  upload/collect so platform binaries actually land in `bin/`.

## [0.1.3] — 2026-06-04
### Changed
- **Semantic recall is now the default** search backend (local embeddings via
  fastembed/ONNX — no PyTorch, no cloud). Dependencies come from PyPI and the
  embedding model from Hugging Face, pulled once on first use (~160 MB) and then
  fully offline. Automatic fallback to text recall when embeddings aren't
  available.

## [0.1.2] — 2026-06-04
### Changed
- Documentation cleanup: removed internal/project references from the README and
  docstrings.

## [0.1.1] — 2026-06-04
### Changed
- Conformed to the official Claude Code plugin docs: `skills/` instead of
  `commands/`, richer `plugin.json` / `marketplace.json` manifests; `claude
  plugin validate` passes clean.

## [0.1.0] — 2026-06-04
### Added
- Initial public release: a private, on-device, role-aware memory layer for
  Claude Code — persistent across sessions, knowledge-graph structured
  (wikilinked markdown), self-pruning (bonsai-inspired), and self-improving from
  feedback. MIT licensed. Cross-platform self-contained binaries built in CI as
  a no-setup fallback.

[Unreleased]: https://github.com/prajwalppv/engram/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/prajwalppv/engram/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/prajwalppv/engram/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/prajwalppv/engram/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/prajwalppv/engram/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/prajwalppv/engram/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/prajwalppv/engram/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/prajwalppv/engram/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/prajwalppv/engram/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/prajwalppv/engram/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/prajwalppv/engram/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/prajwalppv/engram/releases/tag/v0.1.0
