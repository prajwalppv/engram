# Changelog

All notable changes to **engram** are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]
- Team sharing (opt-in, redacted) over the dormant `visibility` axis.

## [0.14.0] — 2026-06-08
Make the feedback loop actually work. A maturity probe found it was **provably
dead**: over 20 memories with feedback history, `used: 0, read: 0` — the explicit
signals the loop depended on **never fire** (the agent judges from snippets, never
calls `memory_read`/`mark_used`). Research (mem0's production Ebbinghaus model;
RAG implicit-feedback literature) says to use the signal that *does* fire: recall
**access**, with recency decay.
### Changed — recall-access feedback model
- The loop now scores memories by **access frequency × recency decay**
  (`min(eff, 50) · 0.5^(days_since_last_access / 14)`), where a recall *hit* counts
  as access (it always fires) and explicit `used`/`read` weigh more (a rarer,
  higher-confidence act). Replaces the old "recalled-but-not-explicitly-used =
  noise" model, which penalized the very signal it should reward.
- Wired into ranking (`vigor.recall_boost`, saturating in [0,1) as a rich-get-richer
  guard), vigor scoring, and pruning (actively-recalled notes are now protected from
  the bonsai; only low-decayed-access ephemeral clusters are folded).
- **Proven live:** 20 memories went from a 0.0 boost (dead loop) to a real
  access-driven boost (0.24–0.50).

## [0.13.0] — 2026-06-07
Make the self-maintenance actually RUN. An architecture audit (reality vs. README)
found the machinery — bonsai pruning, the deterministic prune-param tuner — was
excellent but **inert**: it only ran when a human invoked a tool, yet the README
promised a system that "keeps itself sharp" and "self-improves over time."
### Added — automatic maintenance
- **`core/maintenance.py`** runs at **SessionEnd** (the async hook, off the critical
  path): bonsai-prune stale clusters then self-tune the prune fraction from the
  resurrection signal. Safe by construction — pruning archives (recoverable), is
  bounded by the ⅓-rule, and preserves lifelines (preferences/durable types).
  Config: `ENGRAM_AUTO_MAINTAIN` (on), `ENGRAM_AUTO_PRUNE` (on),
  `ENGRAM_MAINTAIN_INTERVAL_HOURS` (`0` = every SessionEnd; raise to throttle).
### Changed
- README is now honest about the feedback loop's two tiers: **automatic**
  (recall→ranking/vigor bias, prune-fraction self-tuning) vs. **gated/manual** (the
  LLM-cost extraction-prompt search, which only accepts a prompt that beats the
  current one on a held-out split). Removed the inaccurate "recall prompts" claim
  (recall is ranking, not a prompt).
- **Config defaults audited.** `recall_limit` was dead (never read) — now wired into
  the recall hook + `memory_recall` tool (`ENGRAM_RECALL_LIMIT` works). Removed
  `similarity_threshold` (dead + misleading — no cosine floor exists in the RRF
  ranking). Every remaining setting is consumed and has a sensible default.

## [0.12.1] — 2026-06-07
### Fixed
- **`backfill_links` was not convergent** — because `related()` excludes existing
  links, each run found *different* neighbors and kept adding up to `max_links`
  *more*, so repeated runs over-densified the graph (caught by re-running it: a
  store at 0 orphans still gained +350 links). Now it tops up to `max_links`
  **total** per node and converges (a second run adds 0). Idempotency test added.
- Added `cap_links` (and folded it into the `memory_backfill` tool) to trim
  already-over-dense nodes back to the cap. Repaired the maintainer's store
  (771 links / max 9 per node → 482 / max 4) with no loss of orphans-healed state.

## [0.12.0] — 2026-06-07
General repo attribution — the real fix for mis-scoped memories (replaces the
cwd-only heuristic and the engram-specific env pin). A memory belongs to the
project whose FILES the session edited, not the directory the session ran from.
### Added
- **`core/projects.py`** — `repo_name(path)` resolves a path to its git-root repo
  name (version-garbage rejected, `stat`-gated so git stays off the hot path);
  `dominant_repo(paths)` picks the project a session mostly edited.
- **On-the-fly attribution at capture.** `ingest.edited_paths` pulls the files
  touched by Edit/Write/MultiEdit from the transcript; capture scopes the memory to
  their dominant git repo. Precedence: explicit `ENGRAM_REPO` → edited-files repo →
  cwd. So editing project A from project B's directory now attributes to A —
  generically, no per-project config.
