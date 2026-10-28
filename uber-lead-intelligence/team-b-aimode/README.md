# Lead Research - Team B (AI Mode) — pipeline snapshot

Bap workspace `uber` (`1ff3d15f-484f-412b-8b8a-d4ddc0c7ed08`), coworker `38174930-5ad5-49c7-a46a-01530a3a3134`.
The coworker runs the documents attached to it in Bap; this folder is a versioned copy of what changed on 2026-10-28.

| File | Bap document | Note |
|---|---|---|
| `lead_pipeline_b.py` | `4138de89-d499-40d3-8544-0e06571de3c1` | pipeline, deployed 2026-10-28 09:21 UTC |
| `prompt.md` | coworker prompt | same revision |
| `2026-10-28-owner-recovery.diff` | | diff against the 2026-10-25 version |
| `test_prefill.py` | | checks `clean_ai_text` + `prefill_research` on real AI Mode answers (`repro-aimode.json`, `repro-owner-only.json` are session artifacts, not committed) |

Unchanged documents still live only in Bap: `lead_pipeline.py` (shared Places core), `research_sales.py`, `output.html`.

## 2026-10-28 change: find more owners, clean less

- Digest keeps every AI Mode line, including `Not publicly available (...)`.
- Prefill reads `label: value`, a numbered heading with the value on the next bullet, headings without a colon, and strips `Owned by`.
- Leads whose AI Mode answer names no owner get the existing Exa `operator` search (`FAST_WEB_SECONDS` 60 s); the legacy 120 s `WEB_BUDGET` guard is off in fast mode; refs cap `AI_MODE_REFS + 5` so operator pages reach the digest.
- Coworker allowed the workspace Exa MCP server; prompt lets the agent take the owner from any ref and flags directory (BBB) owners as to confirm.

Measured on Batch 1 (George, 100 leads): named owners 26 → 33, runtime 210 s → 318 s, Exa 44 calls, DataForSEO $1.68. One sample each; AI Mode answers vary between runs.

## Deploying a change

1. `coworkerDocument_read` download → edit → `python -I test_prefill.py lead_pipeline_b.py` (needs the two repro JSON files).
2. `attachment_prepareUpload` (exact size) → `curl -X PUT --upload-file` → `attachment_completeUpload` → `coworkerDocument_save` update with that `fileAssetId`.
3. Run Batch 1 and compare `namedDecisionMakers` in the SUMMARY line.
