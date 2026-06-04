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
1. **Official Anthropic directory** — `anthropics/claude-plugins-official` is
   auto-available in every Claude Code install. Submit engram via its PR/submission
   process (reviewed for quality + security). Highest-leverage listing.
   → https://github.com/anthropics/claude-plugins-official
2. **Community directories** (fast, low-friction):
   - claudemarketplaces.com (daily-updated directory)
   - claudepluginhub.com/tools/submit-plugin
   - claudecodecommands.directory/submit
3. **awesome-claude-code** style lists — open a PR adding engram.

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
