/**
 * Typed env access — slice 4.1 (mvs) + later phases.
 *
 * Lazy getters so module imports are cheap; values resolve on first
 * access. Test stubbing via `vi.stubEnv(...)` works because getters
 * read `process.env` at call time, not at import time.
 *
 * Dev defaults match `.env.example` so local + CI work without a
 * fully-populated .env. Production deploys MUST override the empty-
 * string defaults (Auth.js disables Resend/Google providers when
 * their respective creds are empty, which is the right dev behavior
 * but wrong for prod).
 */

function get(name: string, defaultValue?: string): string {
  const v = process.env[name];
  if (v !== undefined && v !== "") return v;
  if (defaultValue !== undefined) return defaultValue;
  throw new Error(`Missing required env var: ${name}`);
}

export const env = {
  get DATABASE_URL() {
    return get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/trip_concierge");
  },
  get NEXTAUTH_URL() {
    return get("NEXTAUTH_URL", "http://localhost:3000");
  },
  get NEXTAUTH_SECRET() {
    return get("NEXTAUTH_SECRET", "dev-only-do-not-use-in-prod");
  },
  get GOOGLE_CLIENT_ID() {
    return get("GOOGLE_CLIENT_ID", "");
  },
  get GOOGLE_CLIENT_SECRET() {
    return get("GOOGLE_CLIENT_SECRET", "");
  },
  get RESEND_API_KEY() {
    return get("RESEND_API_KEY", "");
  },
  get RESEND_FROM_EMAIL() {
    return get("RESEND_FROM_EMAIL", "auth@tripconcierge.app");
  },
  get BACKEND_URL() {
    return get("BACKEND_URL", "http://localhost:8000");
  },
  get INTERNAL_AUTH_SECRET() {
    return get("INTERNAL_AUTH_SECRET", "dev-only-internal-auth-do-not-use-in-prod");
  },
};
