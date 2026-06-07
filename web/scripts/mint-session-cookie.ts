/**
 * Mint a one-shot Auth.js v5 JWE session cookie for a given user.
 * Sunday morning UI smoke handoff — adapted from mint-playwright-auth.ts.
 *
 * Usage:
 *   pnpm tsx web/scripts/mint-session-cookie.ts <user-id> <email>
 *
 * Prints the cookie value + paste instructions to stdout. Does NOT write
 * to playwright-auth.json (that's the fixture path); this is for human
 * paste into Chrome DevTools.
 *
 * Auth.js v5 (beta-31) JWE shape:
 * - alg: dir, enc: A256CBC-HS512
 * - kid: JWK thumbprint of HKDF-derived encryption key
 * - claims: { sub, email, name, userId } — matches what slice 4.1's
 *   auth.config.ts session callback reads (token.userId → session.user.id)
 *
 * NEXTAUTH_SECRET fallback to "dev-only-do-not-use-in-prod" — matches
 * web/lib/env.ts's identical fallback, so the cookie this script mints
 * is byte-compatible with whatever the dev server uses (since neither
 * side sees a real NEXTAUTH_SECRET in the current local env).
 */

import { hkdf } from "@panva/hkdf";
import { EncryptJWT, base64url, calculateJwkThumbprint } from "jose";

const COOKIE_NAME = "authjs.session-token";
const SESSION_LIFETIME_SECONDS = 60 * 60 * 24 * 30;

async function deriveKey(secret: string, salt: string): Promise<Uint8Array> {
  return hkdf("sha256", secret, salt, `Auth.js Generated Encryption Key (${salt})`, 64);
}

async function main() {
  const userId = process.argv[2];
  const email = process.argv[3];
  if (!userId || !email) {
    console.error("Usage: pnpm tsx web/scripts/mint-session-cookie.ts <user-id> <email>");
    process.exit(2);
  }

  const secret = process.env.NEXTAUTH_SECRET ?? "dev-only-do-not-use-in-prod";
  const salt = COOKIE_NAME;
  const encryptionSecret = await deriveKey(secret, salt);

  const thumbprint = await calculateJwkThumbprint(
    { kty: "oct", k: base64url.encode(encryptionSecret) },
    `sha${encryptionSecret.byteLength << 3}` as "sha512",
  );

  const now = Math.floor(Date.now() / 1000);
  const jwe = await new EncryptJWT({
    sub: userId,
    email: email,
    name: email.split("@")[0],
    userId: userId,
  })
    .setProtectedHeader({ alg: "dir", enc: "A256CBC-HS512", kid: thumbprint })
    .setIssuedAt(now)
    .setExpirationTime(now + SESSION_LIFETIME_SECONDS)
    .setJti(crypto.randomUUID())
    .encrypt(encryptionSecret);

  console.log("\n=== Cookie value (copy this whole line) ===\n");
  console.log(jwe);
  console.log("\n=== Cookie attributes ===\n");
  console.log(`  Name:      ${COOKIE_NAME}`);
  console.log(`  Domain:    localhost`);
  console.log(`  Path:      /`);
  console.log(`  Expires:   ${new Date((now + SESSION_LIFETIME_SECONDS) * 1000).toISOString()}`);
  console.log(`  HttpOnly:  true`);
  console.log(`  Secure:    false   (HTTP localhost, dev only)`);
  console.log(`  SameSite:  Lax`);
  console.log("\n=== Paste into Chrome DevTools ===\n");
  console.log("  1. Open Chrome → http://localhost:3000");
  console.log("  2. F12 → Application tab → Storage → Cookies → http://localhost:3000");
  console.log(`  3. Right-click empty area → Add new cookie`);
  console.log(`  4. Name:    ${COOKIE_NAME}`);
  console.log(`     Value:   (paste the JWE above)`);
  console.log(`     Domain:  localhost`);
  console.log(`     Path:    /`);
  console.log(`     ✓ HttpOnly checked`);
  console.log(`     SameSite: Lax`);
  console.log(`     Secure:  unchecked`);
  console.log(`  5. Hit Enter to commit the row`);
  console.log(`  6. Hard reload (Cmd+Shift+R) the page`);
  console.log(`  7. You should now see /trips as user ${email}`);
  console.log(`\n  Session TTL: 30 days from now (re-mint if expires)\n`);
}

main().catch((e) => {
  console.error("mint failed:", e);
  process.exit(1);
});
