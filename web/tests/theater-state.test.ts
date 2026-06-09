/**
 * theater-state — pure-function tests (slice 4.7-theater commit 2).
 *
 * `deriveAgentStates(events)` maps an AgentSummaryRow[] stream into a
 * per-agent-role state map consumed by the 4-up AgentCard grid. The
 * map is keyed by the canonical CrewAI role string ("Travel
 * Researcher", "Local Coorg Expert", etc.) — the destination-aware
 * variants are passed through unchanged, and the parent component
 * does the card-to-role lookup (cards can match by prefix or exact
 * name; not theater-state's concern).
 *
 * `filterEventsByDensity(events, mode)` applies the major-vs-all
 * density filter per Q-impl-249-e=A sign-off:
 *   - "major": task_completed + callback_summary only (the 3 agent
 *     handoffs + closing tally; cleanest demo narrative)
 *   - "all": everything (engineering-depth toggle for "show me everything")
 *
 * Cards always show full state regardless of density toggle per R6
 * confirmation — density filters only the LiveEventLog below the cards.
 */

import { describe, expect, it } from "vitest";

import type { AgentSummaryRow } from "@/lib/backend";

describe("deriveAgentStates", () => {
  it("returns empty map when events array is empty (theater initial state)", async () => {
    const { deriveAgentStates } = await import("@/lib/theater-state");
    expect(deriveAgentStates([])).toEqual({});
  });

  it("a single task_completed event marks that agent done with duration", async () => {
    // task_completed is the canonical agent-completion marker (always
    // 3 per plan_trip post-Path-B). Render contract: state=done,
    // duration from elapsed_ms.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Travel Researcher"]).toEqual({
      state: "done",
      durationMs: 312000,
    });
  });

  it("a step event (AgentFinish) marks that agent working when no task_completed yet", async () => {
    // Step events fire during ReAct intermediate reasoning (when they
    // fire at all per kyh-reframe). Their presence without a
    // task_completed signals "still working."
    const events: AgentSummaryRow[] = [
      {
        event: "AgentFinish",
        timestamp: "2026-06-09T10:04:00+00:00",
        elapsed_ms: 240000,
        agent_role: "Local Coorg Expert",
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Local Coorg Expert"]).toEqual({
      state: "working",
      durationMs: 240000,
    });
  });

  it("task_completed takes precedence over earlier AgentFinish for the same agent (done wins)", async () => {
    // Order-of-events robustness: an agent that reasoned (AgentFinish)
    // then completed (task_completed) is DONE, not still-working. The
    // state machine is monotonic toward done.
    const events: AgentSummaryRow[] = [
      {
        event: "AgentFinish",
        timestamp: "2026-06-09T10:04:00+00:00",
        elapsed_ms: 240000,
        agent_role: "Travel Researcher",
      },
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        agent_role: "Travel Researcher",
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Travel Researcher"]).toEqual({
      state: "done",
      durationMs: 312000,
    });
  });

  it("events without agent_role are ignored (legacy + callback_summary + malformed)", async () => {
    // Backward-compat: legacy AgentFinish events lack agent_role and
    // can't be attributed (no task_index, no proximity rule — too
    // brittle); callback_summary is structurally heterogeneous (no
    // agent_role at all). Neither contributes to agent card state
    // derivation. task_completed without agent_role IS attributable
    // via task_index — tested separately below.
    const events: AgentSummaryRow[] = [
      // No agent_role.
      {
        event: "AgentFinish",
        timestamp: "2026-06-09T10:04:00+00:00",
        elapsed_ms: 240000,
      },
      // callback_summary footer.
      {
        event: "callback_summary",
        step_callback_count: 3,
        task_callback_count: 3,
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    expect(deriveAgentStates(events)).toEqual({});
  });
});

