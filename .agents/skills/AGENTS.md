# App Agent Instructions

## Package manager and scripts
-  Use `bun`, not `npm`.
-  Use `bun db:push` for migrations, not `db:generate`.
-  When editing a Better Auth plugin, run `bun auth:generate` to regenerate the schema.
-  Run `bun run check` to validate types and lint.

## Testing workflow
-  After implementing a feature, test it with `bun run cmdclaw -- chat` when possible.
-  Example chat validation command: `bun run cmdclaw -- chat --message "what's my latest email on gmail?" --model openai/gpt-5.4`
-  After implementing a coworker feature, or when chat is not enough to cover the user flow, test it with `bun run cmdclaw -- coworker`.
-  Example coworker validation command: `bun run cmdclaw -- coworker create --name "Email Check" --trigger manual --prompt "check my latest email every hour" --auto-approve`
-  If `bun run cmdclaw -- chat` is not sufficient to validate the change, clearly report that limitation. If applicable, say how you would change `cmdclaw chat` to support testing this feature.
-  Don't forget to always typecheck and lint via `bun run check`.
-  After a large codebase change, run `bun run test`.
-  When creating a test, always run it to check if it is correct. Maybe the test uncovers a bug, so stop if you think this is the case and report it to the user.
-  Keep runtime behavior compatible with stateless architecture: do not rely on in-memory state for correctness (execution, approvals, auth, routing, locks, or dedupe). Use durable storage/queue/locks (DB/Redis/BullMQ) as the source of truth.
-  `bun run dev` behavior should stay functionally compatible with stateless architecture (no hidden in-memory-only correctness path in dev).

-  My infra is BullMQ queues and Next.js is on Render

## Dev browser authentication
-  For local browser testing, open `/login?autoLogin=1&callbackUrl=<path>` (for example `/login?autoLogin=1&callbackUrl=%2Fagents`).
-  If it does not log in, make sure the dev server was started with `CMDCLAW_DEV_AUTO_LOGIN=1`.

## Pitfalls
-  Do not add unnecessary environment variables to control behavior; ask the user if you want to add a variable to be sure it is really needed.

## Database
Use `bun run db:push` when you edit schema.ts for my app to use the latest schema changes

## Bun
always use bun not npm or pnpm
