/**
 * /trips — list of the signed-in user's trips.
 *
 * Slice 4.3 — adopts spec §9.1 sticky glass header + spec §4.2 typography
 * tokens. Container width per spec §5 (max 1440px, margin tokens by
 * breakpoint).
 *
 * `force-dynamic` is load-bearing per slice 4.2's planning-state UX guard
 * (see trip-concierge-jv7 for the build-time guard followup).
 */

import Link from "next/link";

import { auth } from "@/auth";
import { Header } from "@/components/header";
import { NewTripDialog } from "@/components/new-trip-dialog";
import { TripListRow } from "@/components/trip-list-row";
import { fetchTripList } from "@/lib/backend";

export const dynamic = "force-dynamic";

export default async function TripsPage() {
  const session = await auth();
  if (!session?.user?.id) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <p className="text-on-surface-variant">Sign-in required.</p>
      </main>
    );
  }

  const items = await fetchTripList({ userId: session.user.id });

  return (
    <>
      <Header />
      <main className="mx-auto max-w-[1440px] px-4 pt-28 md:px-8 lg:px-16">
        <div className="mb-8 flex items-baseline justify-between gap-4">
          <h1 className="text-headline-md text-on-surface md:text-headline-lg">Your trips</h1>
          {/* Slice 4.5c: top-right "New trip" CTA opens the MCP-first
           * dialog. Only shown when trips exist — empty-state has its
           * own primary trigger below per Q6=A consolidation. */}
          {items.length > 0 && <NewTripDialog triggerLabel="New trip" />}
        </div>
        {items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-outline-variant p-8 text-center bg-surface-container-lowest">
            <p className="text-body-lg text-on-surface font-medium mb-4">No trips yet.</p>
            <div className="flex justify-center mb-4">
              <NewTripDialog triggerLabel="Plan your first trip" />
            </div>
            <p className="text-body-md text-on-surface-variant">
              Or{" "}
              <Link href="/" className="text-primary underline">
                return home
              </Link>
              .
            </p>
          </div>
        ) : (
          <ul className="space-y-4">
            {items.map((item) => (
              <li key={item.id}>
                <TripListRow item={item} />
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
