---
name: bap-prior-art-scout
description: |
  Before building a new HeyBap coworker (or its skill / custom MCP / panel
  template), scan the operator's prior work to find similar existing
  artefacts that can be reused as-is or adapted: workspace coworkers
  already live on Bap (via `mcp__bap__coworker_list`), past builds under
  `~/HeyBap Pipeline/runs/`, custom MCP projects and demo apps under the
  vault (`~/Personal Agents/vault/projects/`), FDK `lubin-skills/`, and
  personal skills (`~/.claude/skills/`). Returns a ranked list of matches
  with `reuseRecipe` (what to copy + where to anchor) and a primary
  recommendation that downstream skills (`transcript-to-bap-coworker`,
  `parse-transcript-to-agent-spec`, `build-agents-for-bap`) consume to
  ground new coworker generation in existing patterns instead of
  reinventing. Use when the orchestrator is about to generate a new
  skill folder, when the parser flags a capability the operator likely
  has prior art on (PDF render by email, audio transcription, panel
  HTML output, CRM sync), or standalone with `capability: "..."` to ask
  "have I built something like this before?".
---

# Prior art scout for new coworker builds

When Lubin builds a new HeyBap coworker, there is almost always a previous build that solves part of the same problem: a render pattern, a panel layout, an MCP for an external service, a skill prompt structure, a sandbox CLI fallback. Reinventing is the failure mode this skill prevents. The first build of any shape (PDF by email, audio transcription, calendar sync, SEO publishing) does the hard work; subsequent builds should anchor on it.

This skill is the mirror of `bap-capability-impact-analyzer` but for the **creation** side: where the analyzer asks "should we build this and how big is it", this scout asks "have we already built something close enough to copy from".

## When to invoke

- `transcript-to-bap-coworker` Step 1.5 (mandatory): right after the parser emits an `agentSpec`, before generating any skill folder. Output feeds Step 3 (skill folder generation) so the generated `SKILL.md` / `render.py` / `output_template.html` cite the prior art they model on.
- `parse-transcript-to-agent-spec` Step 5 (`needed_tools` resolution): when classifying a tool, check first whether a prior coworker already uses an equivalent (existing MCP, sandbox CLI pattern, integration wiring) before downgrading to `custom_mcp_to_build`.
- Standalone, when the operator asks "have I already done something with X" or "what's the closest agent I have to Y".

Do not invoke when:

- The new coworker is so generic that any matching is noise (e.g. a one-line "send a Slack message" agent).
- The operator explicitly says "fresh from scratch, ignore prior work" (rare, but respect the override).

## Input contract

```json
{
  "capability": "<one-line: e.g. 'PDF report by email triggered by audio file upload'>",
  "context": "<2-3 lines: the use case, the prospect, the surfaces involved>",
  "signals": {
    "outputs": ["pdf-attachment", "html-panel", "email", "notion-page", "..."],
    "inputs": ["audio-file", "transcript", "csv-upload", "..."],
    "integrations": ["gmail", "notion", "salesforce", "..."],
    "verbs": ["render", "transcribe", "summarize", "publish", "..."]
  },
  "options": {
    "researchTimeCapMinutes": 8,
    "maxResultsPerAngle": 5
  }
}
```

`signals` is optional but the more populated, the more precise the scoring. The parser populates it from the transcript; standalone callers can leave it empty and let the scout match on `capability` alone.

## Step 1 — deep parallel scan (5 angles, mandatory)

Run the angles below as parallel subagents (Agent tool, `general-purpose` or `Explore`, one per angle, single Agent message). Each returns a structured report with concrete refs. Wait for all to return before ranking.

### Angle 1 — Workspace coworkers on Bap

The most direct source. Call `mcp__bap__coworker_list({ limit: 100 })`, get every coworker the operator has live. For each, call `mcp__bap__coworker_get(@username)` to read the full prompt + integrations + skillSlugs + description.

Match heuristic (any of):
- description contains a noun from `signals.outputs` / `signals.inputs` / `signals.verbs`
- integrations overlap with `signals.integrations` (>= 1 match)
- skillSlugs overlap with previously-built skills in the same domain
- prompt body contains keywords from `capability`

For each match: `@username`, description, integrations, skillSlugs (with file:line if those skills live in `lubin-skills/`), prompt excerpt (max 3 lines around the matching keyword). The `reuseRecipe` for these: "model the new coworker prompt on `@<username>`; the relevant section is its <X> block".

### Angle 2 — Past HeyBap Pipeline builds

Glob `~/HeyBap Pipeline/runs/*/agent-spec.json` and `~/HeyBap Pipeline/runs/*/coworkers.json` and `~/HeyBap Pipeline/runs/*/report.md`. Each build is a record of a past coworker construction with its full context (transcript reference, prospect, ambiguities, generated assets).

