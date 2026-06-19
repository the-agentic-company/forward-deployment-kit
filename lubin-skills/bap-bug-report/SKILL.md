---
name: bap-bug-report
description: |
  Deeply analyse a bug or feature request in the Bap repo
  (the-agentic-company/bap), produce a factual writeup, and autonomously
  post it to Slack in #bugs or #feature-request (workspace: The Agentic
  Company) with @Baptiste pinged at the start. Use when the user describes
  a bug or feature gap in Bap / Heybap (chat, coworker output, attachments,
  MCP, skills UI, run flow…) and wants the report sent to the CTO without
  manual copy-paste. Triggers: "Bug: …", "Feature: …", "explain this to
  Baptiste", "send a short note to the CTO about …", "audit the bug …".
---

# Bap bug / feature report to CTO

Goal: the user gives a short one-line bug or feature description; you investigate the Bap codebase in depth; you autonomously post one synthetic message to Slack (workspace **The Agentic Company**), pinging **Baptiste (CTO)** at the start, in `#bugs` or `#feature-request` depending on the nature of the input.

## Repo & context (always)

- GitHub: https://github.com/the-agentic-company/bap
- Owner: `the-agentic-company` (Bap is the platform, Heybap is the product brand).
- CTO: Baptiste. The user (Lubin) is Chief of Staff at Hyperstack/CmdClaw and uses Bap heavily as a power user.
- Codebase layout (monorepo):
  - `apps/web/` — Next.js frontend (chat, coworker UIs, prompt bar, attachments, settings).
  - `packages/core/` — server services (sandbox, file service, orpc routers like `generation.startGeneration`, `coworker.trigger`).
  - Two recurring UI surfaces matter and are often asymmetric:
    1. **Chat panel** (`apps/web/src/components/chat/…`) — the main conversation UI.
    2. **Coworker run output** (`apps/web/src/routes/agents/-components/coworker-info-panels.tsx`) and the prototype variant `apps/web/src/routes/prototype/coworker/info/-components/coworker-info-prototype.tsx`.
  - MIME validation for **documents** (skill / coworker uploads) lives in `apps/web/src/server/storage/validation.ts` (separate from chat attachments).
  - Sandbox file limit: `packages/core/src/server/services/sandbox-file-service.ts` (already 50 MB at last check, while the client caps at 10 MB → a frequent mismatch source).

## Step 1 — get a fresh local clone

Check first whether a recent clone already exists under `/tmp/` (previous sessions often leave one):

```bash
ls -d /tmp/bap-* 2>/dev/null
```

Then either `cd` into it and `git pull`, or clone fresh:

```bash
gh repo clone the-agentic-company/bap /tmp/bap-bug-$(date +%s)
```

Never investigate from the GitHub web UI alone for anything non-trivial. The local clone is needed for multi-file grep and asymmetry checks.

## Step 2 — investigate in depth (use the Agent tool)

Delegate the investigation to a subagent (`general-purpose` or `Explore`) with a self-contained briefing that includes:

- The exact bug / feature description from the user.
- The repo path on disk.
- The known monorepo layout above.
- An instruction to check **both** the chat surface and the coworker surface when the issue could exist in either (asymmetry between the two is a common Bap pattern — see the postMessage / agentic-app-prompt bug and the attachment size bug as historical examples).
- A requirement that every claim in the report carries a `file:line` reference.

Cover these axes systematically before concluding:

1. **Frontend filters / validation** — `accept=` attributes, MIME whitelists, size caps, silent `.filter(...)` drops, dropzone configs.
2. **Client → server boundary** — orpc routers (`generation.startGeneration`, `coworker.trigger`, `persistMessageAttachments`, `stageRuntimePromptAttachments`), payload serialization (`dataUrl` base64 in the JSON body is a known cost center).
3. **Server services** — `packages/core/src/server/services/*.ts`, sandbox limits, storage validation.
4. **Surface asymmetry** — same feature wired in chat but missing in coworker output (or vice versa).
5. **UX feedback** — many "bugs" are silent drops with no toast/error: the code works but the user sees nothing happen. Flag these explicitly.
6. **Hosting / runtime assumptions** — **DO NOT assume Vercel, S3, Cloudflare, etc.** Bap is **not** on Vercel. Stay grounded in code-level facts. If you need to mention a body-limit / runtime limit, frame it as "the JSON-base64 body path will hit *any* host body limit", not "Vercel functions cap at 4.5 MB".