- `_repo_of` is now a thin wrapper over `projects.repo_name` (one source of truth).
### Fixed
- **Test isolation** — an autouse fixture strips ambient `ENGRAM_*` env so a value
  in the developer's shell/settings can't silently change test behavior (it did).

## [0.11.0] — 2026-06-07
Repo-scoping correctness + live-data healing. A deep verification pass found the
root cause of mis-scoped memories and a perf regression I'd shipped, and added the
tooling to repair an existing store.
### Fixed
- **Cross-project repo mislabeling.** Root cause: `_repo_of` derives the repo from
  the cwd, which is wrong when you work on project A from project B's directory
  (engram is edited as a plugin from another repo's session → everything captured
  as that repo). Added an explicit **`ENGRAM_REPO`** override that wins over the
  cwd — the durable prevention the v0.10.0 git-root hardening couldn't provide for
  the cross-project case.
- **Perf regression (mine, in v0.10.0).** The git-root resolution in `_repo_of`
  spawned a `git` subprocess on **every** hook — including the guard hook that
  fires on every tool call (~7.8 ms each). Added a `stat`-gated fast path: when cwd
  is a git root (the common case) its basename is used with no subprocess (0.01 ms);
  only subdirs/non-git/version-string cwds shell out.
### Added — live-data healing (`memory_backfill` + helpers)
- `consolidate.backfill_links` retroactively links related orphans;
  `prune_dangling_links` removes edges to notes that no longer exist;
  `rescope_repo` relabels cwd-mislabeled / version-garbage repos. Exposed as the
  `memory_backfill` MCP tool (dry-run by default). All tested.
