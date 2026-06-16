---
name: build-mcp-for-bap
description: |
  Build a custom MCP server (HTTP + JSON-RPC over Streamable HTTP) compatible with Bap (Heybap) workspace MCPs.
  Deploys to Vercel by default with the `mcp-handler` library, exposes one or more tools, and supports the
  four Bap auth modes: none / bearer / api_key / oauth2. Use this skill when the user asks to "build an MCP",
  "expose a tool to Bap", "create a custom MCP server", "add an MCP for X service", or wants to integrate a
  third-party API into a Bap coworker.
---

# Build an MCP for Bap (Heybap)

A Bap workspace MCP is a remote HTTP endpoint that exposes one or more tools to a coworker. Bap reads `tools/list` and calls `tools/call` over JSON-RPC 2.0 with Streamable HTTP transport. The user adds the endpoint URL in Bap → Workspace settings → MCP servers, picks an auth mode, and the tools become available to any coworker that allows the server.

This skill covers the full lifecycle: scaffolding, implementing tools, picking the right auth mode, deploying to Vercel, and registering in Bap.

## Decision flow before writing code

1. **What tool(s) do we expose?** Name them and define the inputs/outputs. One MCP can host many tools; group by domain (e.g. one MCP for "transcription", one for "calendar admin", etc.).
2. **Auth mode** — pick BEFORE coding:
   - **`none`** — Anyone with the URL can call. Use only for safe, idempotent, free operations.
   - **`bearer`** *(default recommendation)* — Single static token in env var. Simple, secure enough for internal tooling. Bap UI: paste the token once.
   - **`api_key`** — Same as bearer but token goes in custom header or query param. Use if the upstream service expects an API key passthrough.
   - **`oauth2`** — Full OAuth 2.0 with `.well-known/oauth-protected-resource` + `.well-known/oauth-authorization-server` discovery. Heavy. Only do this if the MCP itself proxies a per-user OAuth-protected resource (e.g. user-scoped Gmail). For shared/server-side credentials, use `bearer`.
3. **Latency profile** — Vercel Hobby caps function `maxDuration` at 300s. If the tool needs longer (heavy LLM, large file processing), either chunk + parallelize, queue + poll, or move to Vercel Pro.
4. **Reuse** — Will other coworkers/projects use this MCP? If yes, give it a generic name (e.g. `hyperstack-transcribe`, not `batimgie-transcribe`) and put the project in the org's Vercel + Git.

## Scaffold (Vercel + Next.js + mcp-handler)

```
my-mcp/
├── package.json
├── tsconfig.json
├── next.config.mjs        # serverExternalPackages for any native deps
├── vercel.json            # maxDuration + memory
├── app/api/mcp/route.ts   # the MCP endpoint
└── README.md
```

### `package.json`

```json
{
  "name": "my-mcp",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "mcp-handler": "^1.0.0",
    "next": "^15.3.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "zod": "^3.24.0"
  },
  "devDependencies": {
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "typescript": "^5.7.0"
  }
}
```

Don't add the pnpm `packageManager` field if you'll deploy from Vercel; use `npm install` to keep CI/CD simple.

### `next.config.mjs`

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  // Only needed when bundling native node modules (ffmpeg, sharp, etc.)
  serverExternalPackages: ["@ffmpeg-installer/ffmpeg"],
  outputFileTracingIncludes: {
    "/api/mcp": ["./node_modules/@ffmpeg-installer/**/*"],
  },
};
export default nextConfig;
```

### `vercel.json`

```json
{
  "functions": {
    "app/api/mcp/route.ts": {
      "maxDuration": 300,
      "memory": 2048
    }
  }
}
```

Memory cap is 2048 MB on Hobby. `maxDuration` is 300s on Hobby, up to 800s on Pro.

### `tsconfig.json`

Standard Next 15 + app router config. The Next.js scaffold output is the source of truth.

## The MCP endpoint

`app/api/mcp/route.ts`:

```ts
import { createMcpHandler } from "mcp-handler";
import { z } from "zod";

const handler = createMcpHandler(
  (server) => {
    server.tool(
      "my_tool_name",                                  // tool identifier the LLM calls
      "Short description telling the LLM when to use this tool.",
      {
        someArg: z.string().describe("Plain-English description for the LLM."),
        optionalArg: z.number().optional().describe("..."),
      },
      async ({ someArg, optionalArg }) => {
        // Your business logic here. Throw to return an error.
        const result = await doWork(someArg, optionalArg);
        return {
          content: [{ type: "text", text: result }],
        };
      }
    );
    // Add as many server.tool(...) calls as you want.
  },
  {},                            // server options
  { basePath: "/api" }           // must match the route folder
);

