/**
 * HTTP wrappers for the PWA → backend boundary.
 *
 * Three helpers ship from this module:
 *   - mintMcpToken({ userId })     — slice 4.1: signIn callback
 *                                    side effect + per-request mint by
 *                                    the slice 4.2 PWA pages.
 *   - fetchTripList({ userId })    — slice 4.2: list page server data.
 *   - fetchTripDetail({...})       — slice 4.2: detail page server data
 *                                    (Promise.all over /full + /plan/status).
 *
 * Per-request mint pattern (slice 4.2 design dialogue Q3): each page
 * render mints a fresh JWT via the internal endpoint, then forwards it
 * as `x-tc-token`. Costs ~50ms per page (a JWT signing) but avoids
 * session-cache staleness bugs around token expiry, email changes,
 * and admin revocation. Cache discussion deferred to a future P3
 * if the latency becomes user-visible.
 *
 * Errors: helpers throw `BackendError` carrying the HTTP status code
 * so the RSC layer can branch on it. v1.0a relies on Next.js's default
 * error boundary to surface unhandled throws — the pages don't catch.
 */

import { env } from "@/lib/env";

export interface MintResult {
  mcp_token: string;
  expires_at: string;
}

export interface TripListItem {
  id: string;
  destination: string;
  start_date: string | null;
  end_date: string | null;
  currency: string;
  budget_total: string | null;
  state: "succeeded" | "failed" | "planning" | "no_job";
  created_at: string;
}

export interface TripListResponse {
  items: TripListItem[];
}

export interface BlockSource {
  id: string;
  url: string;
  source_type: string;
  excerpt: string;
  confidence_score: string | null;
}

export interface Block {
  id: string;
  order: number;
  type: string;
  venue_name: string;
  lat: string | null;
  lng: string | null;
  start_time: string | null;
  duration_minutes: number;
  est_cost: string | null;
  currency: string;
  locked: boolean;
  notes: string;
  sources: BlockSource[];
}

export interface TripDay {
  id: string;
  day_number: number;
  date: string | null;
  summary: string;
  blocks: Block[];
}

export interface TripFull {
  id: string;
  user_id: string;
  status: string;
  destination: string;
  start_date: string | null;
  end_date: string | null;
  group_size: number;
  budget_total: string | null;
  currency: string;
  constraints: Record<string, unknown>;
  pace: string;
  created_at: string;
  updated_at: string;
  days: TripDay[];
}

export interface AgentSummaryRow {
  agent: string;
  step: number;
  duration_ms: number;
  tokens?: number;
}

export interface PlanStatus {
  state: "queued" | "running" | "cancelling" | "done" | "failed" | "cancelled" | "no_job";
  approved: boolean | null;
  job_id: string | null;
  kind: string | null;
  progress_message?: { agent: string; pass: number; message: string } | null;
  error?: string | null;
  // Slice 4.3 — PRD §F8 partial. Surface from backend PlanStatus
  // schema. Empty list on legacy JobRuns (pre-qek-a); null on
  // synthesized no_job state (no JobRun row exists at all).
  agent_summary?: AgentSummaryRow[] | null;
}

export interface TripDetail {
  trip: TripFull;
  planStatus: PlanStatus;
}

export class BackendError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "BackendError";
    this.status = status;
  }
}

