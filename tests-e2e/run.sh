#!/usr/bin/env bash
# Capture one labelled run of the theme x route matrix.
#
#   ./run.sh baseline     # before a refactor
#   ./run.sh current      # after it
#   ./run.sh compare      # diff the two, exit 1 if anything moved
#
# Two phases, because they need opposite database state: the setup wizard is
# only reachable while SystemSettings.is_configured is false, and every other
# page is only reachable while it is true.
#
# The database is rebuilt for each phase. That is not tidiness — pages render
# live counters (active sessions, activity-log rows) that the harness itself
# increments by logging in and browsing, so without a fresh database each run
# those counts drift and every page reports a phantom diff.
set -euo pipefail

cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"

PORT="${VISUAL_PORT:-8009}"
PY="../.venv/bin/python"
LABEL="${1:-}"

if [[ "$LABEL" == "compare" ]]; then
  exec node compare.mjs "${@:2}"
fi

if [[ "$LABEL" != "baseline" && "$LABEL" != "current" ]]; then
  echo "usage: ./run.sh <baseline|current|compare>" >&2
  exit 2
fi

server_pid=""
stop_server() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
    server_pid=""
  fi
}
trap stop_server EXIT

start_server() {
  # A server from a previous phase still holds the old sqlite file open.
  if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
    lsof -ti tcp:"$PORT" | xargs kill 2>/dev/null || true
    sleep 1
  fi
  PYTHONPATH="..:." DJANGO_SETTINGS_MODULE=settings \
    "$PY" -m django runserver "$PORT" --noreload > state/server.log 2>&1 &
  server_pid=$!
  for _ in $(seq 1 20); do
    curl -sf -o /dev/null "http://127.0.0.1:$PORT/accounts/login/" && return 0
    sleep 0.5
  done
  echo "server never came up; see state/server.log" >&2
  tail -20 state/server.log >&2
  exit 1
}

echo "==> phase 1/2: main (configured)"
"$PY" seed.py
start_server
VISUAL_BASE_URL="http://127.0.0.1:$PORT" node shoot.mjs "$LABEL" --phase main
stop_server

echo "==> phase 2/2: setup (unconfigured)"
"$PY" seed.py --unconfigured
start_server
VISUAL_BASE_URL="http://127.0.0.1:$PORT" node shoot.mjs "$LABEL" --phase setup --append
stop_server

echo "==> $LABEL complete"
