#!/usr/bin/env bash
# Idempotent: installs pre-commit framework, reinstalls bd's hooks, then
# appends our lint shim to .git/hooks/pre-commit. Safe to re-run.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# 1. pre-commit framework — uv tool isolates it from system Python.
if ! command -v pre-commit >/dev/null 2>&1; then
  echo "→ Installing pre-commit framework (uv tool install)..."
  uv tool install pre-commit
else
  echo "✓ pre-commit framework already on PATH."
fi

# 2. bd's git hooks (idempotent — bd handles re-install cleanly).
if command -v bd >/dev/null 2>&1; then
  echo "→ Ensuring bd hooks are installed..."
  bd hooks install >/dev/null
  echo "✓ bd hooks installed."
fi

# 3. Append our lint shim after bd's END marker, only if not already present.
HOOK=".git/hooks/pre-commit"
MARKER_BEGIN="# --- BEGIN TRIP CONCIERGE LINT ---"
MARKER_END="# --- END TRIP CONCIERGE LINT ---"

if [ ! -f "$HOOK" ]; then
  echo "→ Creating $HOOK..."
  printf '#!/usr/bin/env sh\n' > "$HOOK"
  chmod +x "$HOOK"
fi

if grep -qF "$MARKER_BEGIN" "$HOOK"; then
  echo "✓ Lint shim already in $HOOK."
else
  echo "→ Appending lint shim to $HOOK..."
  cat >> "$HOOK" <<EOF

$MARKER_BEGIN
# Runs ruff (backend, mcp_server) and biome (web) against staged files.
# Config: .pre-commit-config.yaml. Managed by scripts/install-hooks.sh.
exec pre-commit run --hook-stage pre-commit
$MARKER_END
EOF
  echo "✓ Lint shim appended."
fi

echo
echo "Hooks ready. Try: echo 'unused' > /tmp/test.py && git add /tmp/test.py"
echo "(then 'git commit' would be rejected by ruff)"
