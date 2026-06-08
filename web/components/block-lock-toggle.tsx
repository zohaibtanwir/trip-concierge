/**
 * BlockLockToggle — always-visible lock indicator + toggle (slice 4.6 commit 4).
 *
 * Per Q-impl-c4c sign-off (option A): lock_open material icon when
 * unlocked, lock when locked. Single click toggles via the slice-4.6
 * commit-1 PATCH /blocks/{id} route.
 *
 * Per Q5 sign-off: OPTIMISTIC UI. The icon flips immediately on click,
 * before the PATCH completes. If the action rejects:
 *   1. Local state reverts to the prior value
 *   2. Inline error badge (role="alert") appears next to the icon
 *   3. After 3 seconds the badge auto-clears
 *
 * No toast primitive in the project (sonner / Toaster absent — see
 * Q-impl-c4a fallback report). Inline badge contains scope; auto-clear
 * keeps the failure transient rather than persistent UI debt.
 *
 * aria-label names the ACTION the click WILL take, not the current
 * state — better screen reader UX. Disabled-while-pending prevents
 * the rapid-double-click race.
 *
 * No success indicator per Q-impl-c4e (A) — the icon flip IS the
 * success signal; a check mark would add noise.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { setBlockLockAction } from "@/lib/actions";

interface BlockLockToggleProps {
  tripId: string;
  userId: string;
  blockId: string;
  initialLocked: boolean;
}

const _ERROR_CLEAR_MS = 3000;

export function BlockLockToggle({ tripId, userId, blockId, initialLocked }: BlockLockToggleProps) {
  const [locked, setLocked] = useState(initialLocked);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const _clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (_clearTimerRef.current !== null) clearTimeout(_clearTimerRef.current);
    };
  }, []);

  async function _handleClick() {
    if (pending) return;
    const target = !locked;
    // Optimistic flip.
    setLocked(target);
    setPending(true);
    setError(null);
    try {
      await setBlockLockAction({ userId, tripId, blockId, locked: target });
    } catch (err) {
      // Revert + surface inline.
      setLocked(!target);
      setError(err instanceof Error ? err.message : "Failed to update lock");
      if (_clearTimerRef.current !== null) clearTimeout(_clearTimerRef.current);
      _clearTimerRef.current = setTimeout(() => {
        setError(null);
        _clearTimerRef.current = null;
      }, _ERROR_CLEAR_MS);
    } finally {
      setPending(false);
    }
  }

  const ariaLabel = locked ? "Unlock this block" : "Lock this block";
  const iconName = locked ? "lock" : "lock_open";

  return (
    <span className="inline-flex items-center gap-1.5">
      <button
        type="button"
        onClick={_handleClick}
        disabled={pending}
        aria-label={ariaLabel}
        title={ariaLabel}
        className="inline-flex items-center justify-center rounded-md border border-outline-variant bg-surface-container-lowest p-1.5 text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <span className="material-symbols-outlined text-sm" aria-hidden>
          {iconName}
        </span>
      </button>
      {error && (
        <span
          role="alert"
          className="rounded bg-error-container px-2 py-0.5 text-label-sm text-on-error-container"
        >
          Couldn't update
        </span>
      )}
    </span>
  );
}
