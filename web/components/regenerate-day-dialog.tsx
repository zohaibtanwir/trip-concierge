/**
 * RegenerateDayDialog — day-scoped regenerate trigger (slice 4.6 commit 2;
 * hotfix-nwk modal-mode pattern 2026-06-08).
 *
 * Per Q2 sign-off (option A): button on Day header → modal with
 * optional hint textarea → submit → page navigates to /trips/[id]
 * where slice 4.2's planning-state UX takes over.
 *
 * Modal-mode pattern (spec §9.18): NO declarative `open` attribute.
 * useEffect drives showModal/close imperatively so the dialog enters
 * modal mode (top-layer, ::backdrop, native Escape). The previous
 * `<dialog open>` shape threw InvalidStateError inside showModal —
 * caught + swallowed — leaving dialogs non-modal.
 *
 * Lock-preservation copy per Q8 sign-off: explicit "Locked blocks on
 * this day are preserved" so the user understands the regen scope.
 * Planning-time disclosure per Q2 sign-off: ~3-5 min wall time.
 *
 * Hint is optional at every layer — empty submit is valid.
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { regenerateDayAction } from "@/lib/actions";

interface RegenerateDayDialogProps {
  tripId: string;
  userId: string;
  dayNumber: number;
}

export function RegenerateDayDialog({ tripId, userId, dayNumber }: RegenerateDayDialogProps) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [open, setOpen] = useState(false);
  const [hint, setHint] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      try {
        dlg.showModal();
      } catch {
        dlg.setAttribute("open", "");
      }
    } else if (!open && dlg.open) {
      try {
        dlg.close();
      } catch {
        dlg.removeAttribute("open");
      }
    }
  }, [open]);

  function _openDialog() {
    setOpen(true);
  }

  function _closeDialog() {
    setOpen(false);
    setHint("");
    setError(null);
  }

  function _backdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) _closeDialog();
  }

  async function _handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await regenerateDayAction({
        userId,
        tripId,
        dayNumber,
        hint: hint.trim() || undefined,
      });
      _closeDialog();
      router.push(`/trips/${tripId}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enqueue regenerate");
      setPending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={_openDialog}
        className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant bg-surface-container-lowest px-3 py-1.5 text-label-sm text-on-surface hover:bg-surface-container-low transition-colors"
      >
        <span className="material-symbols-outlined text-base" aria-hidden>
          refresh
        </span>
        Regenerate
      </button>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: backdrop click has a keyboard
          equivalent — Escape, wired via onClose; there is no "outside-click" key. */}
      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={_backdropClick}
        className="rounded-xl bg-surface-container-lowest p-0 border border-outline-variant shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm m-auto max-w-md w-[calc(100%-2rem)]"
      >
        {open && (
          <form onSubmit={_handleSubmit} className="p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h2 className="text-headline-sm text-on-surface">Regenerate Day {dayNumber}</h2>
              <button
                type="button"
                onClick={_closeDialog}
                aria-label="Close"
                className="material-symbols-outlined text-on-surface-variant hover:text-on-surface transition-colors text-base p-1"
              >
                close
              </button>
            </div>

            <p className="text-body-md text-on-surface-variant mb-4">
              The Logistics Planner will rebuild Day {dayNumber}'s blocks. Locked blocks on this day
              are preserved — they survive regeneration unchanged. Other blocks may be reordered or
              replaced.
            </p>

            <div className="mb-4">
              <label htmlFor="rdd-hint" className="block text-label-md text-on-surface mb-1.5">
                Hint <span className="text-on-surface-variant">(optional)</span>
              </label>
              <textarea
                id="rdd-hint"
                value={hint}
                onChange={(e) => setHint(e.target.value)}
                placeholder="e.g., make Day 2 chiller / more food, less hiking"
                rows={3}
                className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary resize-none"
              />
              <p className="mt-1 text-label-sm text-on-surface-variant">
                Free-text guidance for the crew. Empty is fine — the Planner will use the trip's
                vibe and constraints.
              </p>
            </div>

            {error && (
              <p className="mb-4 text-body-sm text-error" role="alert">
                {error}
              </p>
            )}

            <div>
              <button
                type="submit"
                disabled={pending}
                className="w-full rounded-lg bg-primary px-6 py-2.5 text-label-md text-on-primary hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {pending ? "Starting…" : `Regenerate Day ${dayNumber}`}
              </button>
              <p className="mt-2 text-label-sm text-on-surface-variant">
                The crew takes ~3-5 min. You'll be redirected to the trip page where you can watch
                progress.
              </p>
            </div>
          </form>
        )}
      </dialog>
    </>
  );
}
