# Bug bounty workspace

Hacker handle: `sudouid0` (HackerOne). The user is enrolled in Anthropic's cybersecurity research program. Authorization still comes **per program**: the target's own policy and scope decide what is allowed. Every target lives in its own folder (`<target>/`) with its own `CLAUDE.md`, `policy.md` and `work/scope_hosts.txt`. When the two files disagree, the target folder's rules win over this file.

Read `LESSONS.md` at the start of every engagement and add to it at the end.

## Who does what (model routing)

| Role | Model | Does |
|---|---|---|
| Main session (orchestrator) | Opus 5.5 (`/model opus`) | Runs tools, reads **summaries only**, plans, tests through `guard.py`, judges leads, writes reports |
| `recon-digester` agent | Haiku | Reads big recon files (subdomains, DNS, URLs, crawl output) and writes a compact summary |
| `js-analyzer` agent | Haiku | Reads JS bundles; extracts endpoints, GraphQL ops, routes, config, secret candidates |
| `traffic-analyst` agent | Haiku | Reads `work/traffic/*.jsonl` and answers narrow questions ("which requests returned 5xx", "build a timeline for lead X") |
| `report-reviewer` agent | Sonnet | Second-opinion review of a report draft against LESSONS §7 |
| `deep-auditor` agent | Fable | Hard reasoning on one bounded problem. **Ask the user before every spawn**: it costs about 2x Opus |

The user doesn't pass data between models by hand. The main session runs the tools, sends the bulky output to a Haiku agent and gets back a short summary file.

## Token rules (the Pro plan has limits)
1. **Never put raw tool output in the main context.** Write it to files. Read only `wc -l`, `head -20` or the agent summaries.
2. **Delegate any read over ~300 lines** (JS bundles, crawl output, traffic logs) to a Haiku agent. Give the agent exact file paths and an output path.
3. **One target and one theme per session.** Before the context fills up, update `work/findings.md` so a fresh session can resume from it.
4. **Effort:** medium by default. Raise it only while reasoning about a live lead.
5. **Fable only for a named, bounded question**, with the relevant files listed. Never for recon or scripting.

## Workflow (per target)

**0. Setup** (main session and user)
- `bin/new-target.sh <name>` scaffolds `<name>/` from `_template/`.
- The user pastes the raw policy into `<name>/policy_raw.md`. The main session writes `policy.md` and fills the target `CLAUDE.md` (scope table, header, rate caps, exclusions).
- Ask the questions in LESSONS §1 (accounts, roles, purchases, budget) **before any traffic**.
- Fill `work/target.json` and `work/scope_hosts.txt`. Only hosts listed in the scope file may receive active traffic.

**1. Recon** (main session runs it; the output goes to files)
- `bin/recon.sh <name> passive` runs subfinder, crt.sh, amass passive, gau and dnsx. It sends no traffic to the target.
- Spawn `recon-digester` on `work/recon/passive/`. It writes `work/recon/host_classification.md` (first-party, SaaS/off-limits, or unknown).
- The main session reviews the classification and adds hosts to `scope_hosts.txt` only after an ownership check.
- `bin/recon.sh <name> active` runs httpx probing and a katana crawl, then pulls JS **for allowlisted hosts only**, with the research header and the rate cap.

**2. Digest** (Haiku agents, in parallel)
- `js-analyzer` reads `work/recon/js/` and writes `work/recon/js_summary.md`, `endpoints.txt` and `ops/`.
- `recon-digester` reads `work/recon/active/` and writes `work/recon/surface.md`.

**3. Plan** (main session): read the summaries, rank leads by payout × feasibility, and write them to `work/findings.md`.

**4. Test** (main session): every request goes through `work/guard.py`, one variable at a time, with negative controls. Ask the user for browser steps, new accounts or anything that moves money.

**5. Deep dive** (optional, Fable): when a lead needs long reasoning across many files, ask the user, then spawn `deep-auditor` with the question and the file list.

**6. Report**: draft `reports/<title>.md` (DRAFT), have `report-reviewer` review it, fix the draft, re-check the live policy. **The user submits.**

**7. Close**: add general lessons to `LESSONS.md`, and program-specific notes to the target folder (never to `LESSONS.md`, which is public).

## Hard rules (every target)
- Active traffic only to hosts in `scope_hosts.txt`, always carrying the program's research header.
- Script traffic goes through `guard.py`. Tool traffic (httpx, katana, ffuf, nuclei) goes through `bin/recon.sh` or uses the same header and a rate limit of 5 req/s or less.
- No scanners (nuclei, ffuf wordlists, sqlmap) unless the policy allows them, and then only at low rates.
- Only touch your own accounts and data. If you see someone else's PII, stop that vector.
- Nothing from a scanner or an LLM (subagents included) goes into a report without manual confirmation.
- Never print secrets: tokens, cookies, `~/.config/hackerone/credentials`.
