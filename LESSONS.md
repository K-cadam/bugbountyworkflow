# Bug bounty lessons learned

Reusable notes from real engagements. Add new lessons under the right heading and keep each one actionable: **what to do**, then **why** in one line.
Last updated: 2026-11-11.

---

## 1. Before sending any traffic

- **Settle the account situation first.** Ask how many verified accounts the hunter can create, and whether any can be sellers, admins or other privileged roles. Plan the whole engagement around the answer.
  *Why:* with one account, cross-account IDOR, refund self-approval and seller-against-seller tests are mostly impossible. On one marketplace target, ID and phone verification capped us at one buyer account, which closed most of the high-value lines.
- **Ask early whether real purchases are OK, and set a budget.** Money-logic bugs (checkout tampering, refunds, coupons at redemption) usually can't be proven without a real order.
  *Why:* we found a strong money-logic lead and then couldn't prove it because no purchase was allowed.
- **Ask whether the hunter owns a real seller or creator account, and what it may be used for.** A real account can serve as the *other party* (receive DMs, sell to the test account) without the agent ever having its credentials. Agree on the limits up front: no access, user acts manually, never touch its customers' data.
- **Read the raw policy, not only the summary.** Compare them for discrepancies (e.g. the research header was "required for exceptions" in the raw policy vs "every request" in the summary). When in doubt, follow the stricter rule.
- **Classify every wildcard subdomain before touching it.** Use crt.sh, resolve the CNAME/A records, and list anything pointing at SaaS (Zendesk, Squarespace, Statuspage, Salesforce Marketing Cloud, Proofpoint, Salesloft, SendGrid, Unbounce, Frontify, PactSafe) as third-party and off-limits. Cloudflare-proxied hosts with no SaaS CNAME are usually first-party. Write it all to a file.
- **For hosts not explicitly listed, decide by ownership, not by "not excluded".** Strong evidence is the app's own runtime config naming the host (e.g. `imageServiceURL`), plus the same proxy or service-mesh headers as core hosts (e.g. `x-envoy-upstream-service-time`).

## 2. Tooling and guardrails

- **Route every request through one guarded client.** It should enforce a host allowlist, add the research header, rate-limit across processes (file lock), keep a daily counter with a hard stop, follow redirects only to allowlisted hosts, and log everything. Write it before the first request. (Template: `_template/work/guard.py`.)
- **Redact secrets in log *bodies*, not just headers.** Auth endpoints can return tokens in JSON. Scrub keys matching `*token*`, `appsid`, `password`, `otp`, `code`, `secret`. Scrub by parsing each JSON log line, never with a regex over the escaped line.
- **Never print session secrets to the transcript.** To inspect cookies, print names and lengths; to compare tokens, use truncated SHA-256 hashes. When reading HAR files, extract only the fields you need.
- **Keep session cookies in a `0600` file inside a `0700` dir, and remind the user to delete their Downloads copy.** Exported cookie files and HARs are full account sessions.
- **Handle short-lived access tokens automatically.** Auto-refresh before expiry, and save rotated cookies back to the jar after every response.
- **Disable auto-refresh inside session tests.** Otherwise the wrapper's refresh hides what you're measuring.
- **Use throwaway copies of a session for destructive tests (logout, reuse), and back up the main jar first.** Expect to need fresh cookies afterwards.
- **For long waits (token expiry etc.), use a background job, not a foreground sleep.** Python buffers stdout when writing to a file, so use `python3 -u` or `flush=True` if you want to see progress.

- **Cookie-export extensions often drop the HttpOnly flag.** Never infer cookie flags from an export; read them from the server's `Set-Cookie` headers (wrapper response or HAR), names and attributes only.

## 3. Recon that paid off

