/**
 * /trips — list of the signed-in user's trips.
 *
 * Slice 4.2. RSC: auth() → fetchTripList(userId) → render rows. Empty
 * state when no trips. Each row is a Link to /trips/[id].
 *
 * `force-dynamic` is load-bearing — see trip-concierge-jv7 for the
 * future guard. Without it, Next.js 15's default RSC cache would
 * freeze the list state across renders, breaking the planning-state
 * UX (a just-submitted trip would render stale 'no_job' until the
 * route segment naturally invalidated).
 *
 * No try/catch on fetchTripList — v1.0a uses Next.js's default error
 * boundary. Future slices (4.3 polish, or trip-concierge-og1) can add
 * loading.tsx + error.tsx for explicit skeleton + retry UX.
 */

import Link from "next/link";

import { auth } from "@/auth";
import { TripListRow } from "@/components/trip-list-row";
import { fetchTripList } from "@/lib/backend";

export const dynamic = "force-dynamic";

export default async function TripsPage() {
  const session = await auth();
  // Middleware enforces authenticated access to /trips/*. Session can
  // only be missing here under a misconfigured deploy.
  if (!session?.user?.id) {
    return (
      <main className="max-w-3xl mx-auto p-6">
        <p className="text-slate-600">Sign-in required.</p>
      </main>
    );
  }

  const items = await fetchTripList({ userId: session.user.id });

  return (
    <main className="max-w-3xl mx-auto p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Your trips</h1>
      </header>
      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center">
          <p className="text-slate-700 font-medium">No trips yet.</p>
          <p className="text-sm text-slate-600 mt-2">
            Plan your first trip from Claude Desktop, or{" "}
            <Link href="/" className="underline">
              return home
            </Link>
            .
          </p>
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <TripListRow item={item} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
