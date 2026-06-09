/**
 * ViewAgentTraceLink — replay-mode entry point for the planning theater.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 4. Small link/button in
 * the terminal-state trip detail header. Click → modal containing the
 * full PlanningTheater in replay mode, driven by agent_summary from the
 * already-completed JobRun (Q-impl-249-s=A: same component, two data
 * sources — live polls; replay consumes prop).
 *
 * Modal pattern: spec §9.18 imperative-useEffect (hotfix-nwk hardened).
 * Native <dialog>, showModal/close called from useEffect on the open
 * state, backdrop click + native Escape close. NO declarative `open`
 * attribute — that path throws InvalidStateError inside showModal and
 * leaves the dialog non-modal (real bug, vitest.setup.ts polyfill
 * mirrors it).
 *
 * Replay mode propagation: PlanningTheater receives mode="replay" and
 * the events prop. usePlanStatusPoll fires with disabled:true and
 * short-circuits — no fetchPlanStatusAction call, no polling for a
 * terminal trip.
 *
 * Density preference (Q-impl-249-t=C): the modal's EventDensityToggle
 * reads/writes the same sessionStorage key ("theater-density") as live
 * mode. Last choice survives across live → replay → live again.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { PlanningTheater } from "@/components/planning-theater";
import type { AgentSummaryRow } from "@/lib/backend";

interface ViewAgentTraceLinkProps {
  tripId: string;
  userId: string;
  agentSummary: AgentSummaryRow[];
}

export function ViewAgentTraceLink({ tripId, userId, agentSummary }: ViewAgentTraceLinkProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (open && !dlg.open) {
      dlg.showModal();
    } else if (!open && dlg.open) {
      dlg.close();
    }
  }, [open]);

  function _backdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) setOpen(false);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 text-label-md text-primary hover:underline"
      >
        <span className="material-symbols-outlined text-base" aria-hidden>
          visibility
        </span>
        View agent trace
      </button>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: backdrop click has a keyboard
          equivalent — Escape, wired via onClose; there is no "outside-click" key. */}
      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={_backdropClick}
        className="rounded-xl bg-surface-container-lowest p-0 border border-outline-variant shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm m-auto max-w-4xl w-[calc(100%-2rem)]"
      >
        {open && (
          <div className="p-6 max-h-[85vh] overflow-y-auto">
            <div className="mb-4 flex items-center justify-end">
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="material-symbols-outlined text-on-surface-variant hover:text-on-surface transition-colors p-1"
              >
                close
              </button>
            </div>
            <PlanningTheater mode="replay" tripId={tripId} userId={userId} events={agentSummary} />
          </div>
        )}
      </dialog>
    </>
  );
}
