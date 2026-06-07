/**
 * NewTripForm — inline web form for trip creation (slice 4.5c commit 3.5).
 *
 * Embedded in <NewTripDialog />'s "Create here" tab. Six inputs per
 * commit-3.5 sign-off:
 *   - destination (required)
 *   - start_date, end_date (optional)
 *   - group_size (default 1)
 *   - budget_total (optional) + currency (default INR — matches the
 *     Marsh demo's Coorg trip; user can pick USD/EUR/GBP/INR/JPY)
 *   - pace (3-state segmented: packed / balanced / lazy, default
 *     balanced)
 *
 * No vibe field — vibe is a refine-time concern per the architectural
 * call in Q-product-2. Trip Concierge backend's TripCreate schema
 * doesn't carry vibe; the constraint is structural, not a missing
 * feature.
 *
 * Submit disabled until destination has a value (UI-side guard against
 * the 422 round-trip; backend's Pydantic also rejects empty
 * destination).
 *
 * On success: useRouter.push to /trips/{trip_id} (Q3.5-impl-a sign-off:
 * dialog owns UX flow). The trip detail page's slice-4.2 planning-state
 * UX takes over from there.
 */

"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { createTripAction, type TripPace } from "@/lib/actions";

const _PACE_OPTIONS: { value: TripPace; label: string }[] = [
  { value: "packed", label: "Packed" },
  { value: "balanced", label: "Balanced" },
  { value: "lazy", label: "Lazy" },
];

const _CURRENCY_OPTIONS = ["INR", "USD", "EUR", "GBP", "JPY"];

interface NewTripFormProps {
  userId: string;
  onSuccess?: () => void;
}

export function NewTripForm({ userId, onSuccess }: NewTripFormProps) {
  const router = useRouter();
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [groupSize, setGroupSize] = useState(1);
  const [budgetTotal, setBudgetTotal] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [pace, setPace] = useState<TripPace>("balanced");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = destination.trim().length > 0 && !pending;

  async function _handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      const result = await createTripAction({
        userId,
        destination: destination.trim(),
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        groupSize,
        budgetTotal: budgetTotal ? Number(budgetTotal) : undefined,
        currency,
        pace,
      });
      onSuccess?.();
      router.push(`/trips/${result.trip_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create trip");
      setPending(false);
    }
  }

  return (
    <form onSubmit={_handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="ntf-destination" className="block text-label-md text-on-surface mb-1.5">
          Destination<span className="text-error ml-1">*</span>
        </label>
        <input
          id="ntf-destination"
          type="text"
          required
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          placeholder="e.g., Coorg, Karnataka, India"
          className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="ntf-start-date" className="block text-label-md text-on-surface mb-1.5">
            Start date
          </label>
          <input
            id="ntf-start-date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
          />
        </div>
        <div>
          <label htmlFor="ntf-end-date" className="block text-label-md text-on-surface mb-1.5">
            End date
          </label>
          <input
            id="ntf-end-date"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
          />
        </div>
      </div>

      <div>
        <label htmlFor="ntf-group-size" className="block text-label-md text-on-surface mb-1.5">
          Group size (travelers)
        </label>
        <input
          id="ntf-group-size"
          type="number"
          min={1}
          value={groupSize}
          onChange={(e) => setGroupSize(Math.max(1, Number(e.target.value) || 1))}
          className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
        />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <label htmlFor="ntf-budget" className="block text-label-md text-on-surface mb-1.5">
            Total budget
          </label>
          <input
            id="ntf-budget"
            type="number"
            min={0}
            step="any"
            value={budgetTotal}
            onChange={(e) => setBudgetTotal(e.target.value)}
            placeholder="e.g., 50000"
            className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
          />
        </div>
        <div>
          <label htmlFor="ntf-currency" className="block text-label-md text-on-surface mb-1.5">
            Currency
          </label>
          <select
            id="ntf-currency"
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
            className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
          >
            {_CURRENCY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

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
                className={`flex-1 px-3 py-2 rounded-lg text-label-sm font-medium border transition-colors ${
                  selected
                    ? "bg-primary text-on-primary border-primary"
                    : "bg-surface-container-lowest text-on-surface border-outline-variant hover:bg-surface-container-low"
                }`}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </fieldset>

      {error && (
        <p className="text-body-sm text-error" role="alert">
          {error}
        </p>
      )}

      <div>
        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-primary px-6 py-2.5 text-label-md text-on-primary hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {pending ? "Starting…" : "Plan trip"}
        </button>
        <p className="mt-2 text-label-sm text-on-surface-variant">
          The crew will start planning (~10 min). You'll be redirected to the trip detail page where
          you can watch progress or refine constraints.
        </p>
      </div>
    </form>
  );
}
