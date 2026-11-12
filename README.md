# bounty-workflow

A Claude Code workspace for authorized bug bounty testing. One Opus session plans, tests and writes reports, and hands bulky reading (recon output, JS bundles, traffic logs) to cheaper subagents that return short summaries.

- **Guardrails first.** All scripted traffic goes through `_template/work/guard.py`, which enforces the program's host allowlist, adds the research header, rate-limits across processes, stops at a daily request cap, follows redirects only to allowed hosts and logs every request with secrets redacted.
- **A human stays in the loop.** Nothing from a scanner or an LLM goes into a report without manual confirmation, every report gets a second-opinion review, and the hunter submits it.
- **It learns.** `LESSONS.md` collects general lessons from real engagements and is updated after each one. Program-specific notes stay in each target's folder, which is never committed.

Layout: `CLAUDE.md` (workflow, model routing, hard rules) · `.claude/agents/` (subagents) · `bin/` (target scaffolding, passive and active recon) · `_template/` (per-target files).
