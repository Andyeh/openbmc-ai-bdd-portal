#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  OpenBMC AI-BDD Portal — Run BDD Tests
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
source .venv/bin/activate 2>/dev/null || { echo "[error] Run ./scripts/start.sh first to create the venv."; exit 1; }

ALLURE_RESULTS="tests/bdd/reports/allure-results"
FEATURE_DIR="tests/bdd/features"

mkdir -p "$ALLURE_RESULTS"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 🧪  Running BDD Tests"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

PYTHONPATH="$PROJECT_DIR" behave \
  "$FEATURE_DIR" \
  --format allure_behave.formatter:AllureFormatter \
  --outfile "$ALLURE_RESULTS" \
  --format pretty \
  "$@"

echo ""
echo "[done] Results saved to: $ALLURE_RESULTS"
echo "[hint] Run: allure serve $ALLURE_RESULTS"
