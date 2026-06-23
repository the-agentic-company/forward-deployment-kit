---
name: bap-client-notify
description: |
  Post a client-facing status update to the prospect's Slack channel
  during the transcript-to-bap-coworker pipeline. Two phases:
  "planned" (after the parser + tool resolver have finalised the list of
  coworkers that will be built, posted before any actual build), and
  "validated" (after the test loop confirms the coworkers run live).
  Channel resolution is automatic via `slack_search_channels` with the
  prospect name as query; if no match above 0.5 similarity exists, the
  skill creates a public channel `client-<slug>` with
  `slack_create_conversation` and signals the operator to invite the rest
  of the team manually (the Slack MCP does not expose `conversations.invite`).
  Posts are short, plain-French, business-readable; no internal jargon
  (no skill names, no MCP ids, no FINDING_CONTEXT). Use from
  `transcript-to-bap-coworker` Step 2.5 and Step 6.5.
  **Do not invoke directly.** This skill is called by the Phase 1
  orchestrator at fixed points (Step 2.5 planned, Step 6.5 validated).
  Direct invocation outside the orchestrator can break the idempotence
  guard (the JSONL log is keyed on `callId` + `phase`) and produce
  duplicate client posts. The only exception is reposting after a manual
  channel misconfiguration, with an explicit operator instruction.
---

# Client status notifier for the forward deployment pipeline

Each forward deployment delivers one or more Bap coworkers to a client account. This skill posts two status updates in the account's Slack channel so the team sees what is being built and when it goes live:

1. **Planned**: the spec is finalised, we know exactly which coworkers will be built and which integrations they will use. Sent right after `transcript-to-bap-coworker` Step 2 (tool resolution).
2. **Validated**: the coworkers are tested and live on Bap. Sent right after Step 6 (test loop) and before Step 7 (consolidated report).

The posts are written for a non-engineer reader. The audience is the team that owns the account on Slack, plus any client-side stakeholders who sit in the channel. Keep the language plain.

## When to invoke

- `transcript-to-bap-coworker` Step 2.5 (mandatory): post the "planned" message after the tool resolver returns.
- `transcript-to-bap-coworker` Step 6.5 (mandatory): post the "validated" message after the test loop returns.
- Direct invocation if a channel was misconfigured and the message needs to be reposted.

Do not invoke for:

- A `dryRun: true` orchestrator pass (nothing is actually built, so no client-facing notification).
- A pipeline run where every agent ends in `notBuilt` (nothing to announce). In that case the orchestrator should skip the planned post entirely.

## Input contract

```json
{
  "phase": "planned | validated",
  "prospect": "<from spec.callMeta.prospect, e.g. 'Concentrix Medica'>",
  "callId": "<from spec.callMeta.callId, used for idempotence>",
  "coworkers": [
    {
      "name": "@previsite-medica",
      "objective": "<one line in plain French, no jargon>",
      "tools": ["Notion (lecture)", "Gmail (envoi)", "Browser MCP"],
      "panelUrl": "https://heybap.com/... (validated phase only)",
      "status": "live | needsReview (validated phase only)"
    }
  ],
  "options": {
    "createIfMissing": true,
    "channelSlugPrefix": "client-",
    "channelSearchThreshold": 0.5,
    "dryRun": false
  }
}
```

`dryRun: true` resolves / creates the channel but does NOT post the message; it returns the composed body so the caller can review.

## Step 1 — resolve the client channel

```
matches = mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_search_channels({ query: "<prospect>" })
```

For each returned channel, compute a similarity score against the prospect name lowercased (Levenshtein ratio or token-overlap, whichever is available). Keep the top result if its score ≥ `channelSearchThreshold` (0.5 by default). Below the threshold, treat as no-match (avoids matching `#dev` when prospect is "DevAgency", or `#design` when prospect is "Designit").

When the prospect has multiple words, also try `prospect.toLowerCase().replace(/\s+/g, '-')` and `prospect.toLowerCase().split(' ').join('')` as additional queries; take the union and dedupe by channel id.

If a match passes the threshold, use that channel id and skip to Step 2.

### Step 1b — create the channel when none exists

If no match passes the threshold and `options.createIfMissing` is `true`:

Compute the slug:
- lowercase the prospect name
- strip accents (`é` → `e`, `à` → `a`, etc.)
- replace any non-alphanumeric run with a single `-`
- trim leading / trailing `-`
- prepend the `channelSlugPrefix` (`client-` by default)
- cap to 80 chars (Slack channel name limit)

Example: `Concentrix Medica` → `client-concentrix-medica`. `L'Oréal Paris` → `client-l-oreal-paris`.

Create the channel:

```
created = mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_create_conversation({
  name: "<slug>",
  is_private: false
})
```