## Step 3 — design the fix, honestly

For every diagnosis, produce:

- **A simple fix** (the 10-minute unblock). Often: raise a constant, replace a silent `.filter()` with a toast, add a missing listener, copy a hook from the working surface to the broken one.
- **A durable fix** (the structural one). Describe the **property** the fix should have, not a specific transport / vendor.
  - Wrong framing: "switch to S3 presigned PUT" → Baptiste rightly pushed back on this.
  - Right framing: "get binary attachments out of the JSON-orpc body, with whatever upload transport already fits your stack".
- **All reasonable alternatives** you considered, with the trade-off in one line each. Do not bury them in prose: list them.
- **Implications**: what else gets touched (other surfaces using the same hook/constant/route), whether there is a migration, whether existing data is affected.

## Step 4 — write the message to Baptiste

**Style rules — strict.** These come from the user's explicit feedback:

- English, sober, professional, no childish tone.
- **NO em-dashes (— / –) ever.** Use commas, colons, parentheses, or split sentences.
- Factual only. No business implications, no "this will unblock users", no marketing.
- No fluff intros ("here is", "I analysed", "in summary"). Get to the bug.
- Every technical claim has a `file:line` reference, clickable for Baptiste.
- Short. Aim for ~150-300 words total. If longer, you are padding.
- No prescriptive infra (no Vercel, no S3, no specific vendor) unless the repo itself uses it.
- Be honest about uncertainty. If you are not sure, say "to confirm on the infra side" rather than invent.

**Required structure** (use these exact section names, in this order):

```
**Bug: <one-line restatement>**

**User-facing symptom**: <what the user sees, 1-2 lines>

**Root cause**: <root cause grounded in file:line refs; what code does what wrong>

**Compounding factor (if applicable)**: <secondary contributor, only if real and code-grounded>

**Fix paths**

1. **Quick fix**: <concrete, 5-15 min change, with files to touch>
2. **Durable fix**: <property the fix should have, not a vendor prescription>
3. **Alternatives considered** (optional, if relevant): <2-4 bullets, 1 line each, with why each was not retained>

**Scope**: <which surfaces / files are affected; mention asymmetries explicitly>
```

Sections can be omitted if genuinely empty (e.g. no compounding factor, no alternatives worth listing). Never fabricate a section to fill space.

## Step 5 — dedup check (mandatory, before posting)

Before sending anything, search Slack to make sure the same bug or feature has not already been reported. Posting a duplicate is worse than no message at all.

**Where to search**:

- The target channel only (`#bugs` for bugs, `#feature-request` for features). Cross-channel noise is not relevant.
- Time window: the last 60 days is usually enough. Older than that, the report is stale anyway and a fresh one is fine.

**How to search**:

Use `mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_search_public` (or `slack_search_public_and_private` if the channel is private) with a query built from the most distinctive tokens of the bug. Pick tokens that are unlikely to collide with unrelated reports. In order of preference:

1. A specific file path or symbol from the diagnosis (e.g. `prompt-bar.tsx`, `MAX_FILE_SIZE`, `agentic-app-prompt`, `coworker-info-panels`).
2. A unique noun phrase from the symptom (e.g. `m4a attachment`, `audio attachment`, `button postMessage`).
3. The Slack channel filter syntax: `in:#bugs <terms>` or `in:#feature-request <terms>`.

Run 2 to 3 short queries with different angles, not one long query. Slack search is keyword-based, not semantic.

**Decide**:

- **No match** → proceed to Step 6 (post).
- **Likely match** (same file paths or same symptom, posted by anyone, not just the user) → **do not post**. Return to the user:
  1. A one-line note: `Already reported: <permalink to the existing Slack message> by <author> on <date>.`
  2. The draft message that would have been posted, so the user can decide to reply in-thread or force a repost.
  3. Do not call `slack_send_message` at all in this branch.
- **Borderline** (one shared keyword but different root cause) → proceed to post, but mention in your return-to-user note that a possibly-related thread exists, with the permalink.

Never silently skip the post without telling the user. Never post when a clear duplicate exists.

## Step 6 — auto-post to Slack (mandatory, autonomous)

The skill posts the message itself, autonomously, to the **The Agentic Company** Slack workspace. No draft, no confirmation step. The user explicitly asked for this.

**Routing — pick the channel from the trigger**:

- Bug (triggers: "Bug:", "audit the bug", "the bug is", anything describing broken behaviour) → `#bugs`, channel id `C0AA9RCTCHL`.
- Feature request / gap (triggers: "Feature:", "feature request", "it would be great if", "missing feature", anything describing absent or desired capability) → `#feature-request`, channel id `C0A9ZD8AL3S`.

If the trigger is genuinely ambiguous, default to `#bugs`. Do not ask the user.

**Mention Baptiste at the very start of the message**:

- Baptiste's Slack user id: `U0A87JNV8QP`.
- Prepend `<@U0A87JNV8QP> ` (with a trailing space) to the message body. This renders as a real ping in Slack, not a plain `@Baptiste` string.

**Send via the Slack MCP**:

```
mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_send_message(
  channel_id = "<bug or feature-request id>",
  message = "<@U0A87JNV8QP> " + <message body from Step 4>
)
```

Use `slack_send_message`, **never** `slack_send_message_draft` — the user wants autonomous posting.

**Resolving IDs if they ever drift**: re-run `slack_search_users` for "Baptiste" and `slack_search_channels` for "bug" / "feature-request" inside the workspace **The Agentic Company**. The current logged-in account is the user's own. If multiple bug channels appear, prefer the canonical `#bugs` (general), not product-specific variants like `#bugs-hermes`.

## Step 7 — return to the user

Return to the user, in this exact shape:

1. The full message that was posted (so they can audit what went out).
2. One line below it with the Slack permalink returned by `slack_send_message`, prefixed with `Posted: `.

Do not wrap with commentary, headers, or summaries. Two blocks, that is all.

If during the investigation you find a second, related issue worth mentioning (e.g. same root cause hits another surface), include it in the same message under **Scope**. Do not open a second Slack message.

## Historical bugs to avoid re-hallucinating

These were diagnosed correctly in past sessions; use them as anchors / sanity checks if the current bug sounds similar:

- **`bap:agentic-app-prompt` button works in chat, not in coworker output** → asymmetry. Listener exists at `apps/web/src/components/chat/agentic-app-panel.tsx:110-183`; missing in `apps/web/src/routes/agents/-components/coworker-info-panels.tsx` (AgenticAppFrame L283, iframes L384 + L404) and in the prototype variant. Fix: extract the listener into a shared hook, wire it on both surfaces, force `onSendPrompt` to post into `run.conversationId`.
- **Attaching m4a / mp3 in run chat does nothing** → not a MIME filter. Silent 10 MB cap: `apps/web/src/components/prompt-bar.tsx:56` (`MAX_FILE_SIZE`) + L319 (`.filter(...)` without toast). Same pattern duplicated in `chat-input.tsx:17/123` and `inbox-create-input.tsx:24/81`. Compounding factor: attachments are base64-encoded in the orpc body (+33%). The sandbox already supports 50 MB (`packages/core/src/server/services/sandbox-file-service.ts:25`). Durable fix: get the binary out of the JSON body, transport agnostic.

## What NOT to do

- Do not write a long preamble or business framing.
- Do not suggest specific cloud vendors or transports unless the repo already uses them.
- Do not claim something is broken without a `file:line` reference proving it.
- Do not bundle the diagnostic narrative with the CTO message. The user wants the **message only**, not the working-out.
- Do not use em-dashes anywhere in the output.
