/**
 * PlanControlsPanel — responsive wrapper for PlanControlsForm (slice 4.5b).
 *
 * Mirror of slice 4.5 ConstraintPanel's responsive pattern: `forceVariant`
 * prop pins each variant in jsdom without simulating real viewport changes.
 * Production callers currently pass forceVariant="inline" (desktop default);
 * useMediaQuery resolution tracked under trip-concierge-gdm (shared with
 * ConstraintPanel — same hook unblocks both).
 *
 * onSubmit semantics: PlanControlsForm emits ONLY changed fields. This
 * wrapper fires updateTripSettingsAction with whatever the form
 * surfaced — undefined fields stay out of the PATCH body via the
 * Server Action's omit-undefined serialization.
 *
 * Companion to ConstraintPanel (slice 4.5). Right-rail stack:
 *   TripMap → PlanControlsPanel → ConstraintPanel → ConstraintList
 *   → PlanHistoryPanel
 */

"use client";

import { PlanControlsForm, type PlanControlsSubmission } from "@/components/plan-controls-form";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { type TripPace, updateTripSettingsAction } from "@/lib/actions";

interface PlanControlsPanelProps {
  tripId: string;
  userId: string;
  currentPace: TripPace;
  currentBudgetTotal: number | null;
  currency: string;
  forceVariant?: "sheet" | "inline";
}

export function PlanControlsPanel({
  tripId,
  userId,
  currentPace,
  currentBudgetTotal,
  currency,
  forceVariant = "inline",
}: PlanControlsPanelProps) {
  async function _handleSubmit(changes: PlanControlsSubmission) {
    await updateTripSettingsAction({
      tripId,
      userId,
      pace: changes.pace,
      budgetTotal: changes.budgetTotal,
    });
  }

  if (forceVariant === "sheet") {
    return (
      <Sheet>
        <SheetTrigger render={<Button variant="outline">Plan controls</Button>} />
        <SheetContent side="bottom">
          <div className="p-4">
            <h2 className="text-headline-md text-on-surface mb-4">Plan controls</h2>
            <PlanControlsForm
              currentPace={currentPace}
              currentBudgetTotal={currentBudgetTotal}
              currency={currency}
              onSubmit={_handleSubmit}
            />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <h2 className="text-label-md text-on-surface mb-4">Plan controls</h2>
      <PlanControlsForm
        currentPace={currentPace}
        currentBudgetTotal={currentBudgetTotal}
        currency={currency}
        onSubmit={_handleSubmit}
      />
    </div>
  );
}
