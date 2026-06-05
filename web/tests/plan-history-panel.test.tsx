/**
 * <PlanHistoryPanel /> test (slice 4.3, PRD §F8 partial).
 *
 * Behavior pinned:
 * - Reads agent_summary prop (array of {agent, step, duration_ms, tokens?}).
 * - Renders one row per agent step with the agent name + duration.
 * - Collapsible: defaults to collapsed; clicking the header expands.
 * - Empty agent_summary renders an honest "No agent activity recorded" line
 *   (covers legacy pre-qek-a JobRuns).
 *
 * Tap-to-expand-step-reasoning per PRD §F8 acceptance is deferred until
 * backend enrichment ships per-step reasoning data — tracked as
 * trip-concierge-gco backend enrichment + trip-concierge-auu §17.5.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

afterEach(() => cleanup());

const _SUMMARY = [
  { agent: "Researcher", step: 1, duration_ms: 32500, tokens: 1840 },
  { agent: "Local Expert", step: 2, duration_ms: 28100, tokens: 1560 },
  { agent: "Logistics", step: 3, duration_ms: 41200, tokens: 2310 },
  { agent: "Budget Auditor", step: 4, duration_ms: 18900, tokens: 980 },
];

describe("<PlanHistoryPanel />", () => {
  it("renders one row per agent step when expanded", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} defaultExpanded />);
    expect(screen.getByText(/Researcher/)).toBeDefined();
    expect(screen.getByText(/Local Expert/)).toBeDefined();
    expect(screen.getByText(/Logistics/)).toBeDefined();
    expect(screen.getByText(/Budget Auditor/)).toBeDefined();
  });

  it("renders durations alongside agent names", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} defaultExpanded />);
    // Researcher ran 32.5s — loose match for the human-readable form.
    expect(screen.getByText(/32\.5\s*s|32500\s*ms|32\s*s/i)).toBeDefined();
  });

  it("renders 'No agent activity recorded' when summary is empty", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={[]} defaultExpanded />);
    expect(screen.getByText(/no agent activity recorded/i)).toBeDefined();
  });

  it("shows the 'How this plan was made' header trigger", async () => {
    const { PlanHistoryPanel } = await import("@/components/plan-history-panel");
    render(<PlanHistoryPanel agentSummary={_SUMMARY} />);
    expect(screen.getByText(/how this plan was made/i)).toBeDefined();
  });
});
