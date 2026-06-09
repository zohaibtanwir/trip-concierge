/**
 * /trips/[id] — trip detail page with two-column layout (spec §9.2).
 *
 * Slice 4.3. RSC: auth() → fetchTripDetail(userId, tripId), then
 * branches on planStatus.state. Right column on md+ is sticky: holds
 * the day-chip timeline + 'How this plan was made' panel.
 *
 * Plan again wiring (Q9): failed-only. <PlanAgainDialog /> is rendered
 * only when isFailed; passes planAgainAction from web/lib/actions.ts.
 *
 * `force-dynamic` pinned per slice 4.2 — the planning state UX requires
 * fresh fetches per render (no caching across renders).
 */

import Link from "next/link";

import { auth } from "@/auth";
import { ConstraintList } from "@/components/constraint-list";
import { ConstraintPanel } from "@/components/constraint-panel";
import { DayChipTimeline } from "@/components/day-chip-timeline";
import { Header } from "@/components/header";
import { PlanAgainDialog } from "@/components/plan-again-dialog";
import { PlanControlsPanel } from "@/components/plan-controls-panel";
import { PlanHistoryPanel } from "@/components/plan-history-panel";
import { PlanningTheater } from "@/components/planning-theater";
import { TripDay } from "@/components/trip-day";
import { TripMap } from "@/components/trip-map";
import { planAgainAction } from "@/lib/actions";
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

interface DetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function TripDetailPage({ params }: DetailPageProps) {
  const { id: tripId } = await params;
  const session = await auth();
  if (!session?.user?.id) {
    return (
      <main className="mx-auto max-w-3xl p-6">
        <p className="text-on-surface-variant">Sign-in required.</p>
      </main>
    );
  }

  const userId = session.user.id;
  const { trip, planStatus } = await fetchTripDetail({ userId, tripId });

  const isPlanning = _PLANNING_STATES.includes(planStatus.state);
  const isFailed = _isFailedState(planStatus);
  const isSucceeded = _isSucceededState(planStatus);
  const agentSummary = planStatus.agent_summary ?? [];

  return (
    <>
      <Header />
      <main className="mx-auto max-w-[1440px] px-4 pt-28 pb-12 md:px-8 lg:px-16">
        {/* Slice 4.5c: standalone "← All trips" affordance moved out of
         * the now-shared <Header /> and into the page body. The shared
         * header consolidates the shell (wordmark + profile menu);
         * back-navigation lives at the page level where it remains
         * discoverable without polluting the global shell. */}
        <Link
          href="/trips"
          className="mb-4 inline-block text-label-md text-on-surface-variant hover:text-primary"
        >
          ← All trips
        </Link>
        <h1 className="mb-8 text-headline-md text-on-surface md:text-headline-lg">
          {trip.destination}
        </h1>

        <div className="grid grid-cols-12 gap-6 items-start">
          {/* === Left column (primary content) === */}
          <div className="col-span-12 md:col-span-8 space-y-8">
            {isPlanning && (
              // Slice 4.7-theater (trip-concierge-249) commit 3.
              // Replaces the pre-249 static "Your trip is being planned"
              // section. PlanningTheater polls /plan/status at 2500ms
              // and renders live agent activity until terminal state.
              <PlanningTheater mode="live" tripId={tripId} userId={userId} />
            )}

            {isFailed && (
              <section className="rounded-xl border border-outline-variant bg-error-container/40 p-6">
                <p className="text-label-md text-on-error-container">This trip didn't generate.</p>
                {planStatus.error && (
                  <p className="mt-2 text-body-md text-on-surface">{planStatus.error}</p>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-4">
                  <PlanAgainDialog
                    tripId={tripId}
                    action={
                      planAgainAction.bind(null, tripId, userId) as unknown as (
                        tripId: string,
                      ) => Promise<void>
                    }
                  />
                  <Link href="/trips" className="text-label-md text-primary underline">
                    ← Back to all trips
                  </Link>
                </div>
              </section>
            )}

            {isSucceeded && (
              <section>
                {trip.days.length === 0 ? (
                  <p className="text-body-md italic text-on-surface-variant">
                    The plan was marked succeeded but has no days yet.
                  </p>
                ) : (
                  trip.days.map((day) => (
                    <TripDay key={day.id} day={day} tripId={tripId} userId={userId} />
                  ))
                )}
              </section>
            )}

            {!isPlanning && !isFailed && !isSucceeded && (
              <section className="rounded-xl border border-dashed border-outline-variant p-6 text-center bg-surface-container-lowest">
                <p className="text-body-lg text-on-surface font-medium">
                  This trip hasn't been planned yet.
                </p>
                <p className="mt-2 text-body-md text-on-surface-variant">
                  Plan creation may have stalled. Try again from Claude Desktop.
                </p>
              </section>
            )}
          </div>

          {/* === Right column (sticky on md+) ===
              Stack order (spec §9.2 + §9.12 from slice 4.4 + §9.13
              from slice 4.5 + §9.14 from slice 4.5b):
                DayChipTimeline → TripMap → PlanControlsPanel →
                ConstraintPanel → ConstraintList → PlanHistoryPanel
              All six visible on succeeded + failed states only;
              planning state shows the in-progress section in the
              left column with no right-rail tooling.

              PlanControlsPanel (settings overwrite) sits ABOVE
              ConstraintPanel (rules accumulate) per the slice 4.5b
              Q5=B settings-vs-rules ontology — column-write surface
              before append-only surface. */}
          <aside className="col-span-12 md:col-span-4 md:sticky md:top-28 space-y-4">
            {trip.days.length > 0 && (
              <DayChipTimeline days={trip.days} currentDayId={trip.days[0]?.id} />
            )}
            {(isSucceeded || isFailed) && (
              <TripMap destination={trip.destination} dayCount={trip.days.length} />
            )}
            {(isSucceeded || isFailed) && (
              <PlanControlsPanel
                tripId={tripId}
                userId={userId}
                currentPace={
                  (["packed", "balanced", "lazy"] as const).includes(
                    trip.pace as "packed" | "balanced" | "lazy",
                  )
                    ? (trip.pace as "packed" | "balanced" | "lazy")
                    : "balanced"
                }
                currentBudgetTotal={trip.budget_total === null ? null : Number(trip.budget_total)}
                currency={trip.currency}
              />
            )}
            {(isSucceeded || isFailed) && (
              <ConstraintPanel
                tripId={tripId}
                userId={userId}
                currency={trip.currency}
                existingRules={
                  (
                    trip.constraints as {
                      rules?: Array<{ kind: string; value: string; raw_text: string }>;
                    }
                  )?.rules ?? []
                }
              />
            )}
            {(isSucceeded || isFailed) && (
              <ConstraintList
                rules={
                  (
                    trip.constraints as {
                      rules?: Array<{ kind: string; value: string; raw_text: string }>;
                    }
                  )?.rules ?? []
                }
              />
            )}
            {(isSucceeded || isFailed) && <PlanHistoryPanel agentSummary={agentSummary} />}
          </aside>
        </div>
      </main>
    </>
  );
}
