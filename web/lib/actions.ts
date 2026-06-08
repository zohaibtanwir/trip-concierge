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

import { BackendError, type Block, mintMcpToken, type PlanStatus } from "@/lib/backend";
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

/**
 * updateTripSettingsAction — invoked by <PlanControlsPanel /> on the
 * trip detail page (slice 4.5b). Consumes the new slice-4.5b PATCH
 * /trips/{id} route which updates the Trip.pace + Trip.budget_total
 * columns AND auto-enqueues a refine job to incorporate the new
 * settings.
 *
 * Settings-vs-rules distinction: pace and budget_total are *column
 * writes* (settings overwrite — last value wins). The companion
 * addConstraintAction above handles *rule appends* (constraints
 * accumulate). Two object-args Server Actions, two backend paths
 * (PATCH vs POST), aligned at every layer.
 *
 * Omit-undefined serialization: only fields the user explicitly
 * changed appear in the PATCH body. The backend's at-least-one-of
 * validator would 422 an empty body; the UI prevents that round-trip
 * by no-op'ing submit when nothing changed.
 */
export type TripPace = "packed" | "balanced" | "lazy";

export interface UpdateTripSettingsResult {
  job_id: string;
  status_url: string;
}

export async function updateTripSettingsAction({
  tripId,
  userId,
  pace,
  budgetTotal,
}: {
  tripId: string;
  userId: string;
  pace?: TripPace;
  budgetTotal?: number;
}): Promise<UpdateTripSettingsResult> {
  const { mcp_token } = await mintMcpToken({ userId });
  const body: Record<string, unknown> = {};
  if (pace !== undefined) body.pace = pace;
  if (budgetTotal !== undefined) body.budget_total = budgetTotal;
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "x-tc-token": mcp_token,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `updateTripSettingsAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as UpdateTripSettingsResult;
}

/**
 * createTripAction — invoked by <NewTripDialog />'s "Create here" tab
 * (slice 4.5c commit 3.5). Discharges the Sunday-smoke product gap:
 * users without Claude Desktop can now plan a trip directly from the
 * web app. Same backend endpoint the MCP `create_trip` tool calls.
 *
 * Two-call wire shape:
 *   1. POST /trips with TripCreate payload → returns the new trip row
 *   2. POST /trips/{trip_id}/plan to enqueue the crew planning arq job
 *
 * Returns just `{ trip_id }`; the dialog handles `useRouter().push()`
 * to `/trips/[trip_id]` per Q3.5-impl-a sign-off (keep action pure
 * data-shape, dialog owns UX flow).
 *
 * Omit-undefined for optional fields per the established pattern —
 * Pydantic accepts missing date fields differently than null, so we
 * never send a property unless the user provided a value. Vibe is
 * intentionally absent — vibe is a refine-time concern per the
 * TripCreate schema and the architectural decision in Q-product-2.
 */
export interface CreateTripResult {
  trip_id: string;
}

export async function createTripAction({
  userId,
  destination,
  startDate,
  endDate,
  groupSize,
  budgetTotal,
  currency,
  pace,
}: {
  userId: string;
  destination: string;
  startDate?: string;
  endDate?: string;
  groupSize: number;
  budgetTotal?: number;
  currency: string;
  pace: TripPace;
}): Promise<CreateTripResult> {
  const { mcp_token } = await mintMcpToken({ userId });

  // Build POST /trips body — omit undefined optional fields.
  const createBody: Record<string, unknown> = {
    destination,
    group_size: groupSize,
    currency,
    pace,
  };
  if (startDate !== undefined) createBody.start_date = startDate;
  if (endDate !== undefined) createBody.end_date = endDate;
  if (budgetTotal !== undefined) createBody.budget_total = budgetTotal;

  const createRes = await fetch(`${env.BACKEND_URL}/trips`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-tc-token": mcp_token },
    body: JSON.stringify(createBody),
  });
  if (!createRes.ok) {
    throw new BackendError(
      createRes.status,
      `createTripAction (POST /trips) HTTP ${createRes.status}: ${await createRes.text()}`,
    );
  }
  const trip = (await createRes.json()) as { id: string };

  // POST /trips/{trip_id}/plan — enqueue the crew. Body is the
  // TripRunRequest shape; the backend's _build_request() snapshots
  // from the Trip row, so we send an empty body and the backend
  // composes the full request server-side.
  const planRes = await fetch(`${env.BACKEND_URL}/trips/${trip.id}/plan`, {
    method: "POST",
    headers: { "x-tc-token": mcp_token },
  });
  if (!planRes.ok) {
    throw new BackendError(
      planRes.status,
      `createTripAction (POST /trips/{id}/plan) HTTP ${planRes.status}: ${await planRes.text()}`,
    );
  }

  return { trip_id: trip.id };
}

/**
 * regenerateDayAction — invoked by <RegenerateDayDialog /> on the
 * trip detail page (slice 4.6 commit 2). Consumes the existing
 * slice-3.3 endpoint POST /trips/{tripId}/days/{dayNumber}/regenerate
 * which enqueues a day-scoped arq job (~3-5 min wall time). Locked
 * blocks on the day are preserved per slice 3.3's hard contract.
 *
 * Object-args pattern (matches addConstraint / createTrip /
 * updateTripSettings). Returns the {job_id, status_url} pair the
 * backend route emits; caller (dialog) navigates via router.push to
 * the trip detail page where slice 4.2's planning-state UX takes
 * over.
 *
 * Hint is optional at every layer:
 *   - UI textarea has no required attribute
 *   - This action's hint param is `string?`
 *   - Backend RegenerateRequest.hint: str | None = None
 * Empty submit is a clean "regenerate this day with no specific
 * guidance" call.
 */
export interface RegenerateDayResult {
  job_id: string;
  status_url: string;
}

export async function regenerateDayAction({
  userId,
  tripId,
  dayNumber,
  hint,
}: {
  userId: string;
  tripId: string;
  dayNumber: number;
  hint?: string;
}): Promise<RegenerateDayResult> {
  const { mcp_token } = await mintMcpToken({ userId });
  const body: Record<string, unknown> = {};
  if (hint !== undefined && hint.trim() !== "") body.hint = hint.trim();
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}/days/${dayNumber}/regenerate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-tc-token": mcp_token,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `regenerateDayAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as RegenerateDayResult;
}