- Applied to the maintainer's own store: **121 notes, orphans 60 → 0 (49% → 0%),
  91 notes re-scoped to `engram`, 6 dangling links removed, 0 empty bodies** —
  backed up first (the store isn't git-tracked).

## [0.10.0] — 2026-06-07
Foundation depth — a grounded audit of a real 121-note store found the advanced
machinery (scope ladder, graph expansion) was running on weak capture-time metadata:
**49% of nodes were orphans** and **repo labels were corrupted** (a version string
`"0.1.6"` filed as a repo; cross-project mislabeling). This enriches what capture
writes so the machinery has real signal.
### Added — auto-linking (the graph becomes load-bearing)
- At capture, a new memory is auto-linked to its **related** existing neighbors —
  the band below near-duplicate (which merge) and above unrelated, **cross-type**
  on purpose (a Decision links to the Gotcha about the same thing). Reuses the
  `find_similar` infra. Graph-expansion recall finally has edges to traverse, and
  orphan rate drops on both ends of each link. Toggle: `ENGRAM_AUTOLINK_ON_CAPTURE`.
- New eval gate `score_autolink` (link precision ≥ 0.8 — spurious links pollute the
  graph) + unit and capture-integration tests.
### Fixed — repo scoping no longer corrupted
- `_repo_of` now resolves the **git repository root** (stable across subdirs and
  plugin-cache cwds) and **rejects version-string garbage** (`0.1.6`, `v1.2.3`), so
  the scope ladder isn't poisoned by junk repo labels. Regression tests added.
  (Existing mislabeled data isn't auto-migrated — too risky to reclassify; new
  captures are clean and old labels age out.)

## [0.9.0] — 2026-06-07
Capture quality — the "noisy heart." Auto-capture restates the same fact across
sessions, so the graph slowly fills with near-duplicate nodes. It now merges them.
### Added — near-duplicate consolidation
- **Restated facts merge instead of spawning near-dups.** At capture, a new memory
  that restates an existing one (same type, high body-token overlap — or high cosine
  on the semantic backend) is appended into that node as a dated block rather than
  created as a separate near-duplicate. Exact-title repeats were already merged;
  this closes the *different-title, same-fact* gap that bloats the store over time.
- The decision is a backend-free token **Jaccard** on the substantive body (heading/
  stamp/meta stripped), so it's deterministic and behaves the same on the text
  fallback; the semantic cosine widens it to catch paraphrases. A merge only ever
  **appends** — even a wrong match never loses content (both texts stay, recoverable).
- Config: `ENGRAM_DEDUP_ON_CAPTURE` (default on), `ENGRAM_DEDUP_LEX_THRESHOLD`
  (0.7), `ENGRAM_DEDUP_SEM_THRESHOLD` (0.88).
- New eval gate `score_dedup` (precision ≥ 0.8 — a false merge smears distinct
  facts) plus unit + capture-integration tests.

## [0.8.0] — 2026-06-07
The feedback loop — engram now **learns from whether a memory helped**, which the
stateless compress-and-inject competitors don't do.
### Added — recall that learns
- **Usage feeds ranking.** `memory_recall` now boosts memories with demonstrated
  usefulness (explicitly marked used, or whose body was fetched after the compact
  index) and stops protecting recalled-but-never-acted-on noise. Small, bounded
  uplift (`W_USE`) so relevance still dominates.
- **The signal densifies itself.** Fetching a body with `memory_read` after the
  compact index is logged as an implicit usefulness vote (`read`) — no extra work
  for the agent, so the loop has real data instead of relying on rare explicit
  `mark_used`.
- **Pruning decays noise.** Vigor now rewards demonstrated usefulness and *decays*
  recalled-but-never-used memories (previously raw recall was rewarded, which
  protected noise from the bonsai). Lifelines stay fully protected.
- New eval gate `score_feedback_loop` proves the loop actually reweights (an
  acted-on memory must outrank an equally-relevant untouched one), plus unit tests
  for the usefulness math and vigor noise-decay.
### Fixed
- **Recurring junk preferences.** The detector now rejects changelog/report lines
  ("Fixed: default to …", caught by the "default to" cue) and harness caveat
  artifacts (`</local-command-caveat>`) — the two patterns that kept re-capturing
  bogus standing prefs every session. Regression tests added; the live offenders
  were forgotten.

## [0.7.0] — 2026-06-07
Competitive-analysis pass (vs claude-mem / mem0 / Zep / Letta): borrow the best
ideas, keep engram's local-first, role-aware, zero-infra ethos. All eval-gated.
### Added
- **Token-frugal recall (progressive disclosure).** `memory_recall` returns a
  compact index — each hit now carries a bounded `snippet` and a `created` date but
  not the full body. The agent judges relevance from the index and fetches full
  bodies via `memory_read` only on demand. Gate: `score_recall_compactness`.
- **Temporal / bitemporal supersede.** Superseding a memory now stamps the retired
  one with a dated back-reference (`superseded_by` / `superseded_on`) — content is
  kept (the journey) while recall surfaces the current fact. `created` on hits is an
  age signal for staleness. Gate: `score_temporal_currency`.
- **`<private>` redaction.** Content wrapped in `<private>…</private>` is stripped
  before *any* capture — never reaching the store, summarizer, index, or working
  memory (fail-safe on an unclosed tag). Toggle `ENGRAM_REDACT_PRIVATE` (default on).
  Gate: `score_redaction` (zero leakage).
- **Provenance — `memory_why` tool + `/engram:why`.** Explains a memory's origin
  (when/session/role), temporal lineage (what it retired / what retired it), and
  graph context (links/backlinks) — so you can trust or discount a recalled fact.

## [0.6.2] — 2026-06-07
### Fixed — hardening pass
- **Lock-free readers can't crash on a torn index.** `vectors.npy` and `meta.json`
  are persisted as two separate atomic replaces, so a reader in another process
  (with 0.6.1's freshness reload, more often) could load a torn pair — more vectors
  than meta — and `IndexError` past `_meta` in recall. `_load_from_disk` now clamps
  to the consistent prefix; the freshness check reloads the full state once the
  writer finishes. Regression test added.
- **Preferences mentioning an absolute path are no longer dropped.** 0.6.1's
  non-prose noise filter over-matched: a `/word/word` clause silently rejected
  valid standing prefs like "never edit /etc/hosts directly". Removed that clause
  (absolute paths aren't a non-prose tell); kept the code-fence/header/line-number/
  URL tells. Regression test added.

## [0.6.1] — 2026-06-07
### Fixed — memory quality & freshness (found in an end-to-end audit)
- **Tool output no longer pollutes the always-on layer.** In Claude Code
  transcripts, tool results / file dumps arrive as `user`-role messages; the
  preference detector was mining them, so line-numbered file content and doc text
  ("…by default…") became bogus standing preferences injected every session.
  Fix: `ingest` drops `tool_result`/`tool_use` blocks, and the detector now
  rejects non-prose (code fences, markdown headers, line-number runs, URLs,
  multi-line blobs). Added regression tests + real-world noise cases to the
  preference-detection eval gate.
- **The MCP server no longer serves a stale index.** A long-running server cached
  its startup index snapshot, so memories captured by a hook (a separate process)
  mid-session were missing from `memory_recall` until restart, and `engram_info`
  falsely reported index drift. Fix: a cheap disk-fingerprint (mtime+size) makes
  read paths reload when another process has written. Regression test added.

## [0.6.0] — 2026-06-05
### Added — proactive guardrails
- **Surface the right memory at the moment of action.** A `PreToolUse` hook
  (scoped to `Bash|Edit|Write|MultiEdit`) matches the pending action against
  guardrail-type memory (Gotcha/Constraint/Preference/Decision/…) and injects a
  concise heads-up as **non-blocking advisory context** — e.g. `git push --force`
  surfaces your "commit only when asked" rule. Lexical IDF-lite matching (instant,
  no model load), per-session dedup, fail-open, never changes the permission
  decision. Tunable: `ENGRAM_PROACTIVE` (default on), `ENGRAM_PROACTIVE_MIN_SCORE`.
### Added — eval harness + CI gating
- **CI runs the full suite on every push/PR** (`.github/workflows/ci.yml`) — unit
  tests AND eval gates. Previously nothing gated a merge.
- **Eval gates with thresholds** (a quality regression fails the build, not just a
  crash): recall@k/MRR, proactive guardrail precision/recall/**silence-rate**,
  preference-detection precision/recall, role-inference accuracy, pruning lifeline
  safety, and extraction coverage. All deterministic (text backend / stateless
  scorers → no model download). Scorers live in `core/eval.py` (reusable).
### Note
- The proactive advisory emits `additionalContext` only (no `permissionDecision`),
  so it informs without auto-approving or blocking — confirm it surfaces by
  dogfooding (trigger a known guardrail and see it referenced).

## [0.5.0] — 2026-06-05
### Added — recall quality (hybrid ranking)
- **Hybrid retrieval** (`core/ranking.py`): fuse the dense (embedding) ranking with
  a lexical (term-overlap) ranking via weighted Reciprocal Rank Fusion. Dense stays
  the primary signal; lexical *augments* it to recover the exact tokens embeddings
  are weak at (error codes, flags, IDs, paths) — it can't overturn a clear dense win.
- **Light tie-break boosts** — recency, scope precedence (more-specific wins), and
  type durability, kept small so relevance dominates.
- **Graph-neighbor expansion** — the strongest hits pull in their linked neighbors
  (discounted), surfacing related memory via the wikilink graph.
- Tunable via `ENGRAM_RECALL_HYBRID` / `ENGRAM_RECALL_GRAPH_EXPAND` (both default on).
### Measured (15 golden cases on a real store; recall@5 / MRR)
- Exact-term queries: **0.80/0.80 → 1.00/0.90**. Paraphrase: 0.90/0.783 → 0.90/0.775
  (negligible). **Overall: 0.867/0.789 → 0.933/0.817.** The eval (`memory_eval`) now
  runs through the real ranking path, so the metric reflects the product.
### Note
- This was measurement-driven: the first cut (symmetric fusion + large boosts) *hurt*
  MRR (0.783→0.65); `memory_eval` caught it and drove the dense-weighted, tiny-boost
  design above. Honest tradeoff: small paraphrase cost for a large exact-term gain.

## [0.4.0] — 2026-06-05
### Added — foundation: index integrity + a real recall metric
- **Self-healing semantic index.** On first use the backend detects **drift**
  (notes on disk missing from the index — i.e. silently un-recallable) and rebuilds
  automatically; a corrupt index is rebuilt instead of erroring. New `memory_reindex`
  tool reports what was out of sync; `engram_info` now shows `in_sync`.
- **Cross-process-safe index writes.** Index read-modify-write is now guarded by a
  file lock and always re-loads authoritative state from disk before mutating, so
  two Claude Code hosts sharing `~/.engram/store` can't clobber each other's rows
  (the cause of the earlier "26 of 33 indexed" drift).
- **Runnable recall scorecard.** `memory_eval` reports **recall@k / MRR** from
  labeled cases (feedback + new **golden** cases via `memory_add_recall_case`) PLUS
  an automatic, label-free **self-retrieval** health metric — so "self-improving"
  is measured, and regressions/drift are caught by a number.
### Fixed
- Existing stores that had drifted are repaired on next run (or via `memory_reindex`).

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
