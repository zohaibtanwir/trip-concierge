/**
 * <AgentCard /> tests — slice 4.7-theater commit 2.
 *
 * Per-agent visualization card in the 4-up theater grid. Renders:
 *   - Agent role name (title)
 *   - State pill (idle / queued / working / done / waiting)
 *   - Last action (optional, shown when working or done)
 *   - Cumulative duration (optional)
 *   - Material icon per state (visual disambiguation)
 *
 * "waiting" state per Q-249-d sign-off: Budget Auditor's default
 * pre-audit-loop state. Distinct copy ("Waiting on plan") so the user
 * understands it's not idle, it's queued behind the main crew.
 *
 * Cards always show full state regardless of density toggle (R6
 * confirmation) — density filters only the LiveEventLog below.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

describe("<AgentCard />", () => {
  it("renders idle state — agent role + idle indicator, no action/duration shown", async () => {
    // Initial theater state before any callbacks fire. Card shows the
    // agent's name + "Idle" pill so the user understands the agent
    // exists and is expected to act, not absent entirely.
    const { AgentCard } = await import("@/components/agent-card");
    render(<AgentCard agentRole="Travel Researcher" state="idle" />);
    expect(screen.getByText(/Travel Researcher/)).toBeDefined();
    expect(screen.getByText(/idle/i)).toBeDefined();
  });

  it("renders queued state — distinct from idle (worker has the job; crew hasn't started)", async () => {
    // Between trip creation and the first callback firing. Distinct
    // from "idle" because the user has committed (job_id exists) but
    // distinct from "working" because no crew event has fired yet.
    const { AgentCard } = await import("@/components/agent-card");
    render(<AgentCard agentRole="Travel Researcher" state="queued" />);
    expect(screen.getByText(/queued/i)).toBeDefined();
  });

  it("renders working state — shows last action when provided", async () => {
    // Active agent surface. The lastAction string contextualizes
    // what the agent is doing right now (e.g., "Searching venues" or
    // "Validating costs"). Falls back to bare working pill if absent.
    const { AgentCard } = await import("@/components/agent-card");
    render(
      <AgentCard
        agentRole="Travel Researcher"
        state="working"
        lastAction="Searching venues in Pondicherry"
        durationMs={45000}
      />,
    );
    expect(screen.getByText(/working/i)).toBeDefined();
    expect(screen.getByText(/Searching venues in Pondicherry/)).toBeDefined();
    // Duration rendered (formatted as seconds — 45000ms → 45s)
    expect(screen.getByText(/45/)).toBeDefined();
  });

  it("renders done state — completion indicator + duration", async () => {
    // Terminal-per-agent state. Once an agent emits task_completed,
    // it stays in done. Theater settles into this state for all 4
    // cards by the end of a plan_trip.
    const { AgentCard } = await import("@/components/agent-card");
    render(<AgentCard agentRole="Travel Researcher" state="done" durationMs={312000} />);
    expect(screen.getByText(/done/i)).toBeDefined();
    // Duration formatting: 312000ms = 5.2 min — should render either
    // as "5.2 min" or "312s" or "5:12". Loose match on the digits.
    expect(screen.getByText(/312|5\.2|5:12/)).toBeDefined();
  });

  it("renders waiting state with custom copy for Budget Auditor", async () => {
    // Q-249-d=A: Budget Auditor's default pre-audit-loop state.
    // Distinct copy "Waiting on plan" tells the user this card isn't
    // dormant — it's queued behind the main crew's output. The
    // copy is load-bearing for demo narrative; bare "Waiting" alone
    // would read as ambiguous.
    const { AgentCard } = await import("@/components/agent-card");
    render(<AgentCard agentRole="Budget Auditor" state="waiting" />);
    expect(screen.getByText(/Budget Auditor/)).toBeDefined();
    expect(screen.getByText(/waiting on plan/i)).toBeDefined();
  });
});