describe("deriveAgentStates — task_index fallback (pre-Path-B legacy data)", () => {
  // The Coorg trip (planned 2026-06-06, pre-Path-B) has task_completed
  // events without agent_role. The crew composition in
  // agents/src/trip_agents/crew.py:179 locks the task ordering:
  //   task_index=1 → Researcher
  //   task_index=2 → Local Expert
  //   task_index=3 → Logistics Planner
  // We use task_index as the fallback so legacy trips still render
  // accurate card states.

  it("task_completed task_index=1 without agent_role → Travel Researcher card done", async () => {
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-06T16:08:00+00:00",
        elapsed_ms: 312000,
        task_index: 1,
        // No agent_role — pre-Path-B legacy shape.
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Travel Researcher"]).toEqual({
      state: "done",
      durationMs: 312000,
    });
  });

  it("task_completed task_index=2 without agent_role → Local Expert card done", async () => {
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-06T16:10:00+00:00",
        elapsed_ms: 545000,
        task_index: 2,
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Local Expert"]).toEqual({
      state: "done",
      durationMs: 545000,
    });
  });

  it("task_completed task_index=3 without agent_role → Logistics Planner card done", async () => {
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-06T16:14:00+00:00",
        elapsed_ms: 240000,
        task_index: 3,
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Logistics Planner"]).toEqual({
      state: "done",
      durationMs: 240000,
    });
  });

  it("task_completed with out-of-range task_index AND no agent_role is ignored (defensive)", async () => {
    // task_index=4+ would be the audit loop or future task additions;
    // without an agent_role hint we can't safely attribute. Skip
    // rather than mis-attribute to the wrong card.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-06T16:20:00+00:00",
        elapsed_ms: 60000,
        task_index: 99,
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    expect(deriveAgentStates(events)).toEqual({});
  });

  it("Path B data takes precedence over task_index fallback (newer trips)", async () => {
    // When agent_role IS present (post-Path-B), use that verbatim.
    // For destination-aware variants like "Local Coorg Expert", the
    // parent component's prefix-match handles card lookup — the state
    // map key stays the raw role string.
    const events: AgentSummaryRow[] = [
      {
        event: "task_completed",
        timestamp: "2026-06-09T10:05:00+00:00",
        elapsed_ms: 312000,
        task_index: 2,
        agent_role: "Local Coorg Expert",
      },
    ];
    const { deriveAgentStates } = await import("@/lib/theater-state");
    const result = deriveAgentStates(events);
    expect(result["Local Coorg Expert"]).toEqual({
      state: "done",
      durationMs: 312000,
    });
    // The task_index=2 fallback ("Local Expert") MUST NOT also appear —
    // agent_role wins, single source of truth.
    expect(result["Local Expert"]).toBeUndefined();
  });
});

describe("filterEventsByDensity", () => {
  // Q-impl-249-e=A: major = task_completed + callback_summary.
  // The 3-event-handoff rhythm + closing tally is the clean demo
  // narrative; AgentFinish step events add noise without value.

  const _MIXED_EVENTS: AgentSummaryRow[] = [
    {
      event: "AgentFinish",
      timestamp: "2026-06-09T10:04:00+00:00",
      elapsed_ms: 240000,
      agent_role: "Travel Researcher",
    },
    {
      event: "task_completed",
      timestamp: "2026-06-09T10:05:00+00:00",
      elapsed_ms: 312000,
      task_index: 1,
      agent_role: "Travel Researcher",
    },
    {
      event: "AgentFinish",
      timestamp: "2026-06-09T10:06:00+00:00",
      elapsed_ms: 360000,
      agent_role: "Local Coorg Expert",
    },
    {
      event: "task_completed",
      timestamp: "2026-06-09T10:07:00+00:00",
      elapsed_ms: 420000,
      task_index: 2,
      agent_role: "Local Coorg Expert",
    },
    {
      event: "callback_summary",
      step_callback_count: 2,
      task_callback_count: 2,
    },
  ];

  it("'major' mode keeps task_completed + callback_summary, drops AgentFinish", async () => {
    const { filterEventsByDensity } = await import("@/lib/theater-state");
    const filtered = filterEventsByDensity(_MIXED_EVENTS, "major");
    expect(filtered).toHaveLength(3); // 2 task_completed + 1 callback_summary
    expect(
      filtered.every((e) => e.event === "task_completed" || e.event === "callback_summary"),
    ).toBe(true);
  });

  it("'all' mode returns every event unmodified (engineering-depth toggle)", async () => {
    // Identity preservation: tests + future debugging rely on the
    // "all" pass-through being bit-for-bit identical.
    const { filterEventsByDensity } = await import("@/lib/theater-state");
    const filtered = filterEventsByDensity(_MIXED_EVENTS, "all");
    expect(filtered).toEqual(_MIXED_EVENTS);
  });
});