/**
 * findAlternativeAction — invoked by <BlockAlternativeDialog /> on
 * the trip detail page (slice 4.6 commit 3). Consumes the slice-3.4a
 * SYNCHRONOUS endpoint POST /trips/{tripId}/blocks/{blockId}/alternative
 * which runs the find_alternative crew inline (~90s wall time, 90s
 * timeout ceiling at the backend) and returns 3 ranked Alternative
 * options.
 *
 * Object-args pattern (matches addConstraint / createTrip / updateTrip /
 * regenerateDay). Returns the backend's AlternativesList.model_dump()
 * shape verbatim — the dialog renders the array of cards directly.
 *
 * Reason is optional at every layer:
 *   - UI textarea has no required attribute
 *   - This action's reason param is `string?`
 *   - Backend AlternativeRequest.reason: str | None = None
 * Empty submit is a clean "find me something else" call.
 *
 * 90s wait note: this is the only Server Action in the app that
 * blocks the caller for nearly a minute. The dialog shows a spinner
 * + agent-specialization disclosure during the wait. On 504 the
 * action throws BackendError(504) and the dialog surfaces a
 * "try again" message.
 */
export interface Alternative {
  venue_name: string;
  type: string;
  duration_minutes: number;
  est_cost: number;
  currency: string;
  source_urls: string[];
  rationale: string;
}

export interface FindAlternativeResult {
  alternatives: Alternative[];
}

