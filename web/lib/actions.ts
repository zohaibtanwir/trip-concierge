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
