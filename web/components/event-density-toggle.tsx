/**
 * EventDensityToggle — two-state toggle for the theater LiveEventLog.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 2. Per Q-impl-249-e=A:
 *   - "major" (default) — task_completed + callback_summary only.
 *     The 3-handoff + 1-tally rhythm is the clean demo narrative
 *   - "all" — every event including AgentFinish step events. The
 *     engineering "show me everything" toggle
 *
 * Persists choice to sessionStorage under "theater-density" so the
 * preference survives polling refreshes within the tab but resets
 * across tabs / sessions. Appropriate for a transient demo
 * preference; localStorage would carry across sessions which feels
 * over-sticky.
 *
 * Mounted-flag pattern (hotfix-0pj): renders null until the mount
 * useEffect has fired. sessionStorage is unavailable during SSR; the
 * previous useState-initializer pattern caused a hydration mismatch
 * when the client-first-render read sessionStorage and disagreed with
 * the server's default. Now both server AND client first render return
 * null; the real UI appears after mount with hydrated state. Brief
 * flicker is acceptable for a polish element.
 *
 * R6 confirmation: cards always show full state. This toggle ONLY
 * affects the LiveEventLog below the cards.
 */

"use client";

import { useEffect, useState } from "react";

type Mode = "major" | "all";

const _STORAGE_KEY = "theater-density";

interface EventDensityToggleProps {
  onChange: (mode: Mode) => void;
}

function _readStoredMode(): Mode {
  if (typeof window === "undefined") return "major";
  const raw = window.sessionStorage.getItem(_STORAGE_KEY);
  return raw === "all" ? "all" : "major";
}

export function EventDensityToggle({ onChange }: EventDensityToggleProps) {
  // Mounted-flag pattern: mounted=false during SSR + first client render,
  // both of which return null. After mount, useEffect reads sessionStorage,
  // flips mounted=true, calls onChange. From then on subsequent
  // _handleChange calls update local state + sessionStorage + onChange.
  const [mounted, setMounted] = useState(false);
  const [mode, setMode] = useState<Mode>("major");

  // biome-ignore lint/correctness/useExhaustiveDependencies: mount-only by design
  useEffect(() => {
    const stored = _readStoredMode();
    setMode(stored);
    setMounted(true);
    onChange(stored);
  }, []);

  if (!mounted) return null;

  function _handleChange(next: Mode) {
    if (next === mode) return;
    setMode(next);
    try {
      window.sessionStorage.setItem(_STORAGE_KEY, next);
    } catch {
      // sessionStorage may be unavailable (privacy mode, etc.); the
      // toggle still works in-memory.
    }
    onChange(next);
  }

  return (
    <>
      {/* biome-ignore lint/a11y/useSemanticElements: role="group" + aria-label is
          standard for toggle-button pairs; <fieldset> requires <legend> + default
          styling that conflicts with the inline-flex pill layout. */}
      <div
        role="group"
        aria-label="Event density"
        className="inline-flex rounded-md border border-outline-variant bg-surface-container-lowest p-0.5"
      >
        <button
          type="button"
          onClick={() => _handleChange("major")}
          aria-pressed={mode === "major"}
          className={`rounded px-3 py-1 text-label-sm transition-colors ${
            mode === "major"
              ? "bg-primary text-on-primary"
              : "text-on-surface-variant hover:bg-surface-container-low"
          }`}
        >
          Major
        </button>
        <button
          type="button"
          onClick={() => _handleChange("all")}
          aria-pressed={mode === "all"}
          className={`rounded px-3 py-1 text-label-sm transition-colors ${
            mode === "all"
              ? "bg-primary text-on-primary"
              : "text-on-surface-variant hover:bg-surface-container-low"
          }`}
        >
          All
        </button>
      </div>
    </>
  );
}