For each match: callId, prospect, the agentSpec entries that resemble the new build, links to `<callId>/<slug>/output_template.html` and `<callId>/<slug>/SKILL.md` and `<callId>/<slug>/render.py` if present. `reuseRecipe`: "copy `runs/<callId>/<slug>/output_template.html` and adapt the data shape" or "the render.py pattern at `runs/<callId>/<slug>/render.py:line` already does <X>".

### Angle 3 — Vault projects

Scan `~/Personal Agents/vault/projects/*/`. Read each project's top-level `SKILL.md` (if any), `AGENTS.md`, `README.md`. Look for:

- Custom MCP projects (presence of `mcp-handler` in any `package.json`, an `api/mcp/route.ts` file, Vercel deployment metadata).
- Skill bundles (a `skill.v2/` or `skill/` subdirectory with `SKILL.md` + `render.py`).
- Panel HTML templates (any `.html` file under the project that's referenced as a `/app/output.html` template).
- Reference architectures (`AGENTS.md` documenting how a multi-agent system was structured).

Known anchors the operator already has (verify each is still on disk before citing):
- `vault/projects/batimgie/skill.v2/` — energy audit, audio → PDF by email pattern.
- `vault/projects/hyperstack-transcribe/` — custom MCP for audio transcription.
- `vault/projects/li-seo/` — autonomous SEO operator (heartbeat launchd, multi-language publishing).
- `vault/projects/heybap-live-copilot/` — live call copilot, SSE + multi-tenant context.

For each match: project path, the artefacts inside (with file:line), one-line purpose. `reuseRecipe`: "use the MCP at `vault/projects/hyperstack-transcribe/api/mcp/route.ts:42` for audio transcription instead of building a new one", or "the PDF generation pipeline at `vault/projects/batimgie/skill.v2/render.py:120` already handles the email attachment leg".

### Angle 4 — FDK `lubin-skills/`

Scan `~/Code/forward-deployment-kit/lubin-skills/*/SKILL.md`. These are battle-tested skills shipped to the team. Match against `signals` and `capability`. Specifically check:

- `build-agents-for-bap/SKILL.md` — every rule applies; rule numbers cited where relevant.
- `build-mcp-for-bap/SKILL.md` — if `custom_mcp_to_build` was tagged by the parser, this is the template.
- Any prior pipeline skill (`parse-transcript-to-agent-spec`, etc.) whose anchors apply.

`reuseRecipe`: "rule #X in `build-agents-for-bap/SKILL.md:line` applies; follow it verbatim for the panel button protocol", or "the OAuth dance template lives at `build-mcp-for-bap/SKILL.md:line`, copy it".

### Angle 5 — Personal global skills

Scan `~/.claude/skills/*/SKILL.md`. Same approach as angle 4. The personal skills folder typically holds operator-specific helpers (`bap-feature-brainstorm` lives there; there may be domain helpers like `lubin-blog-writer`, `lubin-html-pages`, `mermaid-diagram` that fit the new build).

For panel HTML output coworkers, `lubin-html-pages` is the natural template anchor; `reuseRecipe`: "invoke `lubin-html-pages` skill to generate the panel template, then drop the result into `<callId>/<slug>/output_template.html`".

## Step 2 — rank and recommend

Aggregate matches across the 5 angles. For each match, compute a score on:

| Criterion | Weight |
|-----------|--------|
| Same surface (chat panel, coworker output, email, PDF, ...) | 3 |
| Same external integration (gmail, notion, salesforce, custom MCP) | 2 |
| Same input shape (audio file, csv, transcript, ...) | 2 |
| Same output shape (PDF, HTML panel, notion page, ...) | 2 |
| Same prospect / domain (rare but high signal) | 1 |
| Recency (last modified < 30d) | 1 |

Sort matches by score desc. Cap to `maxResultsPerAngle` per source. Identify the **single most reusable** artefact across all sources as `recommendation.primaryReuse`.

Surface up to 3 secondary reuses (different angles, complementary). If no match scores above 4 across any angle, set `noPriorArt: true` and explain why (truly novel, or signals too vague).

## Step 3 — patterns observed (synthesis layer)

Beyond individual matches, surface the *patterns* you see in the operator's prior work that apply here. Examples of patterns the scout commonly extracts:

- **Audio → transcribe → structured output**: BATIMGIE pattern. Use `hyperstack-transcribe` MCP, then a `render.py` for the structured artefact.
- **Tabular data → HTML panel with action buttons**: many coworkers follow this. Use rule #15 of `build-agents-for-bap` and copy a known `output_template.html`.
- **Scheduled trigger → fetch → write to Notion**: SEO operator pattern. Anchor: `vault/projects/li-seo/`.
- **Multi-tenant SSE on a live call**: heybap-live-copilot pattern.

Each pattern is one line + the anchor it lives at. Two to five patterns max; this is a signal not a survey.

## Output

```json
{
  "capabilityProbed": "...",
  "matches": [
    {
      "source": "workspace-coworker | past-build | vault-project | fdk-skill | personal-skill",
      "ref": "@username or path:line",
      "name": "...",
      "score": 7,
      "description": "...",
      "reuseRecipe": "<1-2 lines: what to copy + where to anchor>",
      "modifiedAt": "ISO timestamp (if known)"
    }
  ],
  "patternsObserved": [
    { "pattern": "<one-line>", "anchor": "<path:line or @username>" }
  ],
  "recommendation": {
    "primaryReuse": { "ref": "...", "reuseRecipe": "..." },
    "secondaryReuses": [ { "ref": "...", "reuseRecipe": "..." } ],
    "noPriorArt": false
  },
  "researchTimeSeconds": 240
}
```

## Integration with `transcript-to-bap-coworker`

After the orchestrator's Step 1 (parse) and before Step 2 (resolve tools), insert:

```
priorArt = invoke bap-prior-art-scout
  capability: <derived from spec.agents[*].goal + outputs>
  context: <spec.callMeta.prospect + callType>
  signals: { outputs: <from spec.agents[*].outputs[]>,
             inputs: <from spec.agents[*].inputs[]>,
             integrations: <from spec.agents[*].neededTools[]>,
             verbs: <from spec.agents[*].steps[].verb> }
```

The orchestrator passes `priorArt.recommendation.primaryReuse` into Step 3's skill generation prompt: "model the new SKILL.md on `<primaryReuse.ref>`; the existing render.py / output_template.html at that path is the template". The generated assets must cite the prior art they reuse in their own comments (one line at the top: `# Modelled on <ref>`).

If `priorArt.recommendation.noPriorArt == true`, the orchestrator generates from scratch and surfaces the absence in the final report's "Prior art" section so the operator knows this is the first build of this shape.

## Integration with `parse-transcript-to-agent-spec`

The parser can call this skill in its Step 5 (tool classification) to verify: when about to emit `kind: "custom_mcp_to_build"`, first check whether an existing MCP in `vault/projects/*/` does the same thing. If yes, downgrade to `kind: "existing_workspace_mcp"` with `ref` pointing at the vault project and a `bindNote` ("workspace MCP server id needed; if not present, deploy the existing project at `vault/projects/<name>/`"). This avoids the "rebuild the MCP from scratch" failure mode.

## Standalone invocation

```
invoke bap-prior-art-scout
  capability: "audio file uploaded by user, agent transcribes, sends PDF report by email"
  signals: { outputs: ["pdf-attachment", "email"], inputs: ["audio-file"], integrations: ["gmail"] }
```

Returns the ranked list; the operator decides whether to invoke `transcript-to-bap-coworker` with the recommended reuse or to start fresh.

## Anti-patterns

- Returning every coworker in the workspace as a "match". Apply the scoring rubric; below score 4 the match is noise.
- Citing prior art without `file:line` / `@username` / project path. Every `reuseRecipe` must be actionable; "look at batimgie" is not actionable, "copy `vault/projects/batimgie/skill.v2/render.py:120-180` and swap the data schema" is.
- Skipping the parallel-subagents step. A single sequential grep misses cross-source patterns (e.g. a workspace coworker that uses a vault-project MCP).
- Forcing a recommendation when no real match exists. `noPriorArt: true` is a valid output; truly novel builds need to surface that to the operator.
- Running this skill on a one-line "send a slack message" coworker. The scout is for non-trivial builds; for trivial ones it adds latency without signal.
- Letting the scout block the pipeline indefinitely. Cap at `researchTimeCapMinutes` (8 by default); if the cap is hit, return what was collected with `partial: true`.

## Config

`lubin-skills/bap-prior-art-scout/config.yaml`:

```yaml
sources:
  workspace_coworkers:
    enabled: true
    list_limit: 100
  past_builds:
    enabled: true
    root: "~/HeyBap Pipeline/runs"
    lookback_days: 365
  vault_projects:
    enabled: true
    root: "~/Personal Agents/vault/projects"
  fdk_skills:
    enabled: true
    root: "~/Code/forward-deployment-kit/lubin-skills"
  personal_skills:
    enabled: true
    root: "~/.claude/skills"
research_time_cap_minutes: 8
max_results_per_angle: 5
scoring:
  same_surface: 3
  same_integration: 2
  same_input_shape: 2
  same_output_shape: 2
  same_prospect: 1
  recent: 1
match_score_floor: 4
```

Each operator forks the config to match their own paths if their vault / code layout differs.

## See also

- [transcript-to-bap-coworker](../transcript-to-bap-coworker/SKILL.md): primary consumer at Step 1.5.
- [parse-transcript-to-agent-spec](../parse-transcript-to-agent-spec/SKILL.md): can call this skill in Step 5 to verify "custom MCP needed" before committing to building one.
- [build-agents-for-bap](../build-agents-for-bap/SKILL.md): rule on preferring reuse over reinvention.
- [bap-capability-impact-analyzer](../bap-capability-impact-analyzer/SKILL.md): the mirror skill for the analysis side (what to *fix or build new*, not what to *reuse*).
