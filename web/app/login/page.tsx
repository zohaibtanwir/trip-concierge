/**
 * Sign-in page — slice 4.1 (mvs). Minimal.
 *
 * Explicit non-scope (per slice approval):
 *  - No password field (passwordless only for v1.0a)
 *  - No "remember me" checkbox (JWT session strategy default expiry)
 *  - No social-proof copy
 *  - No client-side email validation beyond HTML5 type="email"
 *  - No loading spinner on Submit (Auth.js signIn returns; success is
 *    the redirect)
 *  - No "Resend magic link" button (24h expiry; user can re-submit)
 */

import { signIn } from "@/auth";

async function signInWithEmail(formData: FormData) {
  "use server";
  const email = formData.get("email");
  if (typeof email !== "string" || email === "") return;
  await signIn("resend", { email, redirectTo: "/" });
}

async function signInWithGoogle() {
  "use server";
  await signIn("google", { redirectTo: "/" });
}

export default function LoginPage() {
  return (
    <main className="min-h-screen flex items-center justify-center p-8">
      {/*
       * E2E theme sentinels — verify Tailwind v4 tokens compile to
       * expected RGB values + Material Symbols font renders glyphs (not
       * missing-glyph squares) in production builds. Read by
       * web/tests/e2e/slice-4.3-smoke.spec.ts via getComputedStyle and
       * bounding-rect inspection. Visually off-screen at -9999px so
       * production users never see them. Do not remove.
       */}
      <span
        data-testid="theme-sentinel"
        className="absolute -left-[9999px] bg-primary text-on-primary"
        aria-hidden="true"
      />
      <span
        data-testid="material-symbols-sentinel"
        className="absolute -left-[9999px] material-symbols-outlined"
        aria-hidden="true"
      >
        map
      </span>
      <div className="w-full max-w-sm space-y-6">
        <h1 className="text-2xl font-semibold">Sign in to Trip Concierge</h1>

        <form action={signInWithEmail} className="space-y-3">
          <label htmlFor="email" className="block text-sm">
            Email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            autoComplete="email"
            className="w-full border rounded px-3 py-2"
          />
          <p className="text-sm text-gray-600">We'll email you a sign-in link.</p>
          <button type="submit" className="w-full bg-black text-white rounded px-3 py-2">
            Email me a sign-in link
          </button>
        </form>

        <form action={signInWithGoogle}>
          <button type="submit" className="w-full border rounded px-3 py-2">
            Continue with Google
          </button>
        </form>
      </div>
    </main>
  );
}
