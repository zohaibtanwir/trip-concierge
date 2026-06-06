/**
 * Server Actions — slice 4.3.
 *
 * Each action mints a fresh MCP token (same pattern as fetchTripList /
 * fetchTripDetail) and POSTs to the backend. Errors throw BackendError
 * so the caller (RSC page, client component) can surface them through
 * Next.js's error boundary or via a try/catch with user feedback.
 *
 * Future Server Actions (4.5 refine, 4.6 regenerate_day) accumulate
 * here. Each one follows the same shape: mint → POST → BackendError on
 * non-2xx.
 */

"use server";

import { BackendError, mintMcpToken, type PlanStatus } from "@/lib/backend";
import { env } from "@/lib/env";

/**
 * planAgainAction — invoked by <PlanAgainDialog /> on failed trips per
 * the slice 4.2 Q9 / slice 4.3 design. Triggers a full replan via the
 * existing backend route (POST /trips/{id}/plan from slice 2.5b).
 *
 * Returns the new PlanStatus shape from the enqueue response so the
 * caller can update local UI optimistically.
 *
 * NOTE on signature: positional args; will refactor to object args under
 * trip-concierge-u8v when the next slice consumes the pattern.
 * addConstraintAction below is the first object-args Server Action.
 */
export async function planAgainAction(tripId: string, userId: string): Promise<PlanStatus> {
  const { mcp_token } = await mintMcpToken({ userId });
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}/plan`, {
    method: "POST",
    headers: { "x-tc-token": mcp_token },
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `planAgainAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as PlanStatus;
}

/**
 * addConstraintAction — invoked by <ConstraintPanel /> on the trip
 * detail page (slice 4.5). Consumes the existing slice-3.4a endpoint
 * POST /trips/{id}/constraints which appends to Trip.constraints["rules"]
 * AND auto-enqueues a refine job to incorporate the new constraint.
 *
 * Object-args pattern (first Server Action to adopt). Per
 * trip-concierge-u8v, planAgainAction refactors to the same shape in a
 * future slice for consistency.
 *
 * Caller-facing semantics: the user's plan is replaced with a refined
 * version (~5-10 min). The constraint-panel UI surfaces this timing
 * before the user submits — see spec §9.13.
 */
export interface AddConstraintResult {
  job_id: string;
  status_url: string;
}

export type ConstraintKind =
  | "budget"
  | "dietary"
  | "mobility"
  | "no_go"
  | "walking_limit"
  | "accessibility"
  | "custom";

export async function addConstraintAction({
  tripId,
  userId,
  kind,
  text,
}: {
  tripId: string;
  userId: string;
  kind: ConstraintKind;
  text: string;
}): Promise<AddConstraintResult> {
  const { mcp_token } = await mintMcpToken({ userId });
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}/constraints`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-tc-token": mcp_token,
    },
    body: JSON.stringify({
      constraint_text: text,
      constraint_kind: kind,
    }),
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `addConstraintAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as AddConstraintResult;
}
