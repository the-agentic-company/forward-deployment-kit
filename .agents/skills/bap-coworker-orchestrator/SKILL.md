---
name: bap-coworker-orchestrator
description: Orchestrates a Bap coworker build loop by grilling the user into a PRD, spawning implementer and reviewer sub-agents, and iterating until review accepts the output. Use when building or refining a Bap coworker from an idea, PRD, or unclear feature request.
---

# Bap Coworker Orchestrator

Turn an unclear coworker request into an implemented, reviewed result. Own the loop end to end: clarify, document, delegate implementation, delegate review, and repeat until the reviewer says the output is okay.

## Quick Start

1. Read the repo guidance: root `AGENTS.md`, `CONTEXT.md`, relevant `docs/adr/`, and any area-specific `AGENTS.md`.
2. Interview like `grill-with-docs`: ask one question at a time, give a recommended answer, and wait for the user before continuing.
3. If a question can be answered from code or docs, inspect those instead of asking.
4. Create or update a PRD under `docs/prd/` using the repo's `to-prd` style.
5. Spawn a worker sub-agent using `bap-coworker-implementer` to implement the PRD.
6. Spawn a reviewer sub-agent using `bap-coworker-reviewer` to review the implementation against the PRD and repo standards.
7. If the reviewer rejects the output, send the findings back to an implementer and repeat.
8. Stop only when the reviewer explicitly says the output is okay.

## Interview Rules

- Ask exactly one decision question at a time.
- Include a recommended answer and why it fits the current codebase.
- Prefer codebase exploration over questions when the answer is discoverable.
- Challenge vague or conflicting language against `CONTEXT.md`.
- Capture resolved domain terms in `CONTEXT.md` immediately, keeping it a glossary only.
- Offer an ADR only for decisions that are hard to reverse, surprising without context, and based on a real trade-off.

## PRD Requirements

The PRD must include:

- Problem statement
- User-facing solution
- Extensive user stories
- Implementation decisions
- Testing decisions
- Out of scope
- Further notes

Use Bap glossary terms from `CONTEXT.md`. Do not include brittle file paths unless they are needed to identify a concrete implementation target.

## Delegation Loop

Use sub-agents only after the PRD is clear enough to implement.

### Implementer Prompt Shape

Pass the PRD path, relevant docs, acceptance criteria, and ownership scope. Require the implementer to:

- Use `bap-coworker-implementer`
- Edit files directly
- Avoid reverting unrelated changes
- Run relevant checks
- Report changed files, checks run, and any blockers

### Reviewer Prompt Shape

Pass the PRD path, implementation summary, changed files, and comparison base. Require the reviewer to:

- Use `bap-coworker-reviewer`
- Review standards and PRD fit
- Lead with blockers
- End with exactly one verdict: `OK` or `NOT OK`

## Stop Condition

- If the reviewer says `OK`, summarize the final implementation and verification.
- If the reviewer says `NOT OK`, create a concise fix brief and run another implementer/reviewer cycle.
- Do not declare success based only on passing tests; the reviewer must accept the output.
