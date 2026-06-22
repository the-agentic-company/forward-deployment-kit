---
name: bap-favorite-coworker-watchdog
description: |
  Continuous watchdog over the operator's PRODUCTION coworkers on Bap
  (those marked as favorite via `mcp__bap__coworker_setFavorite` — the
  convention is: favorite = in prod for a client). On each tick, lists
  favorites via `mcp__bap__coworker_list`, pulls their recent runs via
  `mcp__bap__coworker_runs`, and diagnoses anomalies (run failed, run
  completed without expected output, missing tool_use vs the agent's
  contract, run took >5x the median duration, no run in the last 24h
  despite a scheduled trigger). Posts a one-block summary per anomaly
  in Slack `#agents-production` with the run id, the failure pattern,
  the last successful run timestamp, and a suggested action.
  Platform-level issues (Bap API errors, sandbox timeouts) get routed
  through `feature-bug-complexity-classification` so they become Linear
  tickets and fixed via the rest of the pipeline. Designed as a
  scheduled `/loop` (every 1h) on the operator's laptop or on a
  Bap meta-coworker.
---

# Production coworker watchdog

The favorite flag on a Bap coworker (`mcp__bap__coworker_setFavorite`) is the operator's marker for "this one is in production for a client; do not let it silently drift". This skill watches those coworkers continuously, diagnoses anomalies in their recent runs, and surfaces the right signal in the right place:

- **Coworker-side anomalies** (output drift, missed schedule, panel render broken) → Slack `#agents-production`.
- **Platform-side anomalies** (Bap API errors, sandbox crashes, MCP unavailable) → `feature-bug-complexity-classification` so they become a Linear ticket that the rest of the pipeline handles.

The point is not to be exhaustive on every run; the point is to catch the silent failure modes that production usually hides (the coworker "ran" but produced nothing useful) before the client notices.

## When to invoke

- Scheduled `/loop 1h` on the operator's machine.
- Direct invocation with `coworkerRef: "@username"` to spot-check one specific favorite.

Do not invoke for:

- Coworkers NOT marked as favorite (the favorite flag is the explicit "in prod" signal; non-favorites are dev / experiments and noise).
- Coworkers in handoff / disabled state (`mcp__bap__coworker_setStatus` was used to pause them; no point watching).

## Input contract

```json
{
  "coworkerRef": "@username (optional; when set, watch this one only)",
  "options": {
    "cadenceMinutes": 60,
    "lookbackHours": 24,
    "minRunsForMedian": 10,
    "slowRunMultiplier": 5,
    "dryRun": false
  }
}
```

`dryRun: true` produces the diagnosis without posting to Slack or routing platform findings.

## Step 1 — list favorites

```
coworkers = mcp__bap__coworker_list({ filter: { isFavorite: true }, limit: 100 })
```

