#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  OpenBMC AI-BDD Portal — Start Script
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " ⚡  OpenBMC AI-BDD Portal"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$PROJECT_DIR"

# ── 1. Virtual environment ─────────────────────────────────────────
if [[ ! -d ".venv" ]]; then
  echo "[setup] Creating Python virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate
echo "[setup] Virtual environment: .venv"

# ── 2. Install dependencies ────────────────────────────────────────
echo "[setup] Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ── 3. Copy .env if missing ────────────────────────────────────────
if [[ ! -f ".env" ]]; then
  cp .env.example .env
  echo "[setup] Created .env from .env.example — please review settings."
fi

# ── 4. Create output directories ──────────────────────────────────
mkdir -p tests/bdd/reports/allure-results

# ── 5. Start FastAPI server ────────────────────────────────────────
HOST="${APP_HOST:-0.0.0.0}"
PORT="${APP_PORT:-8080}"

# Kill any stale process still holding the port
STALE_PIDS=$(
  { lsof -ti :"$PORT" 2>/dev/null; } ||
  { fuser "$PORT"/tcp 2>/dev/null; } ||
  true
)
if [[ -n "$STALE_PIDS" ]]; then
  echo "[server] Killing stale process(es) on port ${PORT}: ${STALE_PIDS}"
  kill -9 $STALE_PIDS 2>/dev/null || true
  sleep 0.5
else
  # Fallback: kill by process name
  pkill -9 -f "uvicorn backend.main:app" 2>/dev/null || true
  [[ $? -eq 0 ]] && sleep 0.5
fi

echo ""
echo "[server] Starting FastAPI on http://${HOST}:${PORT}"
echo "[server] API docs: http://${HOST}:${PORT}/api/docs"
echo "[server] Press Ctrl+C to stop"
echo ""

PYTHONPATH="$PROJECT_DIR" uvicorn backend.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --reload \
  --log-level info
