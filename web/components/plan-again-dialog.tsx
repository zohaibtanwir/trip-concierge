/**
 * PlanAgainDialog — Server Action confirm dialog for full replan on
 * failed trips.
 *
 * Slice 4.3, Q9 — failed-only gate enforced by the parent (detail
 * page). This component is reusable on any failed surface. Renders a
 * "Plan again" button that opens a shadcn Dialog with a confirmation
 * body + a confirm action that dispatches the passed action prop with
 * tripId.
 *
 * The `action` prop is typed loosely (a function taking tripId) so the
 * caller can pass either the actual Server Action (planAgainAction
 * from web/lib/actions.ts) or a mock in tests. The component itself
 * doesn't import the action — the caller wires it.
 */

"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

interface PlanAgainDialogProps {
  tripId: string;
  action: (tripId: string) => void | Promise<void>;
}

export function PlanAgainDialog({ tripId, action }: PlanAgainDialogProps) {
  const [pending, setPending] = useState(false);

  async function _confirm() {
    setPending(true);
    try {
      await action(tripId);
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog>
      <DialogTrigger render={<Button variant="default">Plan again</Button>} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start a new plan?</DialogTitle>
          <DialogDescription>
            This will replace the failed plan with a new run. The previous attempt's history is
            preserved in your trip activity log.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="default" onClick={_confirm} disabled={pending}>
            {pending ? "Starting…" : "Yes, plan again"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
