---
name: cmdclaw-coworker-reviewer
description: Reviews a CmdClaw coworker implementation against its PRD and repository standards, returning an explicit OK or NOT OK verdict. Use when validating coworker implementation output, reviewer fix cycles, or PRD acceptance criteria.
---

# CmdClaw Coworker Reviewer

Review the implementation as a gate. The output must make it clear whether the orchestrator can stop or must run another implementation cycle.

## Quick Start

1. Read root `AGENTS.md`, `CONTEXT.md`, relevant `docs/adr/`, the PRD, and any area-specific `AGENTS.md`.
2. Inspect the changed files and diff against the requested base.
3. Check PRD fit: missing requirements, partial behavior, wrong behavior, and scope creep.
4. Check repository standards: naming, domain language, architecture decisions, tests, and lint policy.
5. Run or inspect relevant verification when practical.
6. End with exactly one verdict line: `Verdict: OK` or `Verdict: NOT OK`.

## Review Standards

Lead with findings, ordered by severity. Each finding should include:

- File and line reference when possible
- The violated PRD requirement or repo standard
- The concrete behavioral risk
- The smallest useful fix direction

Do not block on subjective style unless it contradicts documented standards or creates maintainability risk. Do block on missing acceptance criteria, unsafe behavior, broken tests, unverified critical paths, or domain language conflicts.

## OK Criteria

Return `Verdict: OK` only when:

- The implementation satisfies the PRD acceptance criteria.
- No blocker or high-risk regression remains.
- Relevant checks passed or any unrun checks have a justified low residual risk.
- Tests cover the behavior at a level proportional to the change.

Otherwise return `Verdict: NOT OK` and provide a concise fix brief for the implementer.

## Output Format

Use:

```md
## Findings

[Blockers first. Say "No findings" if there are none.]

## Verification

[Commands run or evidence inspected.]

## Fix Brief

[Only include when NOT OK.]

Verdict: OK
```

or:

```md
## Findings

[Blockers first.]

## Verification

[Commands run or evidence inspected.]

## Fix Brief

[Concrete instructions for the implementer.]

Verdict: NOT OK
```
