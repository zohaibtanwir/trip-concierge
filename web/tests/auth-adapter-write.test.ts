// @vitest-environment node
/**
 * Integration test: @auth/pg-adapter writes against the real schema.
 *
 * THIS TEST EXISTS TO CATCH "Concern #1" FROM PR #32 REVIEW. The
 * adapter hardcodes camelCase column names + a singular table name
 * (`verification_token`) and provides NO column-aliasing API. The
 * earlier auth-config.test.ts asserted only that the adapter was
 * defined — it did not exercise the adapter's write path. This test
 * fills that gap by exercising createUser, linkAccount, and
 * createVerificationToken against a real Postgres test DB.
 *
 * Uses `@vitest-environment node` (not jsdom) so pg can open TCP
 * sockets. Skips cleanly when the test DB is unreachable (e.g.,
 * developer doesn't have docker running). CI provisions Postgres
 * via the same compose file backend tests use; this test runs there.
 *
 * Lessons banked in experiments/01-langfuse.md ("Slice 4.1 PR #32
 * review, Concern #1").
 */

import PostgresAdapter from "@auth/pg-adapter";
import { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// Derive the Adapter type from PostgresAdapter's return type so we
// don't need a direct @auth/core dev-dependency just for the type.
type Adapter = ReturnType<typeof PostgresAdapter>;

const TEST_DB_URL =
  process.env.TEST_DATABASE_URL ??
  "postgresql://postgres:postgres@localhost:5432/trip_concierge_test";

interface State {
  pool: Pool | null;
  adapter: Adapter | null;
  reachable: boolean;
}

const state: State = { pool: null, adapter: null, reachable: false };

beforeAll(async () => {
  state.pool = new Pool({ connectionString: TEST_DB_URL, connectionTimeoutMillis: 5000 });
  try {
    await state.pool.query("SELECT 1");
    state.reachable = true;
    state.adapter = PostgresAdapter(state.pool);
  } catch (err) {
    state.reachable = false;
    // Surface why the test DB is unreachable so a developer can fix
    // the env (most often: docker not running, or wrong TEST_DATABASE_URL).
    console.warn(`[auth-adapter-write] test DB unreachable: ${String(err)}`);
  }
});

afterAll(async () => {
  if (state.pool) {
    await state.pool.end();
  }
});

interface ReadyContext {
  pool: Pool;
  adapter: {
    createUser: NonNullable<Adapter["createUser"]>;
    linkAccount: NonNullable<Adapter["linkAccount"]>;
    createVerificationToken: NonNullable<Adapter["createVerificationToken"]>;
  };
}

function readyContext(): ReadyContext | null {
  if (!state.reachable || !state.pool || !state.adapter) {
    console.warn("skipped: test DB unreachable");
    return null;
  }
  const { createUser, linkAccount, createVerificationToken } = state.adapter;
  if (!createUser || !linkAccount || !createVerificationToken) {
    console.warn("skipped: adapter missing required method");
    return null;
  }
  return {
    pool: state.pool,
    adapter: { createUser, linkAccount, createVerificationToken },
  };
}

describe("pg-adapter writes against real schema", () => {
  it("createUser writes to users table with emailVerified column populated", async () => {
    const ctx = readyContext();
    if (!ctx) return;
    const email = `adapter-${Date.now()}-${Math.random()}@test.com`;
    const verifiedAt = new Date();
    const created = await ctx.adapter.createUser({
      id: "ignored-by-adapter",
      name: "Adapter Test",
      email,
      emailVerified: verifiedAt,
      image: null,
    });

    expect(created.id).toBeTruthy();
    expect(created.email).toBe(email);

    const row = await ctx.pool.query(
      'SELECT id, email, "emailVerified", image FROM users WHERE email = $1',
      [email],
    );
    expect(row.rowCount).toBe(1);
    expect(row.rows[0].emailVerified).toBeInstanceOf(Date);
  });

  it("linkAccount writes to accounts table with userId + providerAccountId", async () => {
    const ctx = readyContext();
    if (!ctx) return;
    const email = `link-${Date.now()}-${Math.random()}@test.com`;
    const user = await ctx.adapter.createUser({
      id: "ignored",
      name: "Link Test",
      email,
      emailVerified: new Date(),
      image: null,
    });

    const providerAccountId = `pa-${Date.now()}`;
    await ctx.adapter.linkAccount({
      userId: user.id,
      type: "oauth",
      provider: "google",
      providerAccountId,
      access_token: "at",
      refresh_token: "rt",
      expires_at: 9999999999,
      token_type: "bearer",
      scope: "openid email",
      id_token: "id",
      session_state: null,
    });

    const row = await ctx.pool.query(
      'SELECT "userId", provider, "providerAccountId" FROM accounts WHERE "providerAccountId" = $1',
      [providerAccountId],
    );
    expect(row.rowCount).toBe(1);
    expect(row.rows[0].userId).toBe(user.id);
    expect(row.rows[0].provider).toBe("google");
  });

  it("createVerificationToken writes to verification_token table (singular)", async () => {
    const ctx = readyContext();
    if (!ctx) return;
    const identifier = `vt-${Date.now()}-${Math.random()}@test.com`;
    const token = `tok-${Date.now()}`;
    const expires = new Date(Date.now() + 24 * 3600 * 1000);

    const created = await ctx.adapter.createVerificationToken({
      identifier,
      token,
      expires,
    });
    expect(created?.token).toBe(token);

    const row = await ctx.pool.query(
      "SELECT identifier, token, expires FROM verification_token WHERE token = $1",
      [token],
    );
    expect(row.rowCount).toBe(1);
    expect(row.rows[0].identifier).toBe(identifier);
  });
});
