# Changelog

All notable changes to **engram** are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]
- Demo recording (`demo/engram.tape`) → `docs/demo.gif` in the README.

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

[Unreleased]: https://github.com/prajwalppv/engram/compare/v0.1.8...HEAD
[0.1.8]: https://github.com/prajwalppv/engram/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/prajwalppv/engram/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/prajwalppv/engram/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/prajwalppv/engram/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/prajwalppv/engram/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/prajwalppv/engram/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/prajwalppv/engram/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/prajwalppv/engram/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/prajwalppv/engram/releases/tag/v0.1.0
