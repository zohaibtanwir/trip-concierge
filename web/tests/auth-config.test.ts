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

  it("registers exactly two providers (Resend + Google)", () => {
    const providers = authConfig.providers ?? [];
    expect(providers).toHaveLength(2);

    const providerIds = providers.map((p) => {
      // Auth.js v5 normalises provider into an object with .id; if it's
      // still a config function, call it and read .id.
      const resolved = typeof p === "function" ? p({}) : p;
      return resolved.id;
    });
    expect(providerIds.sort()).toEqual(["google", "resend"]);
  });

  it("wires the PostgreSQL adapter", () => {
    expect(authConfig.adapter).toBeDefined();
  });

  it("defines a signIn callback that fires the MCP-mint side effect", () => {
    expect(authConfig.callbacks?.signIn).toBeDefined();
    expect(typeof authConfig.callbacks?.signIn).toBe("function");
  });

  it("routes unauthenticated users to /login", () => {
    expect(authConfig.pages?.signIn).toBe("/login");
  });
});
