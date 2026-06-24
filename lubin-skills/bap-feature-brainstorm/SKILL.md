---
name: bap-feature-brainstorm
description: |
  Frame a COMPLEX HeyBap / Bap finding (feature request OR bug whose fix
  is structural enough to need design discussion) as a brainstorm: problem
  statement, why-it-is-not-trivial, three defensible options with trade-offs,
  and one concrete decision question. Creates a Linear ticket autonomously
  in team `Bap` (key BAP) at status `Triage` with labels `Need More Shaping`
  + (`Bug` or `Feature`) + `Dogfooding`, assigned to Baptiste, with
  @baptiste and @lubin mentioned in the description (never @louis). Then posts a mandatory
  notification in Slack `#pr-lubin` pinging Baptiste with the Linear URL, a
  3-word complexity reason, the problem, and a closing line about the 3
  options awaiting his pick (same retry + fail-loud contract as
  `bap-bug-report` Step 10). Use when `feature-bug-complexity-classification` classifies
  a finding as COMPLEX, or when the user asks for a structured brainstorm
  ticket ("brainstorme cette feature", "feature complexe pour l'equipe",
  "bug complexe a brainstormer", "ouvre un Linear pour ce sujet"). Different
  from `bap-bug-report`: question-oriented, not solution-oriented. No
  prescribed fix, no PR opened. Implementation goes through `bap-bug-report`
  in a follow-up once the team picks an option on the ticket.
  **Do not invoke directly.** This skill is a leaf of the Phase 2 dispatch.
  Route through `feature-bug-complexity-classification` (or the `/phase-2`
  slash command, or `scripts/submit-finding.sh` in the FDK repo). Direct
  invocation skips classification (a finding that should have been SIMPLE
  ends up as a brainstorm ticket; a finding that should have been FUZZY
  ends up with 3 premature options). The only exception is an explicit
  operator override.
---

# Brainstorm ticket for a complex Bap finding (feature or structural bug)

The complement to `bap-bug-report`. Where `bap-bug-report` ships a PR with a concrete quick fix and a Linear ticket at status `In Review`, this skill says "here is the gap or structural bug, here are three ways to address it, the team must decide before code", and creates a Linear ticket at status `Triage` labelled `Need More Shaping`.

Used when the finding is large enough that picking the wrong design now will cost real refactor later. Examples from the forward deployment loop:

- Features: first-class test mode for coworkers, programmatic workspace MCP server creation, a HeyBap-side schema for the agentSpec object, a panel postMessage introspection protocol, scheduled-trigger conditional dispatch.
- Structural bugs: attachments base64-encoded in the orpc JSON body coupling size with body-limit, chat-vs-coworker asymmetry of a feature wired on only one surface, skill_add async indexing race that any naive `chat_run` smoke check would lose.

The shape of the ticket is the same either way: problem, why-not-trivial, three options, decision question. The team picks on the ticket (comment or status transition); the implementation then goes through `bap-bug-report` in a follow-up, which opens its own ticket linked back to this brainstorm via `relatedTo`.

## Repo and context (always)

