# engram — pitch & go-to-market

## One-liner
**engram gives Claude Code a memory — private, on your machine, and it gets sharper over time.**

## The 30-second pitch
Claude Code forgets everything when a session ends. Every morning you re-explain
your codebase, the decision you made last week, the gotcha that cost you two hours.
**engram** is a Claude Code plugin that fixes this: it quietly remembers the durable
facts from each session and recalls the relevant ones the moment you start working
again. It learns whether you're an engineer, PM, or manager and remembers
accordingly. And — uniquely — **everything stays on your laptop. No server, no
account, zero data egress.** That last part is why your security team will actually
let you install it.

## The problem (why anyone cares)
- AI coding agents are now everywhere, but they're **amnesiac** — context dies at
  `/clear` and at session end.
- Developers pay a hidden "re-explanation tax" every session.
- The obvious fix — a cloud memory service — is a **non-starter in most companies**:
  dev conversations contain proprietary code and secrets. Sending them to a SaaS is
  a security review you won't win.

## The solution
A one-plugin install that adds:
1. **Carryover** — `SessionStart` recalls memory for your repo; `SessionEnd` distills
   the session into typed, linked memory (LLM-quality extraction).
2. **Role-awareness** — SWE / PM / EM ontologies, inferred automatically from how you
   work (soft weights, overridable).
3. **A self-pruning knowledge graph** — "bonsai" pruning keeps memory razor-sharp:
   it consolidates stale notes, never deletes durable ones, and **self-tunes** how
   aggressively to prune from a measured "resurrection rate."
4. **Absolute privacy** — local markdown + a local stdio MCP server. Nothing leaves
   the machine. Provable, not promised.

## Differentiators (why not just X)
| vs. | engram's edge |
|-----|---------------|
| Cloud agent-memory SaaS | **On-device, zero egress** — passes security review. |
| A long `CLAUDE.md` | Automatic, role-aware, self-pruning — not a file you hand-maintain. |
| RAG over chat logs | A **typed knowledge graph** (multi-hop) + extraction quality that **self-improves** from feedback. |
| Delete-by-TTL memory | **Compress-don't-delete** + lifeline/deadwood preservation + self-tuned pruning. |
| Lock-in | Plain markdown + wikilinks. Own your data; leave anytime. |

## The demo that sells it (the "aha")
1. **Day 1:** you debug a Postgres timeout in the `payments` service. Session ends.
2. **Day 8, fresh session, `payments` repo:** before you type anything, Claude opens
   with *"Recalled for payments: Decision — standardized on Postgres for transactional
   integrity; Gotcha — the ORM silently swallows pool-exhaustion errors; Fix — pool
   raised to 50 + 2s statement timeout."*
3. You never re-explained a thing. **That's the moment.**

Proof points (real, this build): LLM extraction turned one debugging transcript into
**3 typed, cross-linked memory nodes**; a prune cycle raised average memory "vigor"
**1.13 → 1.63** while losing nothing (fully reversible); 35 automated tests.

## Audience messaging
- **Individual devs:** "Stop re-explaining your codebase to your AI every morning."
- **Eng managers:** "Your team's Claude gets smarter every week — and not one byte
  leaves their laptops."
- **Security / IT:** "Zero network calls for memory. Audit it: it's local files."

## Go-to-market: the install funnel (one → few clicks)
The honest reality of Claude Code distribution, easiest first:

**Tier 0 — Try it (2 commands).** Publish to a (public or internal) git marketplace:
```
/plugin marketplace add your-org/engram
/plugin install engram@engram
```
A landing page's "Install" button just copies those two lines. ~10 seconds.

**Tier 1 — Team, zero-click on a shared repo.** Commit `.claude/settings.json` with
`extraKnownMarketplaces` + `enabledPlugins`. Every teammate who clones the repo and
trusts the workspace gets engram automatically — no commands.

**Tier 2 — Org-wide, zero dev action.** IT ships **managed settings**
(`enabledPlugins`, `strictKnownMarketplaces`) via MDM (Jamf/Intune) or the Anthropic
admin console. Engram is just *there* for everyone. This is the "deploy to every
developer at the company" path.

> The capability is pushed; **data never is**. That separation is the whole sell.

Requirement to keep the funnel frictionless: `uv` on the machine (one-time, standard
for Python devs) — or ship a self-contained binary later to drop even that.

## Launch checklist
- [ ] 60-second screen-capture of the Day-1 → Day-8 demo (the "aha").
- [ ] Landing page: headline, the demo GIF, the 2-line install, a privacy one-pager.
- [ ] Public/internal plugin marketplace repo (this repo already is one).
- [ ] `.claude/settings.json` snippet for teams; managed-settings doc for IT.
- [ ] Security one-pager: "what engram does and does not send" (answer: nothing).
- [ ] A "how it works" diagram (capture → graph → recall → prune → self-improve).

## Honest caveats for the pitch
- "One-click" is really "two commands" (or zero via committed/managed settings) —
  Claude Code has no web-button install protocol today; don't overclaim.
- Summarization uses `claude -p` (already what the dev runs) — call that out so the
  privacy story stays airtight (memory is local; the model is the one they already use).
- The novel pruning/self-tuning is patent-*worthy*, not patent-*guaranteed*.
