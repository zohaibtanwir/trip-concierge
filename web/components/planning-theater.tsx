/**
 * PlanningTheater — live + replay agent flow visualization.
 *
 * Slice 4.7-theater (trip-concierge-249) commit 3. Two modes:
 *
 *   - "live": uses usePlanStatusPoll(tripId, userId) for 2500ms
 *     polling. Renders during {queued, running, cancelling} on the
 *     trip detail page. Replaces the pre-249 static "Your trip is
 *     being planned" surface
 *   - "replay": consumes `events` prop directly (no polling). Used
 *     by the commit 4 "View agent trace" modal for historical view
 *     of agent_summary
 *
 * Q-249-i shared-data-shape: same component, two data sources. The
 * hook is always called (React Hooks rules), and `disabled: true`
 * short-circuits it in replay mode.
 *
 * Layout (Q-249-c):
 *   [4-up agent card grid]
 *   [density toggle]   [live event log]
 *
 * Card-to-role lookup is prefix-based — handles destination-aware
 * variants ("Local Coorg Expert" / "Local Pondicherry Expert" both
 * map to the same Expert card without per-destination configuration).
 */

"use client";

import { useState } from "react";

import { AgentCard } from "@/components/agent-card";
import { EventDensityToggle } from "@/components/event-density-toggle";
import { LiveEventLog } from "@/components/live-event-log";
import type { AgentSummaryRow } from "@/lib/backend";
import {
  type AgentCardData,
  type AgentCardState,
  deriveAgentStates,
  filterEventsByDensity,
} from "@/lib/theater-state";
import { usePlanStatusPoll } from "@/lib/use-plan-status-poll";

interface PlanningTheaterProps {
  mode: "live" | "replay";
  tripId: string;
  userId: string;
  // Required in replay mode; ignored in live mode (hook supplies events).
  events?: AgentSummaryRow[];
}

interface AgentCardSpec {
  display: string;
  matches: (role: string) => boolean;
  // Default state when no event matches this card. Auditor uses
  // "waiting" instead of "idle" per Q-249-d=A.
  defaultState: AgentCardState;
}

const _AGENT_CARDS: ReadonlyArray<AgentCardSpec> = [
  {
    display: "Travel Researcher",
    matches: (role) => role.includes("Researcher"),
    defaultState: "idle",
  },
  {
    display: "Local Expert",
    matches: (role) => role.includes("Expert"),
    defaultState: "idle",
  },
  {
    display: "Logistics Planner",
    matches: (role) => role.includes("Logistics"),
    defaultState: "idle",
  },
  {
    display: "Budget Auditor",
    matches: (role) => role.includes("Auditor") || role.includes("Audit"),
    defaultState: "waiting",
  },
];

function _cardDataFor(
  card: AgentCardSpec,
  agentStates: Record<string, AgentCardData>,
): AgentCardData {
  // Find the first role string in the derived state map that matches
  // this card's prefix predicate. Returns the default state when no
  // event has been observed for this agent yet.
  const matchedRole = Object.keys(agentStates).find(card.matches);
  if (matchedRole !== undefined) return agentStates[matchedRole];
  return { state: card.defaultState };
}

export function PlanningTheater({ mode, tripId, userId, events }: PlanningTheaterProps) {
  // The hook is always called (React Hooks rules). In replay mode,
  // `disabled: true` short-circuits its effect — no polling.
  const live = usePlanStatusPoll(tripId, userId, { disabled: mode !== "live" });
  const sourceEvents: AgentSummaryRow[] = mode === "live" ? live.events : (events ?? []);

  // Cards always show full state regardless of density toggle (R6).
  const agentStates = deriveAgentStates(sourceEvents);

  // Density toggle only filters the LiveEventLog below.
  const [density, setDensity] = useState<"major" | "all">("major");
  const filteredForLog = filterEventsByDensity(sourceEvents, density);

  return (
    <section className="flex flex-col gap-6 rounded-xl border border-outline-variant bg-surface-container-lowest p-6">
      <header>
        <h2 className="text-headline-sm text-on-surface">Your crew is at work</h2>
        <p className="mt-1 text-body-md text-on-surface-variant">
          4 specialist agents collaborate on your trip. Watch them work in real time.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {_AGENT_CARDS.map((card) => {
          const data = _cardDataFor(card, agentStates);
          return (
            <AgentCard
              key={card.display}
              agentRole={card.display}
              state={data.state}
              lastAction={data.lastAction}
              durationMs={data.durationMs}
            />
          );
        })}
      </div>

      <div className="flex items-center justify-between gap-4">
        <h3 className="text-label-md text-on-surface">Recent activity</h3>
        <EventDensityToggle onChange={setDensity} />
      </div>
      <LiveEventLog events={filteredForLog} />
    </section>
  );
}
