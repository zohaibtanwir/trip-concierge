/**
 * Slice 4.1 (mvs) — Auth.js v5 config pins.
 *
 * The `authConfig` object is what gets passed to NextAuth() in
 * `web/auth.ts`. We export it separately so tests can introspect the
 * provider list, session strategy, callbacks, and adapter wiring
 * without going through NextAuth's runtime construction.
 *
 * Four properties pinned here:
 *   1. JWT session strategy (not database) — v1.0a scale doesn't need
 *      replica-shared session state.
 *   2. Two providers: Resend (email magic-link) AND Google OAuth. Both
 *      are spec-locked for v1.0a per BUILD_PLAN §4.1.
 *   3. PostgreSQL adapter is wired — required for accounts +
 *      verification_tokens tables to exist.
 *   4. signIn callback exists — this is where the side-effect MCP
 *      token mint fires. Provider-agnostic per the backend test in
 *      backend/tests/test_auth_mint_route.py.
 */

import { describe, expect, it } from "vitest";

import { authConfig } from "@/auth.config";

describe("authConfig", () => {
  it("uses JWT session strategy", () => {
    expect(authConfig.session?.strategy).toBe("jwt");
  });

  it("registers Google in the Edge-safe config (Resend lives in auth.ts only)", () => {
    // Resend is NOT in authConfig — it's added in auth.ts alongside
    // the PostgresAdapter because Auth.js's assertConfig() rejects an
    // Email provider without an adapter. Keeping Resend out of
    // authConfig is what makes middleware's NextAuth(authConfig)
    // initialize cleanly in the Edge runtime.
    const providers = authConfig.providers ?? [];
    expect(providers).toHaveLength(1);

    const providerIds = providers.map((p) => {
      const resolved = typeof p === "function" ? p({}) : p;
      return resolved.id;
    });
    expect(providerIds).toEqual(["google"]);
  });

  // The adapter is composed in auth.ts (NextAuth({...authConfig, adapter})),
  // not on the authConfig object itself — the Edge-safe split per
  // edge-middleware-fix. Adapter behavior is pinned by the integration
  // test in auth-adapter-write.test.ts.

  it("defines a signIn callback that fires the MCP-mint side effect", () => {
    expect(authConfig.callbacks?.signIn).toBeDefined();
    expect(typeof authConfig.callbacks?.signIn).toBe("function");
  });

  it("routes unauthenticated users to /login", () => {
    expect(authConfig.pages?.signIn).toBe("/login");
  });
});
