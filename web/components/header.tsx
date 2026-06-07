/**
 * Header — auth-aware sticky-glass app header (slice 4.5c commit 1).
 *
 * React Server Component. Reads auth() internally (per Q1=A sign-off:
 * single import, pages stay shorter). Pages do `<Header />` with zero
 * props.
 *
 * Layout:
 *   - Wordmark "Trip Concierge" on the left, always linking to `/`
 *     (per Q5b sign-off: "logo always returns home")
 *   - Right side branches on session:
 *       unauthed → "Sign in" link → /login
 *       authed   → <details> profile menu (email read-only + Sign out)
 *
 * Sign-out is co-located as a "use server" action (per Q-a sign-off:
 * uniquely a header concern, doesn't earn its keep in lib/actions.ts).
 *
 * Extracted from inline page-local headers that were duplicated across
 * /trips and /trips/[id] — slice 4.5c discharges the shell-debt that
 * 8 prior Phase 4 slices accumulated invisibly.
 */

import Link from "next/link";

import { auth, signOut } from "@/auth";

async function _signOutAction() {
  "use server";
  await signOut({ redirectTo: "/" });
}

export async function Header() {
  const session = await auth();
  const user = session?.user ?? null;

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass-header border-b border-outline-variant">
      <nav className="mx-auto flex h-20 max-w-[1440px] items-center justify-between px-4 md:px-8 lg:px-16">
        <Link href="/" className="text-label-md text-on-surface hover:text-primary">
          Trip Concierge
        </Link>
        {user ? (
          <details className="relative">
            <summary className="cursor-pointer list-none flex items-center gap-2 text-label-sm text-on-surface hover:text-primary">
              <span className="material-symbols-outlined text-base" aria-hidden>
                account_circle
              </span>
              <span className="hidden sm:inline">{user.email ?? user.name ?? "Account"}</span>
            </summary>
            <div className="absolute right-0 mt-2 w-56 rounded-xl border border-outline-variant bg-surface-container-lowest p-3 shadow-lg">
              <p className="px-2 py-1 text-label-sm text-on-surface-variant break-all">
                {user.email ?? user.name ?? "Signed in"}
              </p>
              <hr className="my-2 border-outline-variant" />
              <form action={_signOutAction}>
                <button
                  type="submit"
                  className="w-full text-left px-2 py-1.5 rounded text-label-md text-on-surface hover:bg-surface-container-low"
                >
                  Sign out
                </button>
              </form>
            </div>
          </details>
        ) : (
          <Link href="/login" className="text-label-md text-on-surface hover:text-primary">
            Sign in
          </Link>
        )}
      </nav>
    </header>
  );
}
