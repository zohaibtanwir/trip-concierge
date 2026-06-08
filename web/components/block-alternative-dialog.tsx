/**
 * BlockAlternativeDialog — block-scoped swap trigger (slice 4.6 commit 3).
 *
 * Per Q3 sign-off (option B): "Swap this" button on block → modal →
 * IDLE state (optional reason textarea + 90s disclosure) → user
 * submits → LOADING state (~90s spinner with Researcher-specialization
 * copy) → SHOWING state (3 ranked alternative cards with per-card
 * Apply CTAs) → user picks one → applyAlternativeAction enqueues a
 * refine job → page navigates to /trips/[id] where slice 4.2's
 * planning-state UX takes over.
 *
 * 4-state machine: idle | loading | showing | confirming. The
 * confirming step (commit 4 polish, Q-impl-c3c sign-off) gates the
 * ~10 min re-plan behind an explicit Confirm click. Back-to-options
 * preserves the alternatives array — no 90s refetch (Q-impl-c4b=A).
 * Error state is overlaid on top of the current state (role="alert").
 *
 * Native <dialog> + showModal pattern (mirror of RegenerateDayDialog
 * commit 2 + NewTripDialog slice 4.5c commit 3): focus trap, escape,
 * backdrop click — all platform-provided.
 *
 * Reason is collected once in IDLE and threaded both to
 * findAlternativeAction (ranking context) and applyAlternativeAction
 * (refinement_description "Reason:" clause for the crew prompt).
 */

"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { type Alternative, applyAlternativeAction, findAlternativeAction } from "@/lib/actions";

interface BlockAlternativeDialogProps {
  tripId: string;
  userId: string;
  blockId: string;
  blockVenueName: string;
  dayNumber: number;
}

type DialogState = "idle" | "loading" | "showing" | "confirming";

