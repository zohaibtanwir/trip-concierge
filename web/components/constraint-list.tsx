/**
 * ConstraintList — read-only chip rendering of trip.constraints.rules[]
 * (slice 4.5 / z9o).
 *
 * v1.0a chips are READ-ONLY BY DESIGN. Removal requires a DELETE
 * constraint endpoint that doesn't exist yet — deferred to a P3 ticket
 * tracked in BUILD_PLAN. Future readers: don't add an X button without
 * landing the backend route first.
 *
 * Per-kind Material Symbols icons per spec §9.13 mapping (added in
 * v1.0.2 alongside this slice). When new kinds land in the v1.0a-
 * companion slice (pace + budget cap + walking distance), update both
 * the mapping below AND spec §9.13's table.
 */

interface Rule {
  kind: string;
  value: string;
  raw_text: string;
}

const _ICON_BY_KIND: Record<string, string> = {
  dietary: "restaurant",
  mobility: "directions_walk",
  no_go: "block",
  accessibility: "accessible",
  walking_limit: "directions_walk",
  budget: "payments",
  custom: "label",
};

function _iconFor(kind: string): string {
  return _ICON_BY_KIND[kind] ?? "label";
}

export function ConstraintList({ rules }: { rules: Rule[] }) {
  if (rules.length === 0) {
    return <p className="text-body-md italic text-on-surface-variant">No constraints added yet.</p>;
  }
  return (
    <ul className="flex flex-wrap gap-2">
      {rules.map((rule, idx) => (
        <li
          // biome-ignore lint/suspicious/noArrayIndexKey: rules is backend-owned append-only JSONB array — order is stable for a given trip snapshot
          key={`${rule.kind}-${idx}`}
          className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-high text-xs"
        >
          <span className="material-symbols-outlined text-base text-primary" aria-hidden>
            {_iconFor(rule.kind)}
          </span>
          <span className="text-on-surface">{rule.value}</span>
        </li>
      ))}
    </ul>
  );
}
