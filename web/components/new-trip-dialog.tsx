/**
 * NewTripDialog — two-paths trip creation (slice 4.5c commit 3.5).
 *
 * Restructured from commit 3's MCP-only dialog to a two-paths dialog
 * that discharges the Sunday-smoke "Claude Desktop dependency" product
 * gap. Two tabs:
 *
 *   - "Create here" (default) — inline web form via <NewTripForm />.
 *     POSTs to /trips + /trips/{id}/plan via createTripAction, then
 *     redirects to /trips/[trip_id].
 *   - "Create in Claude Desktop" — MCP-first content from commit 3:
 *     explanation paragraph, copy-to-clipboard prompt template,
 *     claude.ai/download link.
 *
 * Q3.5 sign-offs:
 *   - useRouter().push() for post-create navigation (dialog owns UX,
 *     action stays pure data-shape)
 *   - Bare <button role="tab"> tabs (no library; consistent with
 *     PlanHistoryPanel <details>)
 *   - Default tab = "Create here" (friction-free path)
 *
 * `defaultOpen` prop drives the auto-open behavior when /trips lands
 * with `?new=true` searchParam (Critique 1 — Hero "Plan a trip" CTA
 * routes here). Required for the new-trip CTA flow; defaults to false
 * so existing /trips usage is unchanged.
 *
 * `userId` is required ONLY for the form path. MCP-only callers can
 * omit it; the dialog renders only the MCP tab if userId is absent.
 */

"use client";

import { useEffect, useRef, useState } from "react";

import { NewTripForm } from "@/components/new-trip-form";

const _PROMPT_TEMPLATE = `Use trip-concierge to plan a 3-day trip to [DESTINATION] for [N] people, budget [AMOUNT] [CURRENCY], [pace: balanced/packed/lazy], [vibe].`;

type TabKey = "form" | "mcp";

interface NewTripDialogProps {
  triggerLabel: string;
  userId?: string;
  defaultOpen?: boolean;
}

export function NewTripDialog({ triggerLabel, userId, defaultOpen = false }: NewTripDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null);
  const [open, setOpen] = useState(defaultOpen);
  const [activeTab, setActiveTab] = useState<TabKey>("form");
  const [copied, setCopied] = useState(false);

  // Hotfix-nwk modal-mode pattern (spec §9.18). NO declarative `open`
  // attribute — useEffect drives showModal/close imperatively so the
  // dialog enters top-layer modal mode. Replaces both the prior
  // `defaultOpen` useEffect AND the queueMicrotask inside _openDialog —
  // one effect covers all open→close transitions including auto-open.
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
    setCopied(false);
  }

  function _backdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) _closeDialog();
  }

  async function _copyPrompt() {
    try {
      await navigator.clipboard.writeText(_PROMPT_TEMPLATE);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Modern-only clipboard per Q3-impl-b.
    }
  }

  // The form path requires userId. If absent, hide the form tab and
  // only show the MCP path — fallback shape so MCP-only callers (legacy
  // or future) still work.
  const showFormTab = Boolean(userId);

  return (
    <>
      <button
        type="button"
        onClick={_openDialog}
        className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-primary/90 transition-colors"
      >
        {triggerLabel}
      </button>
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: backdrop click has a keyboard
          equivalent — Escape, wired via onClose; there is no "outside-click" key. */}
      <dialog
        ref={dialogRef}
        onClose={() => setOpen(false)}
        onClick={_backdropClick}
        className="rounded-xl bg-surface-container-lowest p-0 border border-outline-variant shadow-2xl backdrop:bg-black/40 backdrop:backdrop-blur-sm m-auto max-w-2xl w-[calc(100%-2rem)]"
      >
        {open && (
          <div className="p-6 max-h-[80vh] overflow-y-auto">
            <div className="flex items-start justify-between gap-4 mb-4">
              <h2 className="text-headline-sm text-on-surface">Plan a new trip</h2>
              <button
                type="button"
                onClick={_closeDialog}
                aria-label="Close"
                className="material-symbols-outlined text-on-surface-variant hover:text-on-surface transition-colors text-base p-1"
              >
                close
              </button>
            </div>

            {showFormTab && (
              <div role="tablist" className="flex gap-1 mb-4 border-b border-outline-variant">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "form"}
                  onClick={() => setActiveTab("form")}
                  className={`px-4 py-2 text-label-md transition-colors border-b-2 -mb-px ${
                    activeTab === "form"
                      ? "text-primary border-primary"
                      : "text-on-surface-variant border-transparent hover:text-on-surface"
                  }`}
                >
                  Create here
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "mcp"}
                  onClick={() => setActiveTab("mcp")}
                  className={`px-4 py-2 text-label-md transition-colors border-b-2 -mb-px ${
                    activeTab === "mcp"
                      ? "text-primary border-primary"
                      : "text-on-surface-variant border-transparent hover:text-on-surface"
                  }`}
                >
                  Create in Claude Desktop
                </button>
              </div>
            )}

            {showFormTab && activeTab === "form" && userId && (
              <div>
                <p className="text-body-md text-on-surface-variant mb-4">
                  Fill in the basics. The 4-agent crew (Researcher, Local Expert, Logistics, Budget
                  Auditor) handles the rest — ~10 min wall time.
                </p>
                <NewTripForm userId={userId} onSuccess={_closeDialog} />
              </div>
            )}

            {(!showFormTab || activeTab === "mcp") && (
              <div>
                <p className="text-body-md text-on-surface-variant mb-4">
                  Trip planning involves 4 specialized agents and ~10 min of computation. Claude
                  Desktop is a great host for that conversation — context window, multi-turn flow,
                  and tool-call timing for a multi-agent crew. The result persists here, in the web
                  app, so you can refine it later.
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
                  For users who prefer conversational planning. The web form on the "Create here"
                  tab is the friction-free path; this Claude Desktop flow is for power users with
                  the desktop app installed.
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
            )}
          </div>
        )}
      </dialog>
    </>
  );
}