Filter out any coworker whose status is `disabled` / `paused` (use `mcp__bap__coworker_get` to read the latest status if `coworker_list` doesn't return it). Result: the production fleet.

When `coworkerRef` is set, skip the list call and watch only that coworker (still verify it is marked favorite; if not, return `not-eligible`).

## Step 2 — pull recent runs (parallel per coworker)

For each coworker in the fleet, in parallel:

```
runs = mcp__bap__coworker_runs({ reference: "<@username>", limit: 20, since: now - lookbackHours })
```

Cap parallelism at 8 concurrent `coworker_runs` calls; cooperate with the Bap rate limit.

For each run that warrants a closer look (see Step 3 triggers), fetch the full log:

```
log = mcp__bap__coworker_logs({ runId: "<id>" })
```

Do not fetch full logs for every run; reserve that for runs that fail the cheap triggers in Step 3.

## Step 3 — diagnose per coworker (5 anomaly checks, parallel-safe)

For each coworker's recent runs, apply each check independently:

### Check 1 — terminal failure

A run with `status` in `{ "failed", "error", "timeout" }`. Pull the log, capture:

- `events[*].errorMessage` (first non-null)
- Last `tool_use` event before the failure
- The `runtime_stopped_making_progress` signal if present (known Bap failure mode, see `bap-coworker-test-loop` Anti-patterns)

### Check 2 — silent output drift

A run with `status: "completed"` but no `sandboxFiles` produced, OR the expected `/app/output.html` is missing. Coworker "succeeded" but produced nothing. Common cause: skill auto-disabled by an upgrade, or a tool call returning empty.

Detect via:

- `log.sandboxFiles` empty when the coworker's last 5 successful runs had files
- Expected file (e.g. `/app/output.html`) absent on this run but present on the 3 prior

### Check 3 — missing tool_use vs contract

The coworker's agent prompt (read once via `mcp__bap__coworker_get(<ref>)`) typically lists which tools should fire each run. If `coworker_logs.events[*].tool_use` is missing a tool the agent always calls (e.g. `notion.create_page` for a Notion-writing coworker), the run is silently broken even when `status: "completed"`.

Compute a contract per coworker from the last 10 successful runs: which `tool_use` names appear in ≥ 80% of them. Flag any current run that is missing one of those tools.

### Check 4 — drastic slowdown

A run whose `durationMs` is > `slowRunMultiplier` × median of the last `minRunsForMedian` runs. Indicates a sandbox stall, an MCP timeout, or an external service degradation. Pull the log to identify the slow step.

### Check 5 — missed schedule

A coworker with a scheduled trigger (`trigger.type == "scheduled"`) that has not produced a run in the last `lookbackHours` hours. Indicates the scheduler is broken on the platform side OR the coworker was paused without `setStatus` (orphaned).

For each anomaly detected, build a finding block:

```json
{
  "coworker": "@<username>",
  "check": "terminal-failure | silent-output-drift | missing-tool-use | drastic-slowdown | missed-schedule",
  "runId": "<id>",
  "evidence": { /* check-specific: errorMessage, sandboxFiles, toolName missing, durationMs vs median, lastRunIso */ },
  "lastSuccessfulRunIso": "<iso>",
  "suggestedAction": "<one sentence>"
}
```

## Step 4 — classify each anomaly (coworker-side vs platform-side)

For each finding, decide where it routes:

| Signal | Route |
|--------|-------|
| Skill silently auto-disabled, sandbox file system error, MCP tool returning 500, Bap runtime "stopped making progress" pattern | **Platform-side** → `feature-bug-complexity-classification` |
| Coworker prompt drift (agent stops calling a tool because the prompt changed), schedule missing because the operator paused it, output template broken because the data shape changed | **Coworker-side** → Slack only |

When in doubt, route as platform-side; the classification gate de-duplicates and discards if it is a false positive.

## Step 5a — Slack `#agents-production` (coworker-side findings)

One Slack message per anomaly. Resolve `#agents-production` channel id from config; fall back to `slack_search_channels({ query: "agents-production" })`.

Body template:

```
:warning: <@username> coworker anomaly: <check>

Run: <runId>  (<linkToBapRun>)
Symptom: <one line, evidence-anchored>
Last successful run: <iso>
Median duration (last <minRunsForMedian>): <ms>; this run: <ms>

Suggested action: <one sentence>
```

No @mention; the channel watchers know to respond. Use `mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_send_message` (channel_id from config).

If three consecutive ticks surface the same anomaly on the same coworker without a fix, escalate: add a Slack `:rotating_light:` prefix and @mention the operator (`<@USER_ID_LUBIN>`) in the third message.

## Step 5b — route platform-side findings

```
invoke feature-bug-complexity-classification
  kind: "bug"
  title: "<one-line: e.g. 'coworker_run sandbox crashes after 6 successive scheduled runs'>"
  oneLineDescription: "<symptom + how often + which coworkers affected>"
  context: {
    pipelineStep: "runtime",
    evidence: [
      { kind: "run_id", value: "<runId>" },
      { kind: "log_excerpt", value: "<200 char quote from events>" },
      { kind: "code_ref", value: "<file:line if observable in the logs>" }
    ]
  }
  operatorConfidence: 0.8
```

The classification gate then dispatches to `bap-bug-report` (SIMPLE) or `bap-feature-brainstorm` (COMPLEX) per its rubric. The watchdog does not implement the fix itself; it just makes the finding visible.

Also post a single Slack message in `#agents-production` linking the new Linear ticket: `:gear: Platform-side anomaly routed to BAP-<n>: <ticketUrl>`.

## Step 6 — return + log

```json
{
  "verdict": "all-green | anomalies-detected | not-eligible | dry-run",
  "fleet": [ { "coworker": "...", "runsSeen": 17, "anomalies": [...] } ],
  "slackPostsSent": 3,
  "linearTicketsOpened": ["BAP-<n>", ...],
  "diagnosticNotes": "<one sentence if verdict != all-green>"
}
```

Append to `~/HeyBap Pipeline/logs/watchdog.jsonl` for audit and dashboard visibility.

## Autonomous mode (`/loop`)

```
/loop 60m watch favorite coworkers
  invoke bap-favorite-coworker-watchdog with no coworkerRef
  on return, append the JSONL log
  if anomalies > 0, the dashboard's footer surfaces a red dot
```

Cadence is a fixed 60 min. The skill is rate-limited internally to 8 concurrent `coworker_runs` calls so a fleet of 40 favorites stays under the Bap rate limit.

## Anti-patterns

- Watching every coworker. The favorite flag IS the contract; non-favorites are noise. Honour the flag.
- Posting to Slack on every run. The skill posts on anomalies only; silent ticks are good ticks.
- Posting platform-side findings to Slack instead of routing through the classification gate. Slack is the activity feed; Linear is the unit of work.
- Spam-escalating: every tick @mentioning the operator. The escalation rule is 3 consecutive same-anomaly ticks; not earlier.
- Treating a missed schedule as urgent without checking if the operator paused the coworker. `mcp__bap__coworker_get` returns `status`; if paused, no alert.
- Pulling full logs on every run. Use the cheap checks first; reserve `coworker_logs` calls for runs that warrant deeper analysis.
- Bypassing the rate-limit cap. 8 concurrent `coworker_runs` calls max; queueing the rest is fine.

## Config

`lubin-skills/bap-favorite-coworker-watchdog/config.yaml`:

```yaml
slack:
  workspace: "The Agentic Company"
  prod_channel_id: "REPLACE_WITH_AGENTS_PRODUCTION_CHANNEL_ID"  # resolved at runtime via slack_search_channels if placeholder
  lubin_user_id: "U0AT7378GSX"                                  # used only on 3rd-tick escalation
  baptiste_user_id: "U0A87JNV8QP"
  louis_user_id: "U0A8M1B4962"
bap:
  list_limit: 100
  runs_lookback_hours: 24
  full_log_concurrency: 8
  min_runs_for_median: 10
  slow_run_multiplier: 5
classification_gate: "feature-bug-complexity-classification"
escalation:
  consecutive_ticks_before_mention: 3
log_path: "~/HeyBap Pipeline/logs/watchdog.jsonl"
```

If `prod_channel_id` is the placeholder, the skill resolves it at runtime via `slack_search_channels({ query: "agents-production" })` and caches the result for the rest of the session. The Slack user id for the operator is only needed for the 3rd-tick escalation; until set, the escalation degrades to a plain message without @mention.

## See also

- [feature-bug-complexity-classification](../feature-bug-complexity-classification/SKILL.md): receives the platform-side findings.
- [bap-coworker-test-loop](../bap-coworker-test-loop/SKILL.md): same diagnose patterns (silent failure modes, tool_use missing, runtime stopped making progress) the watchdog reuses.
- [bap-post-deploy-verify](../bap-post-deploy-verify/SKILL.md): related; closes the loop on a single PR. This watchdog is the continuous parallel check.
- `bap-ticket-implementer`: paired autonomous loop; this skill emits findings, that skill drains them when labelled `agent-autonomous`.