export async function findAlternativeAction({
  userId,
  tripId,
  blockId,
  reason,
}: {
  userId: string;
  tripId: string;
  blockId: string;
  reason?: string;
}): Promise<FindAlternativeResult> {
  const { mcp_token } = await mintMcpToken({ userId });
  const body: Record<string, unknown> = {};
  if (reason !== undefined && reason.trim() !== "") body.reason = reason.trim();
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}/blocks/${blockId}/alternative`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-tc-token": mcp_token,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `findAlternativeAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as FindAlternativeResult;
}

/**
 * applyAlternativeAction — invoked by <BlockAlternativeDialog /> after
 * the user picks one of the 3 alternatives returned by
 * findAlternativeAction (slice 4.6 commit 3).
 *
 * Q4=A apply-via-refine semantics: rather than write the chosen
 * alternative directly into the Block row, we synthesize a
 * refinement_description and enqueue a refine_trip job. The crew runs
 * the swap through the hierarchical refine pipeline, which preserves
 * the Budget Auditor invariant (sub-budget per day still checked) and
 * keeps the apply path identical to every other user-driven trip
 * mutation. ~10 min wall time; the dialog redirects to the trip page
 * where slice-4.2's planning-state UX takes over.
 *
 * Synthesis text shape (option b — sign-off 2026-06-08):
 *   - Always: "On Day {N}, replace '{oldVenueName}' with '{alternativeVenueName}'."
 *   - When reason: " Reason: {reason}." appended (load-bearing — the
 *     crew sees the WHY behind the swap, not just the WHAT).
 *
 * The reason is carried through from the find-alternative step's
 * textarea (collected once, threaded both places).
 */
export interface ApplyAlternativeResult {
  job_id: string;
  status_url: string;
}

export async function applyAlternativeAction({
  userId,
  tripId,
  dayNumber,
  oldVenueName,
  alternativeVenueName,
  reason,
}: {
  userId: string;
  tripId: string;
  dayNumber: number;
  oldVenueName: string;
  alternativeVenueName: string;
  reason?: string;
}): Promise<ApplyAlternativeResult> {
  const { mcp_token } = await mintMcpToken({ userId });
  let refinement_description = `On Day ${dayNumber}, replace '${oldVenueName}' with '${alternativeVenueName}'.`;
  if (reason !== undefined && reason.trim() !== "") {
    refinement_description += ` Reason: ${reason.trim()}.`;
  }
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}/refine`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-tc-token": mcp_token,
    },
    body: JSON.stringify({ refinement_description }),
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `applyAlternativeAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as ApplyAlternativeResult;
}

/**
 * setBlockLockAction — invoked by <BlockLockToggle /> on the trip
 * detail page (slice 4.6 commit 4). Consumes the slice-4.6 commit-1
 * route PATCH /trips/{tripId}/blocks/{blockId} with body {locked}.
 *
 * Metadata-only column write — no Redis touch, no arq enqueue. The
 * regenerate_day worker reads the locked snapshot at dispatch time
 * per slice 3.3's hard contract; toggling during in-flight regen is
 * observed at the next dispatch. No 409 guard at the backend.
 *
 * Returns the full BlockRead so the optimistic UI can reconcile
 * against the server's canonical state. Per Q-impl-c4a fallback (no
 * toast primitive in project) the dialog surface handles rejection
 * via an inline error badge that auto-clears after 3 seconds.
 */
export async function setBlockLockAction({
  userId,
  tripId,
  blockId,
  locked,
}: {
  userId: string;
  tripId: string;
  blockId: string;
  locked: boolean;
}): Promise<Block> {
  const { mcp_token } = await mintMcpToken({ userId });
  const response = await fetch(`${env.BACKEND_URL}/trips/${tripId}/blocks/${blockId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "x-tc-token": mcp_token,
    },
    body: JSON.stringify({ locked }),
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `setBlockLockAction HTTP ${response.status}: ${await response.text()}`,
    );
  }
  return (await response.json()) as Block;
}
