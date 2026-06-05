/**
 * /trips/[id] — trip detail page with 3-state branch.
 *
 * Slice 4.2. RSC: auth() → fetchTripDetail(userId, tripId), then
 * branches on planStatus.state:
 *
 *   planning (queued | running | cancelling) → progress message + back link
 *   succeeded (done + approved=true)         → day-by-day blocks
 *   failed   (done+approved=false | failed |
 *             cancelled | no_job)            → error message + back link
 *
 * `force-dynamic` is load-bearing for the planning state — see
 * tests/trip-detail.test.tsx assertion + trip-concierge-jv7.
 *
 * Like the list page, no try/catch — Next.js's default error boundary
 * surfaces fetchTripDetail throws (404, 403, 5xx).
 */

import Link from "next/link";

import { auth } from "@/auth";
import { TripDay } from "@/components/trip-day";
import { fetchTripDetail, type PlanStatus } from "@/lib/backend";

export const dynamic = "force-dynamic";

const _PLANNING_STATES: PlanStatus["state"][] = ["queued", "running", "cancelling"];

function _isFailedState(planStatus: PlanStatus): boolean {
  if (planStatus.state === "failed" || planStatus.state === "cancelled") return true;
  if (planStatus.state === "done" && planStatus.approved === false) return true;
  return false;
}

function _isSucceededState(planStatus: PlanStatus): boolean {
  return planStatus.state === "done" && planStatus.approved !== false;
}

function _progressLine(planStatus: PlanStatus): string | null {
  const pm = planStatus.progress_message;
  if (!pm) return null;
  return pm.message ? `${pm.agent} (pass ${pm.pass}): ${pm.message}` : pm.agent;
}

interface DetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function TripDetailPage({ params }: DetailPageProps) {
  const { id: tripId } = await params;
  const session = await auth();
  if (!session?.user?.id) {
    return (
      <main className="max-w-3xl mx-auto p-6">
        <p className="text-slate-600">Sign-in required.</p>
      </main>
    );
  }

  const { trip, planStatus } = await fetchTripDetail({
    userId: session.user.id,
    tripId,
  });

  const isPlanning = _PLANNING_STATES.includes(planStatus.state);
  const isFailed = _isFailedState(planStatus);
  const isSucceeded = _isSucceededState(planStatus);

  return (
    <main className="max-w-3xl mx-auto p-6">
      <header className="mb-6">
        <Link href="/trips" className="text-sm text-slate-600 underline">
          ← All trips
        </Link>
        <h1 className="text-2xl font-semibold mt-2">{trip.destination}</h1>
      </header>

      {isPlanning && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-6">
          <p className="font-medium text-amber-900">Your trip is being planned.</p>
          {_progressLine(planStatus) && (
            <p className="text-sm text-amber-800 mt-2">{_progressLine(planStatus)}</p>
          )}
          <p className="text-sm text-amber-800 mt-2">Check back in a few minutes.</p>
        </section>
      )}

      {isFailed && (
        <section className="rounded-lg border border-rose-200 bg-rose-50 p-6">
          <p className="font-medium text-rose-900">This trip didn't generate.</p>
          {planStatus.error && <p className="text-sm text-rose-800 mt-2">{planStatus.error}</p>}
          <p className="text-sm text-rose-800 mt-4">
            <Link href="/trips" className="underline">
              ← Back to all trips
            </Link>
          </p>
        </section>
      )}

      {isSucceeded && (
        <section>
          {trip.days.length === 0 ? (
            <p className="text-slate-600 italic">
              The plan was marked succeeded but has no days yet. This is an inconsistent state —
              please refresh in a moment.
            </p>
          ) : (
            trip.days.map((day) => <TripDay key={day.id} day={day} />)
          )}
        </section>
      )}

      {!isPlanning && !isFailed && !isSucceeded && (
        // Genuinely-unplanned fallback. The active-job overlay in
        // fetchTripDetail demotes most no_job cases to planning (live
        // jobs in flight) or surfaces them as failed (job stalled and
        // wrote a terminal row). What's left: worker crashed at enqueue
        // before writing the Redis key, OR the Redis active_job TTL
        // expired without a JobRun ever being written. Rare in practice
        // but the surface must acknowledge it honestly.
        <section className="rounded-lg border border-dashed border-slate-300 p-6 text-center">
          <p className="text-slate-700 font-medium">This trip hasn't been planned yet.</p>
          <p className="text-sm text-slate-600 mt-2">
            Plan creation may have stalled. Try again from Claude Desktop.
          </p>
        </section>
      )}
    </main>
  );
}