- **Pull the SPA's JS bundles, including lazy chunks from the webpack runtime map.** Then load logged-in routes with the session to get route-specific chunks; logged-in pages roughly doubled the operation count.
- **Apollo/GraphQL apps often ship full query documents as compiled ASTs** (`kind:"Document"` object literals). A small JS-literal→JSON→GraphQL printer turns them into ready-to-send `.graphql` files with fragments resolved. A short Python script does it; no Node needed.
- **Check introspection and field suggestions with one request each.** If both are off, the bundles are the schema.
- **Read the SSR runtime config** (`publicRuntimeConfig`, `__NEXT_DATA__`, RSC payload). It lists API hosts, cookie names, bot-protection paths, OAuth client IDs and redirect URIs, and hints at features (`impersonatorUserID`, internal tools).
- **Grep bundles for internal routes** (`"/dashboard/..."`, `"/account/..."`) to map features, including role-gated ones.
- **Watch for false positives in greps.** Word-boundary matches like `marked` hit `markedAsRead`. Confirm with Python and real context before calling something a library or sink.

## 4. Test techniques that work with only one account

- **IDOR without a second account:** send *your own* object ID with no session, and send a well-formed but nonexistent ID. Compare the errors: "Viewer unauthorized" means an ownership check; "not found" or a crash means a lookup with no role gate. Never use real users' IDs.
- **Get the ID format right before drawing conclusions.** Base64 global IDs (`UserNode:123`) and raw numeric IDs can take different code paths. A 500 with one format and a clean error with the other is about format, not authorization.
- **Over-fetching:** request private fields (email, phone, address) on the public type. Validation errors like "Cannot query field 'email' on type 'PublicUserNode'" settle it in one request.
- **Bucket or path control in image proxies** (base64 JSON `{bucket,key,edits}`, as in AWS Serverless Image Handler): ask for a **nonexistent key** across bucket values and compare status and timing. A fast 403 means it was rejected before S3 (allowlist); a slow 404 means it reached S3. You learn the policy without reading any object.
- **Upload URL generators:** request URLs with odd extensions and traversal-style IDs, and inspect the returned key and signed headers. Nothing needs uploading.
- **Unsigned client "claims" cookies** (base64 JSON with `isEmployee` etc.): forge the flag on your own session and diff the server-rendered output. Never set impersonation to another user's ID.
- **Session revocation tests:** (a) refresh, then replay the superseded refresh token after more than 5 minutes, to rule out a grace window; (b) snapshot, log out, wait past access-token expiry, confirm the expired token fails, then refresh with the snapshot; (c) repeat after a password change. Always include a negative control showing the check can fail.
- **Stored XSS via DMs:** use inert markers (`<u>u1</u>`, `<img src=//x.invalid/h1>`, no JS) and have the counterparty report how they render. Narrow down content filters with one variable at a time (plain / tag / link).
- **Use the app's exact operation documents and enum values from the bundles.** Guessed field or enum names waste requests on validation errors. When a request uses an inline query, make sure `operationName` matches it.

## 5. OAuth and social login

- **Check the `state` parameter right away:** is it random, and is it bound to a cookie or storage? Is it ever sent to the server or compared on callback? A `state` built as base64 JSON in the browser and never checked is a login-CSRF lead, and an account-takeover lead if a logged-in victim can get the attacker's identity linked.
- **A PoC needs an attacker provider identity whose email no target account uses.** If the attacker's Google account uses the same email as the test account, the provider just logs into (and links) that account, and the test proves nothing. Settle this before asking the user to create anything.
- **Google won't accept `+` aliases for a "use existing email" account.** Use `https://accounts.google.com/SignUpWithoutGmail` with the base alias, or a throwaway Gmail, and think through eligibility first.
- **Capturing an unused callback code:** DevTools request blocking did **not** reliably stop Google's top-level redirect. Use a throwaway Chromium profile that can't resolve the target:
  `chromium --user-data-dir=<scratch>/profile --host-resolver-rules="MAP www.target.com ~NOTFOUND" "<auth URL>"`. The redirect fails and the URL with the unused code stays in the address bar.
