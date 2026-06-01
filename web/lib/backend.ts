/**
 * Internal HTTP wrapper for the PWA → backend mint route — slice 4.1 (mvs).
 *
 * Single function: `mintMcpToken({ userId })` POSTs to the backend's
 * `/internal/auth/mint-mcp-token` endpoint with the shared
 * `INTERNAL_AUTH_SECRET` header. Returns the minted JWT.
 *
 * Called from `web/auth.ts`'s signIn callback as a side effect — a
 * mint failure does NOT block sign-in (see auth.ts comment block).
 * The caller is responsible for catching errors and logging with
 * correlation IDs.
 */

import { env } from "@/lib/env";

export interface MintResult {
  mcp_token: string;
  expires_at: string;
}

export async function mintMcpToken({ userId }: { userId: string }): Promise<MintResult> {
  const response = await fetch(`${env.BACKEND_URL}/internal/auth/mint-mcp-token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": env.INTERNAL_AUTH_SECRET,
    },
    body: JSON.stringify({ user_id: userId }),
  });

  if (!response.ok) {
    throw new Error(`mint_mcp_token HTTP ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as MintResult;
}