export function BlockAlternativeDialog({
  tripId,
  userId,
  blockId,
  blockVenueName,
  dayNumber,
}: BlockAlternativeDialogProps) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<DialogState>("idle");
  const [reason, setReason] = useState("");
  const [alternatives, setAlternatives] = useState<Alternative[]>([]);
  const [selected, setSelected] = useState<Alternative | null>(null);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Hotfix-nwk modal-mode pattern (spec §9.18). NO declarative `open`
    // attribute — useEffect drives showModal/close imperatively so the
    // dialog enters top-layer modal mode (vs the previous non-modal
    // shape that conflicted with map markers + DayChipTimeline tooltips
    // and never responded to Escape).
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
    setState("idle");
    setError(null);
    setOpen(true);
  }

  function _closeDialog() {
    setOpen(false);
    setState("idle");
    setReason("");
    setAlternatives([]);
    setSelected(null);
    setApplying(false);
    setError(null);
  }

  function _backdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) _closeDialog();
  }

  async function _handleFind(e: React.FormEvent) {
    e.preventDefault();
    if (state === "loading") return;
    setState("loading");
    setError(null);
    try {
      const result = await findAlternativeAction({
        userId,
        tripId,
        blockId,
        reason: reason.trim() || undefined,
      });
      setAlternatives(result.alternatives);
      setState("showing");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to find alternatives");
      setState("idle");
    }
  }

  function _pickAlternative(alt: Alternative) {
    // Q-impl-c3c sign-off: card Apply click no longer enqueues refine
    // directly. Transition to confirming surface so the user reviews
    // the ~10 min commitment before kicking off the crew.
    setSelected(alt);
    setError(null);
    setState("confirming");
  }

  function _backToOptions() {
    // Q-impl-c4b=A: preserve alternatives, no refetch. The 90s find
    // cost is paid once per dialog open.
    setSelected(null);
    setError(null);
    setState("showing");
  }

  async function _handleConfirm() {
    if (applying || selected === null) return;
    setApplying(true);
    setError(null);
    try {
      await applyAlternativeAction({
        userId,
        tripId,
        dayNumber,
        oldVenueName: blockVenueName,
        alternativeVenueName: selected.venue_name,
        reason: reason.trim() || undefined,
      });
      _closeDialog();
      router.push(`/trips/${tripId}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply alternative");
      setApplying(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={_openDialog}
        className="inline-flex items-center gap-1 rounded-md border border-outline-variant bg-surface-container-lowest px-2 py-1 text-label-sm text-on-surface hover:bg-surface-container-low transition-colors"
      >
        <span className="material-symbols-outlined text-sm" aria-hidden>
          swap_horiz
        </span>
        Swap this
      </button>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: backdrop click has a keyboard
          equivalent — Escape, wired via onClose; there is no "outside-click" key. */}
      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={_backdropClick}
        className="rounded-xl bg-surface-container-lowest p-0 border border-outline-variant shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm m-auto max-w-lg w-[calc(100%-2rem)]"
      >
        {open && (
          <div className="p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h2 className="text-headline-sm text-on-surface">
                Find alternatives for <span className="font-mono">{blockVenueName}</span>
              </h2>
              <button
                type="button"
                onClick={_closeDialog}
                aria-label="Close"
                className="material-symbols-outlined text-on-surface-variant hover:text-on-surface transition-colors text-base p-1"
              >
                close
              </button>
            </div>

            {state === "idle" && (
              <form onSubmit={_handleFind}>
                <p className="text-body-md text-on-surface-variant mb-4">
                  The Researcher will suggest 3 alternatives for this block — this takes about a
                  minute (~90 seconds).
                </p>
                <div className="mb-4">
                  <label
                    htmlFor="bad-reason"
                    className="block text-label-md text-on-surface mb-1.5"
                  >
                    Reason <span className="text-on-surface-variant">(optional)</span>
                  </label>
                  <textarea
                    id="bad-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="e.g., too touristy, closed for renovations, over budget"
                    rows={3}
                    className="w-full px-3 py-2 rounded border border-outline-variant bg-surface-container-lowest text-body-md focus-visible:ring-2 focus-visible:ring-primary resize-none"
                  />
                  <p className="mt-1 text-label-sm text-on-surface-variant">
                    Helps the Researcher rank alternatives. Carried through to the swap prompt.
                  </p>
                </div>
                {error && (
                  <p className="mb-4 text-body-sm text-error" role="alert">
                    {error}
                  </p>
                )}
                <button
                  type="submit"
                  className="w-full rounded-lg bg-primary px-6 py-2.5 text-label-md text-on-primary hover:bg-primary/90 transition-colors"
                >
                  Find alternatives
                </button>
              </form>
            )}

            {state === "loading" && (
              <div className="py-8 text-center">
                <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent mb-4" />
                <p className="text-body-lg text-on-surface mb-1">
                  The Researcher is finding 3 options for you
                </p>
                <p className="text-body-sm text-on-surface-variant">
                  This takes about a minute. Please wait — don't close this window.
                </p>
              </div>
            )}

            {state === "showing" && (
              <>
                <p className="text-body-md text-on-surface-variant mb-4">
                  The Researcher found {alternatives.length}{" "}
                  {alternatives.length === 1 ? "alternative" : "alternatives"}. Pick one to swap;
                  the crew will re-plan the trip (~10 min).
                </p>
                {error && (
                  <p className="mb-4 text-body-sm text-error" role="alert">
                    {error}
                  </p>
                )}
                <div className="space-y-3">
                  {alternatives.map((alt) => (
                    <div
                      key={alt.venue_name}
                      className="rounded-lg border border-outline-variant p-4 bg-surface-container-lowest"
                    >
                      <h3 className="text-title-md text-on-surface mb-1">{alt.venue_name}</h3>
                      <p className="text-body-sm text-on-surface-variant mb-2">{alt.rationale}</p>
                      <div className="flex flex-wrap gap-3 text-label-sm text-on-surface-variant mb-3">
                        <span>{alt.type}</span>
                        {alt.duration_minutes > 0 && <span>{alt.duration_minutes} min</span>}
                        {alt.est_cost > 0 && (
                          <span>
                            {alt.currency} {alt.est_cost}
                          </span>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => _pickAlternative(alt)}
                        className="rounded-md bg-primary px-4 py-1.5 text-label-md text-on-primary hover:bg-primary/90 transition-colors"
                      >
                        Apply
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}

            {state === "confirming" && selected !== null && (
              <>
                <p className="text-body-md text-on-surface mb-2">
                  Swap <span className="font-mono">{blockVenueName}</span> for{" "}
                  <span className="font-mono">{selected.venue_name}</span>?
                </p>
                <p className="text-body-sm text-on-surface-variant mb-4">
                  Confirming will start a full re-plan (~10 min). The crew re-runs end to end so
                  budgets and other constraints stay consistent. You'll be redirected to the trip
                  page to watch progress.
                </p>
                {error && (
                  <p className="mb-4 text-body-sm text-error" role="alert">
                    {error}
                  </p>
                )}
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={_backToOptions}
                    disabled={applying}
                    className="flex-1 rounded-lg border border-outline-variant bg-surface-container-lowest px-6 py-2.5 text-label-md text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-50"
                  >
                    Back to options
                  </button>
                  <button
                    type="button"
                    onClick={_handleConfirm}
                    disabled={applying}
                    className="flex-1 rounded-lg bg-primary px-6 py-2.5 text-label-md text-on-primary hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {applying ? "Starting…" : "Confirm"}
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </dialog>
    </>
  );
}