- **Build the provider authorization URL from the app's own config** (client_id, redirect_uri, scope), so the user doesn't have to click through the target's UI.
- **Make sure a HAR is from the right browser before reading it.** Check which user ID its session belongs to (from an unsigned claims cookie, for example) and whether it covers the flow at all.

## 6. Working with the user

- **Ask before anything that moves money, touches a real (non-test) account, or costs the user effort** (new accounts, phone or ID verification, cookie re-exports). Put the cost and the expected payout side by side so they can decide.
- **Count user effort as a budget.** Each cookie re-export or new account is friction. Batch the tests that need fresh state, and run destructive session tests last.
- **Say so when a lead isn't worth the user's effort.** For example, a coupon restriction bypass that needs a coupon on their real store, for a Low payout.
- **Admit your own mistakes plainly** (guessed op names, a wrong earlier claim about token leakage) and correct them in the notes.

## 7. Reporting

- **No end-to-end PoC, no report.** Code-level evidence ("state is never checked") gets parked, not submitted.
- **Size severity honestly and name the mitigations you verified.** E.g. "password change revokes sessions" cuts a session bug down to Low; say so in the report.
- **Every report states what wasn't verified** (mobile apps, "log out all devices", grace-window upper bound).
- **Keep a timeline table with exact times and statuses from the traffic log**, with token values redacted.
- **Save drafts as `reports/<short-title>.md` marked DRAFT**, and re-check the live policy before submitting.

- **Test every "binding" cookie before claiming impact.** Fingerprint, device or CSRF companion cookies (`*-fp`, `device`, …): drop each one and replay. A fingerprint cookie that is set but not enforced can make a stolen refresh token enough on its own.
- **Get a second-opinion review of drafts (another agent or a person) before submitting.** It caught a confusing timeline row and an untested assumption in the session report.
- **In timeline tables, name each session copy and add an explicit row whenever one session is swapped for another**, so later rows don't look contradictory.

- **Point each claim at the evidence that actually proves it.** E.g. a whoami right after a token replay doesn't prove "no family revocation": access tokens may be stateless and stay valid. The proof is a later *refresh* with a refresh token issued before the replay.
- **Keep severity text and CVSS vector consistent.** Don't write "Low" next to a vector that scores 4.8 (Medium on most program tables). Give the score as computed, then argue business impact in one sentence.
- **Impact bullets only state what was tested.** Untested consequences (purchases, messaging, alerting, "users believe X") either get tested, rephrased as "has the access the account has; specific actions not tested", or moved to Limitations.
- **Separate a server-advertised value from an observed one.** "Token lifetime 1 year (`expires_in`)" isn't the same as "session survives a year". State the observed window (e.g. ~11 min) and the advertised upper bound separately.
- **Be exact about what carried the research header.** Scripted requests did; manual browser actions (login, password change, cookie export) did not. Write "all scripted requests…" and name the alias account for the browser actions.
- **Run the review loop: draft → external agent review → fixes → HackerOne AI pre-check → submit.** Two review rounds caught a confusing timeline row, an untested binding assumption, a severity/vector mismatch, overstated impact and a weak evidence pointer.
- **Once submitted, mark the local report file SUBMITTED** with the date, a placeholder for the H1 ID and triage outcome, and a note that the H1 version is authoritative.

## 8. Low-value or likely-duplicate classes (decide quickly)

- Logout not revoking sessions, or refresh-token reuse: common and often Low/informative, unless password change also fails to revoke.
- Login CSRF without a linking or impact chain: often counts as excluded "CSRF on unauthenticated forms".
- Spending-control/PIN bypass on your own account: the user is the "attacker", so low impact.
- Public client tokens in JS (Datadog `pub…`, Agora appId, OAuth client IDs): not findings.

Per-program notes (stack, verified controls, open leads, submissions) live in each target's own folder, which is never committed.