export async function mintMcpToken({ userId }: { userId: string }): Promise<MintResult> {
  const response = await fetch(`${env.BACKEND_URL}/internal/auth/mint-mcp-token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Secret": env.INTERNAL_AUTH_SECRET,
    },
    body: JSON.stringify({ user_id: userId }),
  });

  if (!response.ok) {
    // SECURITY NOTE: The error body is interpolated into the message.
    // Today this is safe because /internal/auth/mint-mcp-token's error
    // responses are hard-coded to fixed strings (e.g., "invalid internal
    // secret"). Backend error bodies for this endpoint MUST NOT echo
    // received headers or request bodies — that would surface
    // INTERNAL_AUTH_SECRET in Next.js error pages. See
    // backend/app/routes/auth.py:166-171.
    throw new Error(`mint_mcp_token HTTP ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as MintResult;
}

export async function fetchTripList({ userId }: { userId: string }): Promise<TripListItem[]> {
  const { mcp_token } = await mintMcpToken({ userId });
  const response = await fetch(`${env.BACKEND_URL}/trips`, {
    headers: { "x-tc-token": mcp_token },
  });
  if (!response.ok) {
    throw new BackendError(
      response.status,
      `fetchTripList HTTP ${response.status}: ${await response.text()}`,
    );
  }
  const body = (await response.json()) as TripListResponse;
  return body.items;
}

export async function fetchTripDetail({
  userId,
  tripId,
}: {
  userId: string;
  tripId: string;
}): Promise<TripDetail> {
  const { mcp_token } = await mintMcpToken({ userId });
  const headers = { "x-tc-token": mcp_token };

  // Promise.all fires both calls concurrently. Short-circuit reject
  // semantics: if either rejects (a network error), the helper throws
  // immediately. Mid-tier semantics (200 vs 4xx vs 5xx) are handled
  // per-response below — Promise.all only cares about settled vs
  // rejected, not about response.ok.
  const [fullResp, statusResp] = await Promise.all([
    fetch(`${env.BACKEND_URL}/trips/${tripId}/full`, { headers }),
    fetch(`${env.BACKEND_URL}/trips/${tripId}/plan/status`, { headers }),
  ]);

  // /full is the load-bearing call — if the trip doesn't exist, the
  // user doesn't have access, or the backend is down, we throw.
  if (!fullResp.ok) {
    throw new BackendError(
      fullResp.status,
      `fetchTripDetail /full HTTP ${fullResp.status}: ${await fullResp.text()}`,
    );
  }
  const trip = (await fullResp.json()) as TripFull;

  // /plan/status has one tolerable failure: 404, which the backend
  // returns when no JobRun row has been written yet for this trip.
  //
  // Slice 4.2 tightening: 404 alone is ambiguous between "worker
  // enqueued the job but hasn't written its terminal JobRun yet"
  // (planning UX) and "no plan attempt ever made" (no_job UX). Hit
  // the internal active-job endpoint to disambiguate via Redis —
  // matches the list endpoint's Postgres+Redis dual-read pattern.
  //
  // Any other /plan/status code (401, 403, 5xx) means the call itself
  // failed — those propagate as BackendError so Next.js's error
  // boundary surfaces them.
  let planStatus: PlanStatus;
  if (statusResp.ok) {
    planStatus = (await statusResp.json()) as PlanStatus;
  } else if (statusResp.status === 404) {
    planStatus = await _probeActiveJobOr404(tripId);
  } else {
    throw new BackendError(
      statusResp.status,
      `fetchTripDetail /plan/status HTTP ${statusResp.status}: ${await statusResp.text()}`,
    );
  }

  return { trip, planStatus };
}

async function _probeActiveJobOr404(tripId: string): Promise<PlanStatus> {
  // Internal-secret-authenticated probe. The PWA server (not the browser)
  // calls this — same trust model as mintMcpToken. Returns
  // {active: bool}; we translate to either a synthesized 'running'
  // PlanStatus (planning UX) or a synthesized 'no_job' (genuinely
  // unplanned).
  //
  // A graceful-degradation note: if the internal endpoint itself
  // errors (network, 5xx, etc.), we fall back to 'no_job' rather than
  // throwing. The /plan/status 404 path is already the "we couldn't
  // confirm a job exists" branch; degrading silently to no_job
  // preserves the page-renders-at-all guarantee. The UX cost: an
  // in-flight planning trip shows 'no_job' until the internal probe
  // recovers. Symmetric with the list endpoint's graceful-degradation
  // pattern. See trip-concierge-pdo for the narrower-exception
  // followup that applies equally here.
  try {
    const response = await fetch(`${env.BACKEND_URL}/internal/trips/${tripId}/active-job`, {
      headers: { "X-Internal-Secret": env.INTERNAL_AUTH_SECRET },
    });
    if (!response.ok) {
      return { state: "no_job", approved: null, job_id: null, kind: null };
    }
    const body = (await response.json()) as { active: boolean };
    if (body.active) {
      return { state: "running", approved: null, job_id: null, kind: "plan" };
    }
    return { state: "no_job", approved: null, job_id: null, kind: null };
  } catch {
    return { state: "no_job", approved: null, job_id: null, kind: null };
  }
}
