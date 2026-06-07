/**
 * ConstraintPanel — responsive wrapper for ConstraintForm (slice 4.5).
 *
 * Mirror of slice 4.3 BlockExpand's pattern: `forceVariant` prop pins
 * each variant in jsdom without simulating real viewport changes.
 * Production callers pass the resolved variant from a useMediaQuery
 * hook (deferred — current page integration uses forceVariant="inline"
 * for desktop layout; mobile collapse handled by the page-level grid).
 *
 * onSubmit semantics: each non-empty section in ConstraintForm produces
 * one {kind, text} entry; this wrapper fires addConstraintAction
 * sequentially for each entry. Backend's POST /trips/{id}/constraints
 * accepts one constraint per call AND auto-enqueues a refine job. If
 * the user submits dietary + accessibility together, the SECOND POST
 * will surface a 409 (active job conflict). This is correct UX in v1.0a:
 * one constraint per refine cycle is the supported workflow. Multi-
 * constraint submit is a v1.0b refinement tracked separately.
 */

"use client";

import { ConstraintForm, type ConstraintSubmission } from "@/components/constraint-form";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { addConstraintAction } from "@/lib/actions";

interface ConstraintPanelProps {
  tripId: string;
  userId: string;
  existingRules: Array<{ kind: string; value: string; raw_text: string }>;
  // Slice 4d0 smoke (2026-06-07): added so the per-day budget input in
  // ConstraintForm renders the trip's actual currency, not the default
  // USD. Slice 4.5b commit 3 added currency? on ConstraintForm but
  // didn't thread it from the page.tsx caller through this wrapper.
  currency?: string;
  forceVariant?: "sheet" | "inline";
}

export function ConstraintPanel({
  tripId,
  userId,
  currency,
  forceVariant = "inline",
}: ConstraintPanelProps) {
  async function _handleSubmit(entries: ConstraintSubmission[]) {
    for (const entry of entries) {
      await addConstraintAction({
        tripId,
        userId,
        kind: entry.kind,
        text: entry.text,
      });
    }
  }

  if (forceVariant === "sheet") {
    return (
      <Sheet>
        <SheetTrigger render={<Button variant="outline">Edit constraints</Button>} />
        <SheetContent side="bottom">
          <div className="p-4">
            <h2 className="text-headline-md text-on-surface mb-4">Constraints</h2>
            <ConstraintForm onSubmit={_handleSubmit} currency={currency} />
          </div>
        </SheetContent>
      </Sheet>
    );
  }

  return (
    <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
      <h2 className="text-label-md text-on-surface mb-4">Constraints</h2>
      <ConstraintForm onSubmit={_handleSubmit} currency={currency} />
    </div>
  );
}
