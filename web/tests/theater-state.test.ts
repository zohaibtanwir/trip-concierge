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
    // Backward-compat: legacy events lack agent_role; callback_summary
    // is structurally heterogeneous (no agent_role at all). Neither
    // contributes to agent card state derivation.
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
