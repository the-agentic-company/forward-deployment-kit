---
name: bap-direction-shaping
description: |
  Routes a fuzzy or product-direction-impacting HeyBap finding to Slack
  `#feature-brainstorming` for team discussion BEFORE any Linear ticket
  is created. Used when the surface is unknown, the implementation
  would bring large or cross-cutting changes, or it is genuinely
  unclear whether the change is the right direction for HeyBap. The
  skill produces a short structured problem statement (problem, why it
  is fuzzy, possible surfaces, open questions, origin) and posts it in
  `#feature-brainstorming` via the Slack MCP. NO Linear ticket is
  opened here. If the discussion converges on a direction, someone
  re-files the finding through `feature-bug-complexity-classification`
  with the new context; it will then be classified as SIMPLE or
  COMPLEX-SCOPED and get a Linear ticket through the standard path.
---

# Product direction shaping discussion for HeyBap

The Linear board is the unit of work; tickets that land there have a known surface and a defensible plan. Some findings show up without either: too fuzzy, too cross-cutting, or with a real product-direction question hiding behind the symptom. Filing those as Linear tickets pollutes the board with stalled items and asks Baptiste to take a position on something the whole team should weigh in on first.

This skill handles that earlier stage. The output is a Slack post in `#feature-brainstorming`, structured for the team to engage with. The Linear ticket comes later, if and when the discussion converges on a direction.

## When to invoke

The router (`feature-bug-complexity-classification`) dispatches here when the classification grid returns **COMPLEX-FUZZY**. A finding is FUZZY when AT LEAST TWO of the following hold (single-criterion fuzziness defaults to COMPLEX-SCOPED, see Anti-patterns):

- **Surface unknown**: no file:line or system boundary identified during the router's 5-minute investigation.
- **Cross-cutting**: implementation would touch more than two major surfaces (sandbox runtime, schema, MCP layer, panel UI, billing, multi-tenant boundary).
- **Multiple plausible products**: more than one defensible "shape" could come out of this idea, with no obvious winner.
- **Product-fit unclear**: it is genuinely undecided whether HeyBap should solve this at all (vs document as out of scope, vs redirect to a third-party).
- **Operator confidence band**: `operatorConfidence` is in `[0.6, 0.75)`. Strong enough to discuss, not strong enough to ticket.

Do not invoke this skill directly from a pipeline step. The router is the single entry; this skill is a leaf.

## Input contract (from the router)

```json
{
  "kind": "bug | feature",
  "title": "<one-line restatement>",
  "oneLineDescription": "<operator-observed symptom>",
  "context": {
    "pipelineStep": "...",
    "evidence": [...],
    "transcriptOrCoworker": "..."
  },
  "operatorConfidence": 0.62,
  "fuzzyReasons": [
    "surface-unknown",
    "cross-cutting",
    "multiple-products",
    "product-fit-unclear",
    "confidence-band"
  ]
}
```

`fuzzyReasons` is the router's structured reason set explaining why the finding landed FUZZY. It feeds the Slack post's "Why this is fuzzy" line.

## Step 1 — shape the problem statement (5 minutes hard cap)

This step does NOT do deep investigation (that comes later, via `bap-feature-brainstorm`, IF the team decides this is worth pursuing). What it produces:

