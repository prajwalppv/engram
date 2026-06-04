# Publishing & distribution — engram

## ✅ Done (self-published)
engram is a public GitHub repo with a `.claude-plugin/marketplace.json`, so it is
already an installable Claude Code marketplace. Anyone can:
```
/plugin marketplace add prajwalppv/engram
/plugin install engram@engram
```
- Repo: https://github.com/prajwalppv/engram (MIT)
- Release: v0.1.0 (CI builds mac-x64 + linux-x64 binaries on the tag; mac-arm64 is committed)
- Topics set for GitHub search; README is the landing page (hero + install + demo narrative).

## 📈 Get listed for discovery (manual — needs your account)
Per the official docs there are two Anthropic marketplaces:
- **`claude-community`** (`anthropics/claude-plugins-community`) — the public community
  marketplace where third-party submissions land **after review**. This is what you
  submit to. Run `claude plugin validate .` first (CI runs the same check), then submit
  via an in-app form: **claude.ai/settings/plugins/submit** or
  **platform.claude.com/plugins/submit**. Approved plugins are pinned to a commit SHA and
  synced nightly; users install with `/plugin marketplace add anthropics/claude-plugins-community`
  → `@claude-community`.
- **`claude-plugins-official`** — curated by Anthropic **at their discretion**; no
  application process, the submission form does NOT add you here. Auto-available in every
  install. If listed, your CLI can prompt users to install (Claude Code "plugin hints").

**Independent of all that, engram is installable today** from your own repo:
`/plugin marketplace add prajwalppv/engram` → `/plugin install engram@engram`.

Extra reach: claudemarketplaces.com, claudepluginhub.com/tools/submit-plugin,
awesome-claude-code lists (open a PR).

## 📣 Launch posts (the sales surface)
Lead every post with the **privacy + "stop re-explaining your codebase"** angle.
- r/ClaudeAI and r/ClaudeCode
- X/Twitter + LinkedIn (tag the demo GIF)
- Hacker News "Show HN: engram – private, on-device memory for Claude Code"
- dev.to / a short blog cross-post

## 🎥 Assets to produce
- [ ] 60-sec demo GIF: **Day 1** debug a Postgres timeout → **Day 8** new session,
      engram recalls the decision + gotcha + fix before you type. (The "aha".)
- [ ] Privacy one-pager (for enterprise/security): "engram makes zero network calls
      for memory; audit it — it's local files." (Already true; just write it up.)
- [ ] `.claude/settings.json` snippet for teams (zero-click on clone) + managed-settings
      doc for org-wide rollout (see docs/PITCH.md).

## Positioning (one line)
**engram gives Claude Code a memory — private, on your machine, and it gets sharper over time.**
Full pitch + GTM funnel: `docs/PITCH.md`.
