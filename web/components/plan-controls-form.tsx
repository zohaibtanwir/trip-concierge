/**
 * PlanControlsForm — pure form component (slice 4.5b / cdr).
 *
 * Two settings-shaped controls:
 *   - pace: 3-state segmented control (packed / balanced / lazy)
 *     rendered as aria-pressed buttons (mirror of constraint-form's
 *     dietary chip pattern). Single-select via aria-pressed mutual
 *     exclusion.
 *   - budget_total: numeric input with currency label.
 *
 * Dirty-state tracking: emits ONLY fields the user explicitly changed
 * from the `current*` props. Submit no-ops when nothing changed —
 * prevents the backend's at-least-one-of validator from 422'ing an
 * empty PATCH round-trip.
 *
 * Submit copy "Update settings and re-plan" (Q5/B sign-off): the
 * settings-vs-rules distinction at the UI layer matches column-vs-rule
 * at the data layer. Companion ConstraintPanel uses "Save and re-plan"
 * (append semantics). Verb-as-disclosure of data shape.
 */

"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { TripPace } from "@/lib/actions";

const _PACE_OPTIONS: { value: TripPace; label: string; description: string }[] = [
  { value: "packed", label: "Packed", description: "max blocks/day" },
  { value: "balanced", label: "Balanced", description: "mix of pace" },
  { value: "lazy", label: "Lazy", description: "low-key, downtime" },
];

export interface PlanControlsSubmission {
  pace?: TripPace;
  budgetTotal?: number;
}

interface PlanControlsFormProps {
  currentPace: TripPace;
  currentBudgetTotal: number | null;
  currency: string;
  onSubmit: (changes: PlanControlsSubmission) => Promise<void> | void;
}

export function PlanControlsForm({
  currentPace,
  currentBudgetTotal,
  currency,
  onSubmit,
}: PlanControlsFormProps) {
  const [pace, setPace] = useState<TripPace>(currentPace);
  const [budgetInput, setBudgetInput] = useState<string>(
    currentBudgetTotal === null ? "" : String(currentBudgetTotal),
  );
  const [pending, setPending] = useState(false);

  const paceChanged = pace !== currentPace;
  const budgetParsed = budgetInput === "" ? null : Number(budgetInput);
  const budgetChanged =
    budgetParsed !== null && !Number.isNaN(budgetParsed) && budgetParsed !== currentBudgetTotal;
  const hasChanges = paceChanged || budgetChanged;

  async function _handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!hasChanges) return;
    const changes: PlanControlsSubmission = {};
    if (paceChanged) changes.pace = pace;
    if (budgetChanged && budgetParsed !== null) changes.budgetTotal = budgetParsed;
    setPending(true);
    try {
      await onSubmit(changes);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={_handleSubmit} className="space-y-6">
      {/* Pace — 3-state segmented control */}
      <fieldset>
        <legend className="text-label-md text-on-surface mb-2">Pace</legend>
        <div className="flex gap-1.5">
          {_PACE_OPTIONS.map((option) => {
            const selected = pace === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={selected}
                onClick={() => setPace(option.value)}
                className={`flex-1 px-3 py-2 rounded-lg text-xs font-medium border transition-colors ${
                  selected
                    ? "bg-primary text-on-primary border-primary"
                    : "bg-surface-container-lowest text-on-surface border-outline-variant hover:bg-surface-container-low"
                }`}
              >
                <div>{option.label}</div>
                <div
                  className={`text-[0.625rem] mt-0.5 ${
                    selected ? "text-on-primary/80" : "text-on-surface-variant"
                  }`}
                >
                  {option.description}
                </div>
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* Total budget — numeric input with currency label */}
      <fieldset>
        <legend className="text-label-md text-on-surface mb-2">Total budget</legend>
        <div className="flex items-center gap-2">
          <span className="text-label-sm text-on-surface-variant uppercase">{currency}</span>
          <input
            type="number"
            id="budget-total-input"
            aria-label="Total budget"
            min={0}
            step="any"
            value={budgetInput}
            onChange={(e) => setBudgetInput(e.target.value)}
            placeholder="e.g., 50000"
            className="flex-1 px-3 py-1.5 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
          />
        </div>
      </fieldset>

      <div>
        <Button type="submit" disabled={pending || !hasChanges} variant="default">
          {pending ? "Saving…" : "Update settings and re-plan"}
        </Button>
        <p className="mt-2 text-label-sm text-on-surface-variant">
          Pace and budget changes overwrite the previous values. Your plan will be replaced with one
          that respects the new settings (~5-10 minutes).
        </p>
      </div>
    </form>
  );
}
