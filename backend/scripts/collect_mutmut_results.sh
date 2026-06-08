#!/usr/bin/env bash
# Collect mutmut run results into experiments/03-mutmut-results.md
# Run after the overnight mutmut grind completes.
# trip-concierge-ht5
set -euo pipefail

cd "$(dirname "$0")/.."

OUTPUT="../experiments/03-mutmut-results.md"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

echo "Collecting mutmut results → $OUTPUT"

# `mutmut results` prints the survival breakdown in a stable text form.
RAW=$(uv run mutmut results 2>&1 || true)

mkdir -p ../experiments
cat > "$OUTPUT" <<EOF
# Mutmut mutation testing — baseline run

**Captured:** $TS
**Ticket:** trip-concierge-ht5
**Target:** \`backend/app/\` (59 files mutated)
**Test suite:** \`backend/tests/\` (223 tests)
**Mutmut version:** $(uv run mutmut --version 2>/dev/null || echo "unknown")

## Headline numbers

\`\`\`
$RAW
\`\`\`

## Source files mutated

\`\`\`
$(find app -name "*.py" ! -path "*/migrations/*" ! -path "*/__pycache__/*" | sort)
\`\`\`

## Deck framing (for Marsh)

The mutation-survival rate is one concrete number anchoring the "harness and eval stack didn't commodify" thesis. A survived mutant is a code change that the test suite did NOT catch — i.e., real coverage gap, not just line-coverage theater.

Interpretation guide:
- **>85% killed**: strong demo number; cite it
- **70-85% killed**: usable with caveat ("baseline; will sharpen with X")
- **<70% killed**: don't deck-cite yet; file follow-up to harden tests in top survived files

## Survived-mutants top-5 (manual sweep TBD)

After the run completes, sweep \`uv run mutmut browse\` or read \`mutants/\` directory to identify the highest-value survived mutants — these are real test-gap signals worth filing as follow-up tickets.

## Reproduce

\`\`\`bash
cd backend
uv run mutmut run        # full grind (hours)
uv run mutmut results    # survival summary
uv run mutmut browse     # interactive review of survived mutants
\`\`\`

EOF

echo "✓ Saved to $OUTPUT"
echo ""
echo "Summary (last 20 lines):"
tail -20 "$OUTPUT"
