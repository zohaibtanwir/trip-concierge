/**
 * NewTripDialog — MCP-first trip creation explainer (slice 4.5c commit 3).
 *
 * Used on /trips at two surfaces (Q6=A consolidation):
 *   - Top-right "New trip" CTA (users who already have trips)
 *   - Empty-state primary button "Plan your first trip" (no trips yet)
 * Both instances render the SAME dialog content — only triggerLabel
 * differs.
 *
 * Implementation choices:
 * - Native HTML <dialog> via showModal() (Q3-impl-a sign-off). Focus
 *   trap, escape-to-close, backdrop click — all free from the platform.
 * - navigator.clipboard.writeText only, no execCommand fallback
 *   (Q3-impl-b sign-off — modern-only is the v1.0a posture).
 * - claude.ai/download opens in new tab (target="_blank") so users
 *   don't lose their dialog state.
 *
 * Copy reflects the user's narrative explicitly: WHY creation lives in
 * Claude Desktop, not just HOW to do it. The 4-agent / ~10-minute
 * detail is load-bearing per Q3.
 */

"use client";

import { useRef, useState } from "react";

const _PROMPT_TEMPLATE = `Use trip-concierge to plan a 3-day trip to [DESTINATION] for [N] people, budget [AMOUNT] [CURRENCY], [pace: balanced/packed/lazy], [vibe].`;

interface NewTripDialogProps {
  triggerLabel: string;
}

export function NewTripDialog({ triggerLabel }: NewTripDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  function _openDialog() {
    setOpen(true);
    // Defer to next tick so the dialog element is mounted, then call
    // showModal() to get native modal semantics (focus trap, escape,
    // backdrop). Wrapped in try/catch because jsdom (vitest) doesn't
    // implement HTMLDialogElement.showModal — in that env the dialog
    // content is still in the DOM via the conditional render, just
    // without the modal behavior. Real browsers get the full
    // platform primitive.
    queueMicrotask(() => {
      try {
        dialogRef.current?.showModal();
      } catch {
        // jsdom or older browsers without <dialog> support.
      }
    });
  }

  function _closeDialog() {
    // Guard for jsdom (no HTMLDialogElement.close). Real browsers
    // get the native close which cleans up modal state; tests rely on
    // the conditional render driven by `open` state below.
    try {
      dialogRef.current?.close();
    } catch {
      // jsdom or older browsers.
    }
    setOpen(false);
    setCopied(false);
  }

  async function _copyPrompt() {
    try {
      await navigator.clipboard.writeText(_PROMPT_TEMPLATE);
      setCopied(true);
      // Reset the "copied" state after a brief moment so the user can
      // copy again if they want.
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Modern-only clipboard per Q3-impl-b: if unavailable, button is
      // a no-op; user can manually select the visible template text.
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={_openDialog}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-primary/90 transition-colors"
      >
        {triggerLabel}
      </button>
      {open && (
        <dialog
          open
          ref={dialogRef}
          onClose={() => setOpen(false)}
          className="rounded-xl bg-surface-container-lowest p-0 border border-outline-variant shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm m-auto max-w-2xl w-[calc(100%-2rem)]"
        >
          <div className="p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h2 className="text-headline-sm text-on-surface">
                Plan your next trip from Claude Desktop
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
            <p className="text-body-md text-on-surface-variant mb-4">
              Trip planning involves 4 specialized agents and ~10 min of computation. Claude Desktop
              is the right host for that conversation — it has the context window, the multi-turn
              flow, and the tool-call timing needed for a multi-agent crew to complete a real trip.
              The result persists here, in the web app, so you can refine it later.
            </p>
            <div className="rounded-lg border border-outline-variant bg-surface-container-low p-3 mb-2">
              <pre className="whitespace-pre-wrap text-body-md text-on-surface font-mono text-sm">
                {_PROMPT_TEMPLATE}
              </pre>
            </div>
            <div className="flex items-center justify-end mb-4">
              <button
                type="button"
                onClick={_copyPrompt}
                className="inline-flex items-center gap-2 rounded-md bg-surface-container-low px-3 py-1.5 text-label-sm text-on-surface hover:bg-surface-container transition-colors"
              >
                <span className="material-symbols-outlined text-base" aria-hidden>
                  {copied ? "check" : "content_copy"}
                </span>
                {copied ? "Copied" : "Copy prompt"}
              </button>
            </div>
            <p className="text-label-sm text-on-surface-variant italic mb-4">
              Trip Concierge is currently web-only via Claude Desktop. A standalone mobile/web
              creation flow is on the v1.0b roadmap.
            </p>
            <a
              href="https://claude.ai/download"
              target="_blank"
              rel="noopener noreferrer"
              className="text-label-md text-primary hover:underline"
            >
              Don't have Claude Desktop? Download it →
            </a>
          </div>
        </dialog>
      )}
    </>
  );
}
