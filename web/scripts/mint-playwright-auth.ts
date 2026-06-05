/**
 * Mint a JWE storageState fixture for Playwright auth-gated tests.
 * Slice 4.4 commit 1 (trip-concierge-p8l).
 *
 * Auth.js v5 (beta-31) uses encrypted JWE (Jose A256CBC-HS512, dir alg)
 * for session cookies. The encryption key is HKDF-derived from
 * NEXTAUTH_SECRET via @panva/hkdf. The JWE protected header carries a
 * JWK thumbprint as `kid`.
 *
 * This script tracks Auth.js's `encode()` in @auth/core/src/jwt.ts
 * exactly. If Auth.js changes the JWE shape between betas, the fixture
 * breaks loudly via auth-fixture-smoke.spec.ts (catches at minted-
 * fixture time rather than at every downstream test).
 *
 * Run via `pnpm mint:auth`. Companion to `seed-e2e-trip.ts` which creates
 * the matching user row.
 */

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

import { hkdf } from "@panva/hkdf";
import { EncryptJWT, base64url, calculateJwkThumbprint } from "jose";

const SEED_USER_ID = "11111111-1111-1111-1111-111111111111";
const SEED_USER_EMAIL = "e2e-test@trip-concierge.local";
const COOKIE_NAME = "authjs.session-token";
const SESSION_LIFETIME_SECONDS = 60 * 60 * 24 * 30;

async function deriveKey(secret: string, salt: string): Promise<Uint8Array> {
  // Matches @auth/core/src/jwt.ts:getDerivedEncryptionKey for A256CBC-HS512.
  return hkdf("sha256", secret, salt, `Auth.js Generated Encryption Key (${salt})`, 64);
}

async function main() {
  const secret = process.env.NEXTAUTH_SECRET ?? "dev-only-do-not-use-in-prod";
  const salt = COOKIE_NAME;
  const encryptionSecret = await deriveKey(secret, salt);

  // Match Auth.js's kid: a JWK thumbprint of the symmetric key.
  const thumbprint = await calculateJwkThumbprint(
    { kty: "oct", k: base64url.encode(encryptionSecret) },
    `sha${encryptionSecret.byteLength << 3}` as "sha512",
  );

  const now = Math.floor(Date.now() / 1000);
  const jwe = await new EncryptJWT({
    // Match the claims our slice 4.1 auth.config.ts session callback writes.
    // session({ session, token }) reads token.userId → session.user.id.
    sub: SEED_USER_ID,
    email: SEED_USER_EMAIL,
    name: "E2E Test User",
    userId: SEED_USER_ID,
  })
    .setProtectedHeader({ alg: "dir", enc: "A256CBC-HS512", kid: thumbprint })
    .setIssuedAt(now)
    .setExpirationTime(now + SESSION_LIFETIME_SECONDS)
    .setJti(crypto.randomUUID())
    .encrypt(encryptionSecret);

  const storageState = {
    cookies: [
      {
        name: COOKIE_NAME,
        value: jwe,
        domain: "localhost",
        path: "/",
        expires: now + SESSION_LIFETIME_SECONDS,
        httpOnly: true,
        secure: false,
        sameSite: "Lax" as const,
      },
    ],
    origins: [],
  };

  const out = resolve(import.meta.dirname, "..", "playwright-auth.json");
  writeFileSync(out, JSON.stringify(storageState, null, 2));
  console.log(`Wrote ${out}`);
  console.log(`Cookie ${COOKIE_NAME} for user ${SEED_USER_ID}, ttl ${SESSION_LIFETIME_SECONDS}s`);
}

main().catch((e) => {
  console.error("mint failed:", e);
  process.exit(1);
});