The Slack MCP does not expose `conversations.invite`, so the only initial member is the operator (whoever's token is in play). Record this in the return value so the orchestrator's final report tells Lubin "channel created, invite Baptiste / Louis manually if needed".

If `createIfMissing` is `false` and no match exists, return `{ verdict: "channel-not-found", proposedName: "<slug>", message: "no Slack channel found for <prospect> and createIfMissing is false; post skipped" }`. The orchestrator continues without raising.

## Step 2 — compose the message

Plain French, business-readable. No em-dashes. No internal terms.

### Phase = planned

```
:rocket: Coworkers planifiés pour {Prospect}

Voici les agents que nous allons déployer pour cet échange :

• *{coworker[0].name}* — {coworker[0].objective}
  Intégrations : {coworker[0].tools.join(", ")}

• *{coworker[1].name}* — {coworker[1].objective}
  Intégrations : {coworker[1].tools.join(", ")}

...

Prochaine étape : génération du code, déploiement et tests automatisés. Je reposte ici dès que les coworkers sont en place.
```

When `coworkers.length === 1`, drop the colon-introduction and use "Voici l'agent que nous allons déployer pour cet échange :" (singular).

### Phase = validated

```
:white_check_mark: Coworkers {Prospect} en place

Les agents sont créés, testés et opérationnels :

• *{coworker[0].name}* — {coworker[0].objective}
  Accès : {coworker[0].panelUrl}

• *{coworker[1].name}* — {coworker[1].objective}
  Accès : {coworker[1].panelUrl}

...

Tu peux les retrouver dans le workspace HeyBap. Pour les déclencher, passe par la conversation du coworker ou par son trigger natif.

Si quelque chose à ajuster, fais-moi signe.
```

For a coworker with `status: "needsReview"`, prefix its bullet with `:warning:` and replace the access line with `Accès : en cours de validation` (no URL). When at least one coworker is `needsReview`, append a final line: `Un agent demande encore une vérification manuelle. Je reviens vers toi dès qu'il est validé.`

When all coworkers are `needsReview` (no `live`), skip the validated post entirely and signal `{ verdict: "skipped-all-needsreview" }` to the caller. The orchestrator's consolidated report carries the diagnosis.

## Step 3 — post

```
posted = mcp__aa816864-db59-4de1-a375-68c8cccbfe71__slack_send_message({
  channel_id: "<resolved or created>",
  text: "<composed body>"
})
```

Capture `posted.permalink`.

Idempotence: the orchestrator passes `callId`; the skill writes a JSONL log entry to `~/HeyBap Pipeline/logs/client-notify.jsonl` with `{ callId, phase, channelId, permalink, ts }`. Before posting, the skill greps the log for an existing entry matching `(callId, phase)`. If one exists, the skill skips the post and returns the prior permalink. This keeps `/loop` and retries from spamming the channel.

## Step 4 — return

```json
{
  "verdict": "posted | already-posted | channel-not-found | skipped-all-needsreview | dry-run",
  "channelId": "C0XYZ...",
  "channelName": "client-concentrix-medica",
  "createdChannel": true,
  "needsManualInvite": ["Baptiste", "Louis"],  // when createdChannel = true
  "permalink": "https://the-agentic-company.slack.com/archives/C0XYZ.../p123...",
  "composedBody": "<the post body; useful for the orchestrator report>"
}
```

When `createdChannel: true`, the orchestrator's Step 7 consolidated report surfaces the needsManualInvite list as a TODO line so Lubin can `/invite` the rest of the team in the new channel from the Slack UI.

## Anti-patterns

- Posting internal jargon (skill names, MCP server ids, FINDING_CONTEXT, BAP-<n> identifiers). The client reads this; product-language only.
- @mentioning anyone with `<@U…>`. The post is informative, not a review request. Pings belong in `#dev` (handled by other skills).
- Using em-dashes. Team style ban.
- Skipping the idempotence log. Without it, every `/loop` tick reposts the planned message and the channel fills with duplicates.
- Auto-creating private channels. Default is public; the operator switches to private manually if the account requires it.
- Creating a channel for a one-off pipeline run that ends in `notBuilt`. The orchestrator must check `live.length + needsReview.length > 0` before invoking the planned phase.
- Posting both phases from a single invocation. Each call posts one phase; the orchestrator calls twice.
- Treating the `validated` phase as a hard sync point. If the test loop ends `needsReview` for all agents, the skill skips the post; the consolidated report alone carries the diagnosis.

## Config

`lubin-skills/bap-client-notify/config.yaml`:

```yaml
slack:
  workspace: "The Agentic Company"
  channel_search_threshold: 0.5
  channel_slug_prefix: "client-"
  is_private_default: false
  operator_user_id: "U0AT7378GSX"  # Lubin (only auto-member when a channel is created)
  manual_invite_reminder:
    - "U0A87JNV8QP"  # Baptiste
    - "U0A8M1B4962"  # Louis
log_path: "~/HeyBap Pipeline/logs/client-notify.jsonl"
```

## See also

- [transcript-to-bap-coworker](../transcript-to-bap-coworker/SKILL.md): primary caller (Step 2.5 and Step 6.5).
- [parse-transcript-to-agent-spec](../parse-transcript-to-agent-spec/SKILL.md): produces `spec.callMeta.prospect` and the per-agent goal / tool list this skill renders.
- [bap-coworker-test-loop](../bap-coworker-test-loop/SKILL.md): emits the `live` / `needsReview` status this skill renders in the validated post.