1. Restate the finding in 1-2 factual sentences, no jargon.
2. Identify which surfaces it could touch (best guess, not exhaustive). A bullet list of 2-4 candidates is enough.
3. List 3-5 open questions the team should answer (NOT 3 defensible options; the whole point is we don't have options yet).
4. Identify origin: who observed it, where, when, how often. This is the "why now" anchor for the discussion.

If the problem cannot be shaped in 5 minutes, the skill defaults to a thinner post and surfaces "needs more reproduction" as the first open question.

## Step 2 — dedup against the channel

Before posting:

1. Search Slack `#feature-brainstorming` for recent posts with distinctive tokens from the title.

   ```
   mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_search_public_and_private({
     query: "<distinctive token> in:#feature-brainstorming",
     limit: 20
   })
   ```

2. Search Linear team `Bap` for the same tokens (last 90 days). If a Linear ticket already exists, the finding has been ticketed and we should NOT also start a discussion thread; return `verdict: already-ticketed` with the ticket URL.

3. If a Slack thread already exists for the same root cause, do NOT post a new one; add a `:eyes:` reaction to the original post (signals "another person hit this") and return `verdict: already-discussed` with the thread URL.

## Step 3 — post to #feature-brainstorming

Body template (markdown, kept short on purpose; the channel is for human discussion):

```
:thinking_face: *<Title>*  ·  status: fuzzy / no Linear ticket yet

*Problem*
<1-2 factual sentences>

*Why this is fuzzy*
<one line, anchored on fuzzyReasons>

*Possible surfaces (best guess)*
- <surface 1>
- <surface 2>
- ...

*Open questions for the team*
- <q1>
- <q2>
- ...

*Origin*
<who observed it, where, when, how often>

> If the team converges on a direction, re-file via the gate (`./go.sh bug "..."` or `./go.sh feature "..."`) with the added context; the finding will then land in Linear through the standard path.
```

Post via `mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_send_message` with `channel_id` from config (resolved via `slack_search_channels({ query: "feature-brainstorming" })` if the config value is the placeholder).

No `@mention` by default. If `operatorConfidence >= 0.85` OR `fuzzyReasons` includes `product-fit-unclear`, add `<@USER_ID_BAPTISTE>` so the CTO sees it during the next product-direction review.

## Step 4 — return + log

```json
{
  "verdict": "posted | already-discussed | already-ticketed | low-confidence | config-missing",
  "slackThreadUrl": "<url>",
  "slackChannelName": "#feature-brainstorming",
  "fuzzyReasons": ["surface-unknown", "cross-cutting"],
  "openQuestions": ["...", "..."],
  "notes": "<one-sentence summary for the orchestrator>"
}
```

Append to `~/HeyBap Pipeline/logs/direction-shaping.jsonl` for audit and dashboard visibility.

## What happens after

The Slack thread runs at the team's pace. Three typical outcomes:

1. **Team converges on a direction**. Someone re-files via `./go.sh bug "..."` or `./go.sh feature "..."` with the new context (e.g. "we decided to solve this via X; ticket it as scoped"). It lands in the gate, gets classified SIMPLE or COMPLEX-SCOPED, and gets a Linear ticket. The new ticket links back to the Slack thread.
2. **Team decides "not now"**. Thread closed with a `:no_entry_sign:` reaction; the skill's log records the verdict but no Linear ticket is opened.
3. **Team decides "out of scope"**. Same as above with a `:wave:` reaction; the operator may redirect the user/customer to a different tool.

The thread itself is the trace. This skill does NOT create a Linear ticket no matter the outcome.

## Anti-patterns

- Posting to `#feature-brainstorming` AND creating a Linear ticket. The whole point of FUZZY is "we don't know yet"; ticketing prematurely locks in a frame.
- Producing 3 defensible options here. Options come from `bap-feature-brainstorm` once we have enough clarity to scope them. Here, we list questions, not options.
- Posting without dedup. The channel becomes noisy fast; one thread per discussion.
- Posting evidence dumps. The channel is for humans; keep the post short (problem + 5-7 lines max). Detailed evidence belongs in a Linear ticket later.
- Defaulting to FUZZY because the router was uncertain. Uncertainty without specific fuzziness criteria should default to COMPLEX-SCOPED so a Baptiste-owned ticket gets opened. FUZZY is for genuinely undecided direction questions.
- Single-criterion fuzziness. ONE fuzzy criterion is not enough; ticket as SCOPED. Two or more is the gate.

## Config

`lubin-skills/bap-direction-shaping/config.yaml`:

```yaml
slack:
  workspace: "The Agentic Company"
  brainstorming_channel_id: "REPLACE_WITH_FEATURE_BRAINSTORMING_CHANNEL_ID"  # resolved at runtime via slack_search_channels if placeholder
  baptiste_user_id: "U0A87JNV8QP"
  lubin_user_id: "U0AT7378GSX"
  louis_user_id: "U0A8M1B4962"
linear:
  team_key: "BAP"
  dedup_window_days: 90
investigation_time_cap_minutes: 5
log_path: "~/HeyBap Pipeline/logs/direction-shaping.jsonl"
```

If `brainstorming_channel_id` is the placeholder, the skill resolves it at runtime via `slack_search_channels({ query: "feature-brainstorming" })` and caches the result for the rest of the session.

## See also

- [feature-bug-complexity-classification](../feature-bug-complexity-classification/SKILL.md): the router that dispatches here when COMPLEX-FUZZY.
- `bap-feature-brainstorm`: COMPLEX-SCOPED sibling. Creates a Linear ticket with 3 defensible options + decision question, assignee Baptiste. Lives in `~/.claude/skills/bap-feature-brainstorm/`. Use when the surface is known and we need a Baptiste position on the implementation path.
- `bap-bug-report`: SIMPLE sibling. Implements the fix, opens the PR, creates the Linear ticket.
