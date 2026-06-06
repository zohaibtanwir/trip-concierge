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
import { PlanAgainDialog } from "@/components/plan-again-dialog";
import { PlanHistoryPanel } from "@/components/plan-history-panel";
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
      <header className="fixed top-0 left-0 right-0 z-50 glass-header border-b border-outline-variant">
        <nav className="mx-auto flex h-20 max-w-[1440px] items-center justify-between px-4 md:px-8 lg:px-16">
          <Link href="/trips" className="text-label-md text-on-surface hover:text-primary">
            ← All trips
          </Link>
        </nav>
      </header>
      <main className="mx-auto max-w-[1440px] px-4 pt-28 pb-12 md:px-8 lg:px-16">
        <h1 className="mb-8 text-headline-md text-on-surface md:text-headline-lg">
          {trip.destination}
        </h1>

        <div className="grid grid-cols-12 gap-6 items-start">
          {/* === Left column (primary content) === */}
          <div className="col-span-12 md:col-span-8 space-y-8">
            {isPlanning && (
              <section className="rounded-xl border border-outline-variant bg-primary-fixed-dim/10 p-6">
                <p className="text-label-md text-on-primary-fixed-variant">
                  Your trip is being planned.
                </p>
                {_progressLine(planStatus) && (
                  <p className="mt-2 text-body-md text-on-surface">{_progressLine(planStatus)}</p>
                )}
                <p className="mt-2 text-body-md text-on-surface-variant">
                  Check back in a few minutes.
                </p>
              </section>
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
                  trip.days.map((day) => <TripDay key={day.id} day={day} />)
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
              from slice 4.5):
                DayChipTimeline → TripMap → ConstraintPanel →
                ConstraintList → PlanHistoryPanel
              All five visible on succeeded + failed states only;
              planning state shows the in-progress section in the
              left column with no right-rail tooling. */}
          <aside className="col-span-12 md:col-span-4 md:sticky md:top-28 space-y-4">
            {trip.days.length > 0 && (
              <DayChipTimeline days={trip.days} currentDayId={trip.days[0]?.id} />
            )}
            {(isSucceeded || isFailed) && (
              <TripMap destination={trip.destination} dayCount={trip.days.length} />
            )}
            {(isSucceeded || isFailed) && (
              <ConstraintPanel
                tripId={tripId}
                userId={userId}
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
