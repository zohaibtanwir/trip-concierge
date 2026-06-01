/**
 * Auth.js v5 entry point (NODE runtime) — slice 4.1 (mvs) +
 * edge-middleware-fix.
 *
 * This file is the Node-runtime entry point. It composes the Edge-
 * safe `authConfig` (providers + callbacks) with the PostgreSQL
 * adapter + pg Pool, which are NOT Edge-safe. Anything that needs
 * the database half of Auth.js — route handlers (sign-in/sign-out),
 * server components calling `auth()`, the API route at
 * `app/api/auth/[...nextauth]/route.ts` — imports from here.
 *
 * Middleware does NOT import from this file. Middleware imports
 * `authConfig` directly from `auth.config.ts` and calls
 * `NextAuth(authConfig)` itself to get an Edge-safe wrapper. The
 * pg Pool below would crash the Edge bundle.
 *
 * Two-writers pattern: pg-adapter (running in the Node server)
 * writes to the `users`, `accounts`, and `verification_token`
 * tables in the same Postgres DB the FastAPI backend reads from.
 * The adapter is the authoritative writer for `accounts` and
 * `verification_token`; both adapter and backend touch `users`
 * (adapter on signup; backend on existing flows via SQLAlchemy).
 *
 * Auth.js v5 has been in beta for ~18 months and is the official-
 * docs-recommended path on https://authjs.dev. The 5.0.0-beta.31
 * pin avoids floating-version churn. Watch the authjs/next-auth
 * changelog for the v5.0.0 stable cut and update at that point.
 *
 * Dependency review (slice 4.1 commit 2): @auth/pg-adapter's npm
 * registry shows a single maintainer account. The package is part
 * of the official Auth.js monorepo (Vercel-backed, multi-million
 * weekly downloads); the single account is the org's publishing
 * identity, not an individual project. Reviewed against CLAUDE.md
 * rule 5 ("bus factor of 1 with sensitive scope") and accepted as
 * proceedable. If the maintainership ever appears to genuinely
 * narrow (account changes, prolonged release gap), revisit Path 2
 * custom HTTP adapter.
 */

import PostgresAdapter from "@auth/pg-adapter";
import NextAuth from "next-auth";
import Resend from "next-auth/providers/resend";
import { Pool } from "pg";

import { authConfig, sendMagicLink } from "@/auth.config";
import { env } from "@/lib/env";

export { authConfig, sendMagicLink } from "@/auth.config";

// Pool construction is lazy — pg's `new Pool()` does not connect
// until the first query.
const pool = new Pool({ connectionString: env.DATABASE_URL });

// Resend provider lives here, NOT in authConfig. Auth.js refuses to
// initialize an Email provider without an adapter; the adapter only
// lives in Node runtime. Middleware uses authConfig (Google-only)
// to stay Edge-safe.
export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  adapter: PostgresAdapter(pool),
  providers: [
    ...authConfig.providers,
    Resend({
      apiKey: env.RESEND_API_KEY,
      from: env.RESEND_FROM_EMAIL,
      sendVerificationRequest: sendMagicLink,
    }),
  ],
});
