/**
 * ConstraintForm — pure form component (slice 4.5 / z9o).
 *
 * Tracks local state for 4 control sections:
 *   - dietary: multi-select chips (aria-pressed for selected state)
 *   - mobility: radio group (single value)
 *   - accessibility: single toggle (checkbox)
 *   - no-go: free-text list with add + per-entry remove
 *
 * On submit, fires the onSubmit prop with one {kind, text} entry per
 * non-empty section. Parent (ConstraintPanel) wires this to
 * addConstraintAction — one POST per entry, sequentially.
 *
 * Submit copy per Q15 spec dialogue: button label "Save and re-plan",
 * helper text below explains the existing plan is replaced (~5-10 min).
 */

"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { ConstraintKind } from "@/lib/actions";

const _DIETARY_OPTIONS = ["Vegetarian", "Vegan", "Halal", "Gluten-free", "Nut-free"];

const _MOBILITY_OPTIONS = [
  { value: "active", label: "Active (long walks, hikes)" },
  { value: "standard", label: "Standard (typical city pace)" },
  { value: "walking-distance", label: "Walking distance only" },
  { value: "no-stairs", label: "No stairs / step-free" },
];

export interface ConstraintSubmission {
  kind: ConstraintKind;
  text: string;
}

interface ConstraintFormProps {
  onSubmit: (entries: ConstraintSubmission[]) => Promise<void> | void;
}

export function ConstraintForm({ onSubmit }: ConstraintFormProps) {
  const [dietary, setDietary] = useState<string[]>([]);
  const [mobility, setMobility] = useState<string>("");
  const [accessibility, setAccessibility] = useState(false);
  const [noGoList, setNoGoList] = useState<string[]>([]);
  const [noGoInput, setNoGoInput] = useState("");
  const [pending, setPending] = useState(false);

  function _toggleDietary(option: string) {
    setDietary((prev) =>
      prev.includes(option) ? prev.filter((o) => o !== option) : [...prev, option],
    );
  }

  function _addNoGo() {
    const trimmed = noGoInput.trim();
    if (!trimmed) return;
    setNoGoList((prev) => [...prev, trimmed]);
    setNoGoInput("");
  }

  function _removeNoGo(index: number) {
    setNoGoList((prev) => prev.filter((_, i) => i !== index));
  }

  async function _handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const entries: ConstraintSubmission[] = [];
    if (dietary.length > 0) {
      entries.push({ kind: "dietary", text: dietary.join(", ") });
    }
    if (mobility) {
      entries.push({ kind: "mobility", text: mobility });
    }
    if (accessibility) {
      entries.push({
        kind: "accessibility",
        text: "wheelchair / step-free accessibility required",
      });
    }
    for (const entry of noGoList) {
      entries.push({ kind: "no_go", text: entry });
    }
    if (entries.length === 0) return;

    setPending(true);
    try {
      await onSubmit(entries);
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={_handleSubmit} className="space-y-6">
      {/* Dietary — multi-select chips */}
      <fieldset>
        <legend className="text-label-md text-on-surface mb-2">Dietary</legend>
        <div className="flex flex-wrap gap-2">
          {_DIETARY_OPTIONS.map((option) => {
            const selected = dietary.includes(option);
            return (
              <button
                key={option}
                type="button"
                aria-pressed={selected}
                onClick={() => _toggleDietary(option)}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                  selected
                    ? "bg-primary text-on-primary border-primary"
                    : "bg-surface-container-lowest text-on-surface border-outline-variant hover:bg-surface-container-low"
                }`}
              >
                {option}
              </button>
            );
          })}
        </div>
      </fieldset>

      {/* Mobility — radio */}
      <fieldset>
        <legend className="text-label-md text-on-surface mb-2">Mobility</legend>
        <div className="space-y-1.5">
          {_MOBILITY_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex items-center gap-2 text-body-md text-on-surface cursor-pointer"
            >
              <input
                type="radio"
                name="mobility"
                value={option.value}
                checked={mobility === option.value}
                onChange={() => setMobility(option.value)}
                className="text-primary focus-visible:ring-2 focus-visible:ring-primary"
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      {/* Accessibility — toggle */}
      <fieldset>
        <legend className="sr-only">Accessibility</legend>
        <label className="flex items-center gap-2 text-body-md text-on-surface cursor-pointer">
          <input
            type="checkbox"
            checked={accessibility}
            onChange={(e) => setAccessibility(e.target.checked)}
            aria-label="Accessibility accommodations required"
            className="text-primary focus-visible:ring-2 focus-visible:ring-primary"
          />
          Wheelchair / step-free accessibility required
        </label>
      </fieldset>

      {/* No-go — input + add + list */}
      <fieldset>
        <legend className="text-label-md text-on-surface mb-2">No-go list</legend>
        <div className="flex gap-2">
          <input
            type="text"
            id="no-go-input"
            aria-label="No-go entry"
            value={noGoInput}
            onChange={(e) => setNoGoInput(e.target.value)}
            placeholder="e.g., loud bars, crowded markets"
            className="flex-1 px-3 py-1.5 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary"
          />
          <Button type="button" variant="outline" onClick={_addNoGo} aria-label="Add no-go entry">
            Add
          </Button>
        </div>
        {noGoList.length > 0 && (
          <ul className="mt-2 flex flex-wrap gap-2">
            {noGoList.map((entry, idx) => (
              <li
                // biome-ignore lint/suspicious/noArrayIndexKey: list is append/remove only — same text twice is permitted and we want both rendered distinctly
                key={`${entry}-${idx}`}
                className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container-high text-xs"
              >
                <span>{entry}</span>
                <button
                  type="button"
                  aria-label={`Remove ${entry}`}
                  onClick={() => _removeNoGo(idx)}
                  className="text-on-surface-variant hover:text-error"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      <div>
        <Button type="submit" disabled={pending} variant="default">
          {pending ? "Saving…" : "Save and re-plan"}
        </Button>
        <p className="mt-2 text-label-sm text-on-surface-variant">
          Your existing plan will be replaced with one that respects these constraints (~5-10
          minutes).
        </p>
      </div>
    </form>
  );
}
