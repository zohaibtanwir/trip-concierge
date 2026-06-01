/**
 * Auth.js v5 entry point — slice 4.1 (mvs).
 *
 * This file calls `NextAuth(authConfig)` which pulls in Next.js's
 * server-side APIs (next/server). Pure config + callbacks live in
 * `auth.config.ts` so middleware (Edge runtime) and tests can import
 * the config without dragging in next/server.
 *
 * Two-writers pattern: the PostgreSQL adapter inside authConfig
 * writes to the `users`, `accounts`, and `verification_tokens`
 * tables in the same Postgres DB the FastAPI backend reads from. The
 * adapter is the authoritative writer for `accounts` and
 * `verification_tokens`; both adapter and backend touch `users`
 * (adapter on signup; backend on existing flows via SQLAlchemy).
 *
 * Auth.js v5 has been in beta for ~18 months and is the official-
 * docs-recommended path on https://authjs.dev. The 5.0.0-beta.31
 * pin avoids floating-version churn. Watch the authjs/next-auth
 * changelog for the v5.0.0 stable cut and update at that point.
 *
 * Dependency review (slice 4.1 commit 2): @auth/pg-adapter's npm
 * registry shows a single maintainer account. The package is part of
 * the official Auth.js monorepo (Vercel-backed, multi-million
 * weekly downloads); the single account is the org's publishing
 * identity, not an individual project. Reviewed against CLAUDE.md
 * rule 5 ("bus factor of 1 with sensitive scope") and accepted as
 * proceedable. If the maintainership ever appears to genuinely
 * narrow (account changes, prolonged release gap), revisit Path 2
 * custom HTTP adapter.
 */

import NextAuth from "next-auth";

import { authConfig } from "@/auth.config";

export { authConfig, sendMagicLink } from "@/auth.config";

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
