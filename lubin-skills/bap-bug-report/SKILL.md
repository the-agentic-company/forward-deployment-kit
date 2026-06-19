---
name: bap-bug-report
description: |
  Deeply analyse a bug or feature request in the Bap repo
  (the-agentic-company/bap) and produce a factual writeup ready to forward
  to the CTO (Baptiste). Use when the user describes a bug or feature gap in
  Bap / Heybap (chat, coworker output, attachments, MCP, skills UI, run
  flow…) and wants a short, accurate, CTO-ready report with file:line
  references and fix paths. Triggers: "Bug: …", "Feature: …", "explain this
  to Baptiste", "write a short note to the CTO about …", "audit the bug …".
---

# Bap bug / feature report to CTO

Goal: the user gives a short one-line bug or feature description; you investigate the Bap codebase in depth; you return one synthetic message ready to forward to **Baptiste (CTO of the-agentic-company / Bap / Heybap)**.

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

## Step 5 — return the message

Return **only** the message text, ready to copy-paste to Baptiste. Do not wrap it in commentary like "here is the message" or "hope this helps". The user will paste it as-is.

If during the investigation you find a second, related issue worth mentioning (e.g. same root cause hits another surface), include it in the same message under **Scope**. Do not open a second message.

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