export { handler as GET, handler as POST, handler as DELETE };
```

### Bearer auth wrapper (recommended default)

Wrap the handler before exporting so the token is checked on every request:

```ts
function withBearerAuth(
  inner: (req: Request) => Promise<Response> | Response
): (req: Request) => Promise<Response> {
  return async (req: Request) => {
    const expected = process.env.MCP_BEARER_TOKEN;
    if (expected) {
      const got = req.headers.get("authorization") || "";
      const ok = got === `Bearer ${expected}` || got === expected;
      if (!ok) {
        return new Response(JSON.stringify({ error: "unauthorized" }), {
          status: 401,
          headers: {
            "Content-Type": "application/json",
            "WWW-Authenticate": 'Bearer realm="my-mcp"',
          },
        });
      }
    }
    return inner(req);
  };
}

const guarded = withBearerAuth(handler);
export { guarded as GET, guarded as POST, guarded as DELETE };
```

Note the env var check: if `MCP_BEARER_TOKEN` is unset, the wrapper falls through (useful for local dev with `pnpm dev`). In production, always set it.

### Streaming long responses

If the tool produces incremental output (e.g. video processing progress), use the `server.tool` callback's progress reporting (see `mcp-handler` docs). Most tools should just return text at the end — simpler and works fine for sub-300s operations.

### Native binaries (ffmpeg, sharp, etc.)

If you need a native binary on Vercel Functions:
1. Add the npm wrapper that bundles per-arch binaries: `@ffmpeg-installer/ffmpeg`, `sharp`, etc.
2. Add it to `serverExternalPackages` in `next.config.mjs`.
3. Add the directory to `outputFileTracingIncludes` so Vercel ships it.
4. The runtime is Linux x64 — verify the wrapper has that target installed (`node_modules/@ffmpeg-installer/linux-x64/` should exist after `npm install`).

## Deploy to Vercel

```bash
vercel link --yes --project my-mcp                    # one-time
echo "$TOKEN" | vercel env add MCP_BEARER_TOKEN production
vercel deploy --prod --yes
```

Generate the token once:
```bash
openssl rand -hex 32                                  # → 064c...e2c, save it for Bap
```

After deploy, **disable Vercel SSO protection** (default on Hobby personal projects):

```bash
vercel project protection disable --sso
```

Without this step, every MCP request returns the Vercel auth HTML page → Bap can't reach the JSON-RPC handler.

Get the stable URL:
```bash
vercel inspect <latest-deployment> | grep -A 5 Aliases
# → https://my-mcp.vercel.app
```

The MCP endpoint is `https://my-mcp.vercel.app/api/mcp`.

## Register in Bap

Workspace admin → **MCP servers** → **Add new** → fill:

| Field | Value |
|---|---|
| **Name** | Anything human-readable |
| **URL** | `https://my-mcp.vercel.app/api/mcp` |
| **Auth** | **Pick `Bearer token`** (Bap's UI defaults to OAuth — change it!) |
| **Header name** | `Authorization` (default) |
| **Prefix** | `Bearer ` (default — keep the trailing space) |
| **Secret / Token** | Paste the `openssl rand -hex 32` token |

Save. The status should immediately flip to `Connected`. Enable the MCP for the specific coworker(s) that should use it.

### Common Bap UI gotcha

The UI defaults `authType` to `oauth2` (cf. `apps/web/src/components/executor-source-form.tsx:80-96` in the bap repo). If you forget to change it and click "Connect OAuth", Bap fails with an internal 500 because it tries to fetch `.well-known/oauth-protected-resource` on your MCP (which doesn't exist). **Always change the Auth dropdown before saving.**

## Smoke-test the MCP from the terminal

```bash
TOKEN="..."  # the value you stored in MCP_BEARER_TOKEN

# 1. initialize (creates a session)
SID=$(curl -s -i -X POST https://my-mcp.vercel.app/api/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' \
  | grep -i mcp-session-id | tr -d '\r' | awk '{print $2}')

# 2. notify initialized
curl -s -X POST https://my-mcp.vercel.app/api/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "mcp-session-id: $SID" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' > /dev/null

# 3. list tools
curl -s -X POST https://my-mcp.vercel.app/api/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "mcp-session-id: $SID" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | sed 's/event: message//; s/^data: //'

# 4. call a tool
curl -s -X POST https://my-mcp.vercel.app/api/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "mcp-session-id: $SID" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"my_tool_name","arguments":{"someArg":"hello"}}}' \
  | sed 's/event: message//; s/^data: //'
```

A 401 from step 1 means the bearer header is wrong. A successful step 3 returns `{"result":{"tools":[...]}}` — those are the tools that will appear in the coworker.

## Bap auth modes — implementation cheat-sheet

| Mode | When to use | Server-side check |
|---|---|---|
| `none` | Tool is safe + free for anyone (e.g. read-only public data lookup) | None |
| `bearer` | Default for internal MCPs **if** the Bap UI shows the auth dropdown | `Authorization: Bearer <token>` |
| `api_key` | Upstream API expects key in header/query | Custom header/query check |
| `oauth2` | UI hides the dropdown (only "Connect OAuth" button) OR per-user OAuth needed | Full RFC 8414 + RFC 9728 discovery + auto-approve flow |

### Real-world gotcha: some Bap UIs hide the auth dropdown

Depending on the workspace config (`fixedMcpAuthType` server flag), the "Add MCP" form may only ask for a URL, and the resulting MCP fiche only shows a "Connect OAuth" button — no Bearer or No-auth alternative. In that case Bearer is impossible without intervention from a Bap admin. **You must implement OAuth 2.0 on your MCP.**

The good news: you don't need real user-scoped OAuth. You can implement an **auto-approving OAuth 2.0** that, behind the scenes, hands out a single shared bearer token. The flow goes through Bap's OAuth machinery (so the UI is happy) without ever showing a consent screen.

### The auto-approving OAuth 2.0 pattern

You need 5 endpoints. The full implementation is in the reference repo (`hyperstack-transcribe`). Summary:

```
/.well-known/oauth-protected-resource           (GET)  → { authorization_servers: [<origin>], scopes_supported: ["mcp"] }
/.well-known/oauth-authorization-server         (GET)  → RFC 8414 metadata
/oauth/register                                  (POST) → echo {client_id, ...}, public client, no secret
/oauth/authorize?response_type=code&...          (GET)  → 302 to redirect_uri with code=<JWT> (auto-approve, NO consent screen)
/oauth/token                                     (POST) → verify PKCE → return { access_token: <static bearer> }
```

Key design choices that make this small:

1. **JWT-signed authorization code** — stateless. Sign with HS256 using `MCP_BEARER_TOKEN` as the secret. Payload: `{ redirect_uri, code_challenge, code_challenge_method, scope, jti, exp }`. 10 min TTL.
2. **Auto-approve** — `/oauth/authorize` does NOT show a login or consent page; it immediately 302-redirects with a signed code. This is safe because the static bearer is server-only, the client never sees the real secret.
3. **PKCE verification at /oauth/token** — `sha256(code_verifier) base64url === code_challenge`. Standard. Reject if mismatch or redirect_uri changed.
4. **access_token == your static MCP_BEARER_TOKEN** — every successful OAuth flow returns the same shared bearer. Your `/api/mcp` keeps the simple Bearer middleware.
5. **`token_endpoint_auth_method: "none"`** — public client, no client_secret. Bap uses this mode by default.
6. **Dynamic Client Registration** — Bap doesn't strictly need it, but expose `/oauth/register` anyway since some Bap versions probe it. Just echo back the requested fields with a generated `client_id`.

### Implementation files (copy-paste from `hyperstack-transcribe`)

```
app/
├── api/mcp/route.ts                           (your MCP handler, wrapped with bearer middleware)
├── .well-known/
│   ├── oauth-protected-resource/route.ts      (RFC 9728 metadata)
│   └── oauth-authorization-server/route.ts    (RFC 8414 metadata)
└── oauth/
    ├── authorize/route.ts                      (signs JWT code, redirects)
    ├── token/route.ts                          (verifies PKCE, returns bearer)
    └── register/route.ts                       (DCR echo)
lib/
└── oauth.ts                                    (signCode, verifyCode, verifyPkce helpers using jose)
```

Add `jose` to dependencies for JWT signing:
```bash
npm install jose
```

The `/oauth/authorize` route is the magic — it just signs a code and 302s back. Skeleton:

```ts
import { signCode } from "@/lib/oauth";
import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const redirectUri = url.searchParams.get("redirect_uri")!;
  const state = url.searchParams.get("state") || "";
  const codeChallenge = url.searchParams.get("code_challenge")!;
  const codeChallengeMethod = (url.searchParams.get("code_challenge_method") || "S256") as "S256" | "plain";

  const code = await signCode({
    redirect_uri: redirectUri,
    code_challenge: codeChallenge,
    code_challenge_method: codeChallengeMethod,
    client_id: url.searchParams.get("client_id") || "anonymous",
    scope: url.searchParams.get("scope") || "mcp",
  });

  const target = new URL(redirectUri);
  target.searchParams.set("code", code);
  if (state) target.searchParams.set("state", state);
  return NextResponse.redirect(target.toString(), 302);
}
```

`/oauth/token` verifies and returns the static bearer:

```ts
import { verifyCode, verifyPkce, getAccessToken } from "@/lib/oauth";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  // Bap sends application/x-www-form-urlencoded
  const text = await req.text();
  const body = Object.fromEntries(new URLSearchParams(text));

  if (body.grant_type === "refresh_token") {
    return NextResponse.json({
      access_token: getAccessToken(),
      token_type: "Bearer",
      expires_in: 31536000,
      refresh_token: body.refresh_token,
      scope: "mcp",
    });
  }

  if (body.grant_type !== "authorization_code") {
    return NextResponse.json({ error: "unsupported_grant_type" }, { status: 400 });
  }

  const payload = await verifyCode(body.code);
  if (payload.redirect_uri !== body.redirect_uri) {
    return NextResponse.json({ error: "invalid_grant" }, { status: 400 });
  }
  if (!verifyPkce(body.code_verifier, payload.code_challenge, payload.code_challenge_method)) {
    return NextResponse.json({ error: "invalid_grant", error_description: "PKCE mismatch" }, { status: 400 });
  }

  return NextResponse.json({
    access_token: getAccessToken(),
    token_type: "Bearer",
    expires_in: 31536000,
    refresh_token: getAccessToken(),
    scope: payload.scope || "mcp",
  });
}
```

The `lib/oauth.ts` helpers (signCode/verifyCode using `jose`, verifyPkce using node crypto sha256) are ~30 lines. See the `hyperstack-transcribe` reference.

### How Bap consumes the OAuth flow

1. User adds the MCP URL in Bap UI (URL only — no auth dropdown shown).
2. Bap fetches `/.well-known/oauth-protected-resource` and `/.well-known/oauth-authorization-server`.
3. Bap POST `/oauth/register` (optional discovery, your endpoint echoes back).
4. User clicks **Connect OAuth** in the Bap fiche → Bap opens a popup to your `/oauth/authorize?...&code_challenge=...`.
5. Your endpoint auto-302s back to Bap's `{APP_URL}/api/oauth/callback?code=<JWT>&state=...`.
6. Bap exchanges at your `/oauth/token` with PKCE verifier → receives the static bearer.
7. Bap stores the bearer in `workspaceMcpAuthorization.accessToken` and uses it on every `/api/mcp` call.
8. Status flips to `Connected`. The user never sees a consent screen because step 4→5 is instant.

### Bap redirect URI

Bap uses a fixed redirect URI of the shape `{APP_URL}/api/oauth/callback`. Your `/oauth/authorize` must accept arbitrary `redirect_uri` values (don't whitelist) since `APP_URL` varies per Bap deployment. The JWT-signed code binds the redirect_uri so it can't be tampered with at the token exchange step.

## Pitfalls

- **Forgot to disable Vercel SSO** → all requests return HTML auth page. Run `vercel project protection disable --sso`.
- **Wrong basePath** in `createMcpHandler` → 404. The third arg `basePath` must match the route folder (`/api` if the route file is at `app/api/mcp/route.ts`).
- **Native binary path errors at runtime** (`Cannot find module '@ffmpeg-installer/...'`) → missing `outputFileTracingIncludes` in `next.config.mjs`.
- **Tool not appearing in coworker** → check that the workspace MCP is enabled for THAT specific coworker (per-coworker toggle).
- **Token won't validate** → the bearer wrapper does an exact-string equality. Make sure the env var has no trailing newline (Vercel CLI auto-strips it but check).
- **maxDuration too short** → Vercel cancels at 300s on Hobby. For longer operations, parallelize internally or upgrade to Pro (800s).
- **Bap UI only shows "Connect OAuth"** (no auth dropdown) → workspace has `fixedMcpAuthType` enabled. Implement the auto-approving OAuth pattern above. Do NOT wait for a Bap UI fix — your MCP just needs the 5 OAuth endpoints to be unblocked.
- **OAuth flow returns 500 on Connect OAuth** → your `.well-known/oauth-*` endpoints aren't reachable (likely SSO still on, or the routes are in `app/api/.well-known/` instead of `app/.well-known/`). The discovery endpoints MUST be at the origin root.
- **OAuth code exchange fails with "invalid_grant"** → check PKCE: `sha256(verifier)` base64url-encoded (no padding) must equal `code_challenge`. Common bug: using base64 instead of base64url.

## When NOT to build an MCP

- The tool is a one-off used by a single coworker → use a skill with embedded Python/bash instead, runs in the sandbox.
- The data fits in a coworker document (PDF, CSV, image, txt) → upload it directly.
- The "tool" is a fixed answer / template → use a skill, not an MCP.

MCPs are best when **multiple coworkers** call the same logic, or when the logic requires **secrets that shouldn't be in the coworker's sandbox** (e.g. paid API keys).

## Reference implementation

The `hyperstack-transcribe` MCP is the canonical reference for this skill — single-tool MCP (audio URL → text via Groq Whisper), Bearer auth, native ffmpeg, deployed on Vercel Hobby. Code: https://github.com/lubindanilo/hyperstack-transcribe (or wherever the user has it).
