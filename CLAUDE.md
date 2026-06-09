<!-- engram:preferences:start -->
## Your preferences — remembered by engram

- Testing is as important as development. Add/maintain tests with every change, run the FULL suite, and never regress. Doing it right matters more than speed — don't rush. For audits/reviews, be thorough and adversarial; verify, don't assume.
- I like exploring openly before converging (open thinking de-risks the real build — e.g. obsidian-mcp seeded engram). Aim for work that genuinely stands out, not just "done." Push back and offer honest tradeoffs; recommend a default; skip flattery and filler.
- Only commit or push when I explicitly ask. Branch off the default branch for changes rather than committing to main directly. End commit messages with the `Co-Authored-By: Claude` trailer. Use the gh CLI for GitHub operations (I'm authed as prajwalppv).
- macOS (Mac mini), zsh, Homebrew, Claude Code Desktop, gh CLI (authed prajwalppv). Note: `timeout` isn't available on macOS by default. Prefer dedicated tools over raw shell where one exists. I build a lot with MCP servers and Claude Code plugins.
- Check claims against official documentation before stating them as fact — especially for tools/APIs (Claude Code, plugins, marketplaces). When unsure, say so and verify rather than guessing. I notice and care about accuracy.
- Minimize wasted tokens and tool calls — don't re-read files unnecessarily, prefer targeted edits, and batch independent calls. I run dev commands through RTK (Rust Token Killer) for token savings. Be deliberate about cost-vs-thoroughness tradeoffs; "street smart" beats brute force.
- When recording decisions or notes, be verbose and faithful — preserve HOW the thinking evolved (the messy middle), not only the final state. Prefer redundancy over loss. I value the journey as much as the destination.
- For Python work, use uv (never pip) and Python 3.13. Run tests with `uv run pytest`. Manage deps in pyproject.toml. This is my standard Python toolchain.
- I strongly prefer privacy and local-first design: on-device, no telemetry, no servers/auth, no vendor lock-in. Favor pluggable seams so components are swappable. This is a core value, not a nice-to-have (it's the whole ethos behind engram).
- dont leave stray shit in github.
- Never raises.
- Never end responses by proposing to stop/pause or asking "want me to continue / is this a good place to stop?" — it's tiring filler. Keep working through the task; the user decides when to stop and what's next. Just report what was done and proceed; no stopping-coda, no permission-fishing.
- In the vault, keep MY words as mine; put Claude's research/analysis under a "Muse's add-on" section. Three personas: PJ (professional/engineer → Technology & Work), Vibestar (creative → Creative), Prajju (personal → Life). Five areas: Work, Technology, Finance, Creative, Life. Be verbose and faithful — the journey matters.  _(area)_
- My Obsidian vault is "Life-e-Jeevana" at ~/Documents/Obsidian/Life-e-Jeevana. NEVER hand-write or edit vault markdown directly — ALL writes go through .scripts/obsidian.py (new / link / enrich / daily / snapshot / find). Read .scripts/VAULT.md first; it's the source of truth for identity, areas, types, and conventions.  _(area)_
- Vault rules: relationships are QUOTED wikilinks in YAML; one note per title (dedup with `find` before creating); prefer ENRICH over thin new notes; snapshot before AND after a sync; leave a dated `Journal/_Sync Report`; unplaceable notes go to Inbox for triage. Capacities is RETIRED — never read from or write to it.  _(area)_

_engram learned these from how you work. Remove any with `/engram:status` → forget, or just delete this block._
<!-- engram:preferences:end -->