- GitHub: https://github.com/the-agentic-company/bap
- Linear team: **Bap** (key `BAP`), workspace `heybap` (https://linear.app/heybap).
- CTO: Baptiste. Co-founder: Louis. Power user / Chief of Staff: Lubin (you).
- Monorepo layout (same as `bap-bug-report`):
  - `apps/web/` Next.js frontend.
  - `packages/core/` server services (sandbox, file service, orpc routers).
  - `packages/db/src/schema/` data model.

## Step 1 — clone or pull the bap repo

```bash
ls -d /tmp/bap-* 2>/dev/null
gh repo clone the-agentic-company/bap /tmp/bap-brainstorm-$(date +%s)
```

Reuse a recent clone if present. Investigation requires multi-file grep that the GitHub web UI cannot do at depth.

## Step 2 — investigate the current state (15 min cap, parallel subagents)

Longer than the router (5 min) but shorter than `bap-bug-report` (which can spend an hour). The goal here is to surface enough current-state facts to make the three options grounded, not exhaustive, **and to anchor every option in an existing pattern in the codebase**. Options that invent abstractions where existing ones fit are the failure mode this step prevents.

Run the angles below as **parallel subagents** via the Agent tool (`general-purpose` or `Explore`, one per angle, in a single message). Each returns a structured report with `file:line` evidence. Wait for all returns before drafting options in Step 3.

1. **Current implementation, if any** of the area the feature touches. The feature is sometimes "extend X to Y" rather than "build from scratch". Locate X with file:line and one sentence on its current contract.
2. **Adjacent surfaces** that would need to change together. HeyBap has known asymmetries (chat vs coworker output panel, prototype vs prod variants). A feature that lives only on one surface is usually wrong. For each adjacent surface, file:line + which contract it owes.
3. **Reusable patterns**. Find 2 to 3 places in the repo where a *similar shape* is already implemented (different domain, same kind of work). Each option you draft in Step 3 must point at one of these or justify why none fits. No option should invent a brand new abstraction in parallel to an existing one without that justification.
4. **Open PRs and recent commits** in the area. `gh pr list --search "<area>" --state all --limit 20` and `git log --oneline -- <path>` reveal ongoing work that constrains the design. List any in-flight work that the brainstorm must respect.
5. **Existing related Linear tickets.** Search team BAP with distinctive tokens from the finding, especially looking for prior brainstorm tickets (label `Need More Shaping`) on the same area. Past discussions anchor the new ticket; link them via `relatedTo`.
6. **One-line model-of-the-world**: how the feature would change the contract for skill writers / coworker creators / forward deployment operators.

Brief each subagent with: the feature title, the repo path on disk, the layout above, and the requirement to ground every claim in `file:line` references. Run angles 1-5 **concurrently** (single Agent tool message, multiple invocations). Angle 6 is synthesised by this skill from the others, not delegated.

Cap: 15 minutes wall-clock total. If the area is so unfamiliar that 15 minutes is not enough to draft three options grounded in existing patterns, abort and return to the human: "Need a 30-min sync to scope before brainstorming. Topics: <2-3 unknowns from the angle reports>."

## Step 3 — design three distinct options

Three options, not two, not five. Two collapses into "we should do A". Five is a survey, not a decision.

Each option must be:

- **Defensible**: a real product person could argue for it. No strawman option B exists to make A look good.
- **Distinct**: different on at least one of (transport, surface, scope, data model, who-owns-the-action). Two options that vary only in naming or in a constant are one option.
- **Bounded**: one or two sentences for the "how", one sentence for the trade-off.

For each option, name it with a short noun phrase that captures the design choice ("Inline route on the coworker side", "Server-side dedicated worker", "Out-of-band webhook with retry", etc.). Avoid generic names like "Option A", "MVP", "Quick path" in the ticket.

Honest trade-off line: what does this option cost that the other two do not. Cost can be lines of code, ongoing maintenance, breaking change surface, performance, billing exposure, security review, learning curve for skill writers.

## Step 3b — quantify impact (feature gaps only, mandatory)

When the finding is a *capability gap* (HeyBap cannot do X today), produce demand-side signal before drafting the ticket body. Step 2 already gave you the codebase grounding (adjacency, surfaces, callers, tests, history). This step adds the why-it-matters axis: who else needs this capability, and what is the team's verdict.

Skip this step only when the finding is a *structural bug* (not a missing capability). Bugs already have the right shape for the 3-options approach without the impact lens.

### 3b.1 — scan the Grain transcript corpus for the same pain

The operator's Grain transcript corpus (~620 transcripts via the Grain public API + PAT bearer, see memory `grain-corpus-access`) is the canonical place to measure feature demand. Build 3 to 5 distinctive queries from the finding title and context:

- File paths / symbol names mentioned in the original finding.
- Noun phrases unique to the gap ("programmatic MCP bind", "scheduled trigger conditional", "panel button introspection").
- Verbs that hint at the missing API ("listAll", "createBound", "subscribe").

For each match, record: transcript id, speaker, timestamp, quoted line. Collapse near-duplicates (same speaker within 2 min on the same topic). If the corpus is not accessible locally (no API key, no cache), fall back to past Linear tickets in team `BAP` with label `Need More Shaping` matching the capability text.

### 3b.2 — scan past coworker builds for blocked work

Past builds live under `~/HeyBap Pipeline/runs/<callId>/` with an `agent-spec.json`, a `coworkers.json`, and a `report.md`. Grep them for:

- `ambiguities[]` entries whose `topic` mentions the same capability area.
- `notBuilt[]` entries whose evidence overlaps lexically with the capability noun phrase.
- `report.md` lines flagged "Built and waiting for human MCP bind" or "Blocked by HeyBap capability gap".

Each hit becomes a `useCasesUnlocked[]` entry: the coworker that would have shipped if the capability had existed, with the run id that surfaced the block.

### 3b.3 — list adjacent use cases unlocked

Beyond the use case that triggered this finding, what *new* things become possible once the capability exists. 2 to 5 entries, each with:

- One-line use case (concrete, customer-facing when possible).
- Evidence reference: transcript id from 3b.1, run id from 3b.2, or related BAP-<n> ticket. No speculation without a reference.
- Workaround that exists today (or `null` if none). Lets the team weigh "feature vs accepting the workaround".

The use case that triggered the finding is the *trigger*, not part of the unlocked list. Counting it inflates the demand signal.

### 3b.4 — verdict + rationale

Produce a single block reused in the ticket body's `## Impact si implémenté` section:

```json
{
  "verdict": "implement | wait | defer | won't fix",
  "rationale": "<2-3 lines: use cases unlocked vs effort (t-shirt from Step 2) vs risk>",
  "alternatives": [
    { "name": "workaround in operator's playbook", "where": "manual UI step in <screen>" },
    { "name": "feature flag on adjacent surface", "where": "feature already exists for chat, extend to coworker output" }
  ]
}
```

Verdict rubric:

- **implement**: t-shirt S/M AND ≥ 2 unlocked use cases (one customer-facing) AND no defensible workaround.
- **wait**: t-shirt L/XL, even with many unlocked use cases. Bundle with a larger initiative.
- **defer**: t-shirt S/M but only 1 unlocked use case AND a documented workaround. Cost > value today.
- **won't fix**: the capability would conflict with a deliberate design choice already made on this surface (Step 2 angle 5 surfaced the conflict).

When in doubt, output `wait` and ask the team to override.

If verdict is `won't fix`, still create the ticket (the team sees the dissent) but prepend `**Recommandation : won't fix**` at the top of the description body.

Cap: 10 minutes wall-clock on the corpus + builds scans combined. Do not bluff numbers the scans did not support; missing data is itself a signal.

## Step 4 — write the Linear ticket body

**Strict style**:

- French (the team is French, the call transcripts are in French, the brainstorm should match).
- Sober, professional, no childish tone.
- **No em-dashes (— / –) ever.** Use commas, colons, parentheses, split sentences.
- Factual only. No business framing, no "this would unlock", no marketing.
- No fluff intros. Get to the gap.
- Every technical claim that points at code carries a `file:line` reference.
- **Aim 250-400 words.** Linear renders long markdown comfortably, but a brainstorm ticket is still a decision artefact, not a doc.
- No prescriptive infra (no Vercel, no S3) unless the repo uses it.

**Title** (under 70 chars, no em-dash): start with the area in parentheses to mirror the bap PR convention, then the noun phrase.

```
(Brainstorm) <Area>: <noun phrase that names the gap>
```

Example: `(Brainstorm) Web: programmatic workspace MCP server bind`.

**Description** (mandatory blocks):

```markdown
**Status : à arbitrer par l'équipe.**

@baptiste @lubin

## Contexte
<2-3 lignes : le besoin observé (forward deployment, retour client, gap du pipeline FDK) et la surface HeyBap concernée>

**Use cases débloqués (${unlockedCount})**
- ${use_case_1} (évidence : ${ref}, workaround actuel : ${workaround})
```

Mentions: the `@baptiste` `@lubin` line at the top of the description triggers Linear notifications for both. **Never mention `@louis`** — Louis Adam must not be tagged in any ticket or message produced by this workflow, regardless of whether the finding touches UI / chat / coworker output / panel rendering. Use Linear's `@displayName` syntax exactly as written, no brackets, no email; the MCP description for `save_issue` specifies this format.

**Optional, include only if it adds signal**:

- **Lien aux findings récents**: `Surfaced N fois dans le pipeline FDK ce mois (test loop / orchestrator).` Use when multiple coworker builds hit the same gap; raises priority.
- **Constraints connues**: `Ne touche pas <X>, design déjà arbitré en <date / ticket BAP-Y>.` Use to keep the brainstorm focused.

No "scope" section, no "alternatives considered" (the three options ARE the alternatives), no preamble.

## Step 6 — create the Linear ticket

```
mcp__linear__save_issue({
  team: "BAP",
  title: "(Brainstorm) <Area>: <noun phrase>",
  description: "<full markdown body from Step 4>",
  state: "<config.linear.statuses.triage>",
  labels: [
    "<config.linear.labels.need_more_shaping>",
    "<config.linear.labels.bug | .feature>",                    // pick one based on the finding kind
    "<config.linear.labels.dogfooding>",
    "<config.linear.labels.ui_ux>"                              // only if the finding touches UI
  ],
  assignee: "<config.linear.default_assignee_user_id>",        // Baptiste
  priority: 3
})
```

Capture the identifier and URL from the response.

If the team_id or any required label id in config is missing or set to a placeholder, refuse to create and return `verdict: "config-missing"` with the missing key name.

## Step 6.5 — Slack `#pr-lubin` notification (brainstorm à trancher, ping Baptiste)

**This step is MANDATORY**, same contract as `bap-bug-report` Step 10: without the Slack post, Baptiste does not learn the ticket exists and the COMPLEX-SCOPED dispatch is NOT complete. The skill is done at "Slack permalink captured", not at "Linear ticket created".

Why the post is needed even though Linear notifies on its own: SIMPLE tickets and SCOPED tickets land in the same Linear board; without an explicit signal in `#pr-lubin` flagging that this one is a brainstorm requiring a design decision (not a code review), Baptiste cannot triage his Linear queue at a glance.

Resolve identifiers (same as bug-report):

- channel id from `config.slack.pr_channel_id` (`C0BCH5L6PQS` = `#pr-lubin`); fall back to `slack_search_channels({ query: "pr-lubin" })` only if the placeholder is still in place.
- reviewer id from `config.slack.review_user_id` (`U0A87JNV8QP` = Baptiste); fall back to `slack_search_users({ query: "Baptiste" })` only if missing.

Body template (Slack mrkdwn). 5 lines. Line 1 = `À toi de trancher` prefix + Baptiste ping + Linear URL — at a glance, Baptiste sees this is a brainstorm awaiting his decision, not a PR awaiting review (the SIMPLE sibling uses `Fixed, to review` instead). Line 2 = italic ticket title. Line 3 = explicit complexity flag with the 3-word reason. Lines 4-5 = problem + closing line about the 3 options awaiting his pick.

```
À toi de trancher <@<reviewer-id>> <Linear ticket URL>
_<titre du ticket, sans le préfixe (Brainstorm)>_
Bug/feature *complexe* (<raison en 3 mots : intermittent | multi-approches | surface-large | data-model | ux-decision | security-risk | breaking-change | scaling-question>) → pas de PR, brainstorm à trancher.
<problème en 1-2 phrases, avec la surface technique localisée file:line si possible>
3 options défendables proposées dans le ticket avec leurs trade-offs. À toi de choisir, je repars sur un fix SIMPLE une fois tranché.
```

`<raison en 3 mots>` is picked from the Step 2 investigation:
- `intermittent` : the symptom does not reproduce deterministically.
- `multi-approches` : Step 3 produced 3 genuinely defensible options with no obvious winner.
- `surface-large` : the change touches 3+ surfaces (chat + coworker + settings, or web + sandbox + db).
- `data-model` : a schema migration or contract change is needed.
- `ux-decision` : the team must pick between defensible UX paths.
- `security-risk` : the change opens auth / permission / data-exposure questions.
- `breaking-change` : existing callers must update.
- `scaling-question` : the right answer depends on volume assumptions.

If the finding is a *bug* (not a feature gap), prefer `bug *complexe*` over `feature *complexe*` in line 3.

Mandatory call sequence (same retry + fail-loud as `bap-bug-report` Step 10):

```
result = mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_send_message({
  channel_id: "<config.slack.pr_channel_id>",
  text: "<composed body above>"
})
if result.ok != true OR result.permalink is null:
  # retry once
  result = mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_send_message({ channel_id, text })
if result.ok != true OR result.permalink is null:
  slackPostFailed = true
  slackPostError  = result.error or "no permalink returned"
else:
  slackPermalink = result.permalink
```

The return value (Step 7) must carry either `slackPermalink` OR `slackPostFailed: true` with the error. Silently skipping is a contract violation.

Constraints:

- Exactly one message per ticket (top-level, no thread). On a re-run that produces a different brainstorm ticket, post fresh; on a re-run that lands on the same ticket (the Linear save is idempotent on title + label), skip via `slack_search_public({ query: "<Linear URL>", limit: 5 })`.
- Line 1 starts with the literal text `À toi de trancher ` followed by the `<@U…>` ping and the Linear URL. The ping is what notifies Baptiste's Slack; the prefix labels the action (brainstorm-to-arbitrate, not PR-to-review).
- Use `*complexe*` (Slack bold mrkdwn) so the complexity flag stands out even if the line scrolls past in the channel.
- No `Linear:` link line. The URL is on line 1.
- No em-dashes.

## Step 7 — return to the user

Three blocks, no commentary:

1. The Linear ticket: `BAP-<n>  <ticket URL>`.
2. The Slack permalink from Step 6.5, **or** `SLACK POST FAILED: <error>` if Step 6.5's retry also failed. Never silently omit this block.
3. The full description that was posted to Linear (so the user can edit in Linear if needed).

If `slackPostFailed: true`, the operator must repost manually before Baptiste is aware of the brainstorm.

## Config

`~/.claude/skills/bap-feature-brainstorm/config.yaml`:

```yaml
linear:
  team_id: "5ff3b86a-a1a5-4241-ac5c-e65a143f16e3"
  team_key: "BAP"
  default_project_id: null
  default_assignee_user_id: "b05ce629-639d-4861-8de0-c2ba17ce84a6"  # Baptiste
  labels:
    bug: "e356eade-cc41-4abb-9447-00487b30583c"
    feature: "296529af-3672-4bd7-876d-64245d40c768"
    need_more_shaping: "aec20ab1-873c-400c-9466-747706a58b1d"
    dogfooding: "50b28f0f-60be-460d-9db1-bd2e03e79f42"
    ui_ux: "848839d8-15da-440a-96e1-02e725dc153d"
  statuses:
    triage: "b63fe240-0351-4011-a754-3b69c3cc5c99"
slack:
  workspace: "The Agentic Company"
  pr_channel_id: "C0BCH5L6PQS"   # #pr-lubin — resolved at runtime via slack_search_channels({ query: "pr-lubin" }) if missing
  review_user_id: "U0A87JNV8QP"   # Baptiste — resolved via slack_search_users({ query: "Baptiste" }) if missing
github_repo: "the-agentic-company/bap"
investigation_time_cap_minutes: 15
```

Keep this in sync with `lubin-skills/feature-bug-complexity-classification/config.yaml`. The router is the canonical source.

## What NOT to do

- Do not write two options. Two is binary, three forces real comparison.
- Do not propose strawman options to push the team toward your favourite. Each option must be defendable on its own.
- Do not write a "recommendation" section. The skill does not pick; the team does.
- Do not include code snippets in the ticket body. The decision is product-shaped, not code-shaped. `file:line` references are enough.
- Do not use em-dashes.
- Do not invoke `bap-bug-report` as a fallback. They cover different shapes of findings; route through `feature-bug-complexity-classification` if uncertain.
- Do not skip Step 6.5 (Slack `#pr-lubin` post). Without it, Baptiste cannot tell from his Linear queue alone that the ticket is a brainstorm awaiting a decision instead of a PR awaiting review.
- Do not silently succeed when `slack_send_message` returns a non-ok payload. The retry + fail-loud sequence in Step 6.5 is the contract.
- Do not create the ticket without the `@baptiste @lubin` mention line (never add `@louis`). Without it, the team is not notified inside Linear either.

## See also

- `feature-bug-complexity-classification`: invokes this skill for COMPLEX-SCOPED findings.
- `bap-bug-report`: SIMPLE counterpart (solution-oriented, opens PR + creates Linear ticket at `In Review`).
- `bap-post-deploy-verify`: closes the loop after the team picks an option and `bap-bug-report` ships the implementation; transitions the resulting `In Review` ticket to `Live`.
- Grain corpus access: operator memory `grain-corpus-access` (~620 transcripts via Grain public API + PAT bearer). Used by Step 3b.1 to measure demand for feature gaps.
- Pipeline skills under `lubin-skills/` that produce the findings this skill consumes.
