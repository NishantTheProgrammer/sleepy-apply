#!/usr/bin/env bash
# Sleepy Apply - Pipeline Trigger Script
# Called by launchd every N hours. Triggers the user's pipeline via the shared backend API.
# Uses caffeinate to keep Mac awake during execution.

set -euo pipefail

LOG_FILE="${LOG_FILE:-$(dirname "$0")/logs/scheduler.log}"
LOCK_FILE="${LOCK_FILE:-$(dirname "$0")/logs/scheduler.lock}"
BACKEND_URL="${BACKEND_URL:-}"
USER_TOKEN="${USER_TOKEN:-}"
MAX_RUN_SECONDS="${MAX_RUN_SECONDS:-600}"

mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

# ── Lock (prevent overlap) ────────────────────────────────
if ( set -o noclobber; echo "$$" > "$LOCK_FILE" ) 2>/dev/null; then
  trap 'rm -f "$LOCK_FILE"' EXIT INT TERM
else
  existing_pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
  if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
    log "SKIP: Pipeline already running (PID: $existing_pid)"
    exit 0
  else
    log "Stale lock detected — reclaiming."
    echo "$$" > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT INT TERM
  fi
fi

# ── Validate config ───────────────────────────────────────
if [ -z "$BACKEND_URL" ] || [ -z "$USER_TOKEN" ]; then
  log "ERROR: BACKEND_URL and USER_TOKEN must be configured."
  exit 1
fi

START_TIME=$(date +%s)
log "════════════════════════════════════════════════════════"
log "Sleepy Apply Pipeline Trigger (PID: $$)"
log "Backend: $BACKEND_URL"
log "════════════════════════════════════════════════════════"

# ── Wait for network ──────────────────────────────────────
NETWORK_OK=false
for i in {1..5}; do
  if nc -zw 2 1.1.1.1 53 &>/dev/null || nc -zw 2 8.8.8.8 53 &>/dev/null; then
    NETWORK_OK=true; break
  fi
  log "Waiting for network (attempt $i/5)…"; sleep 3
done
if [ "$NETWORK_OK" != "true" ]; then
  log "WARNING: Network unavailable. Proceeding anyway…"
fi

# ── Trigger pipeline via API ──────────────────────────────
log "─── Triggering user job pipeline ───"
HTTP_STATUS=$(
  caffeinate -ims \
  curl -s -o /tmp/sa_pipeline_response.json -w "%{http_code}" \
    -X POST "${BACKEND_URL}/api/internal/trigger-pipeline" \
    -H "Authorization: Bearer ${USER_TOKEN}" \
    -H "Content-Type: application/json" \
    --max-time "$MAX_RUN_SECONDS" || echo "000"
)
RESPONSE=$(cat /tmp/sa_pipeline_response.json 2>/dev/null || echo "{}")

if [ "$HTTP_STATUS" = "200" ] || [ "$HTTP_STATUS" = "202" ]; then
  log "✓ Pipeline triggered successfully (HTTP $HTTP_STATUS)"
  log "Response: $RESPONSE"
else
  log "✗ Pipeline trigger failed (HTTP $HTTP_STATUS): $RESPONSE"
fi

DURATION=$(( $(date +%s) - START_TIME ))
log "Completed in ${DURATION}s. Mac may return to sleep."
log "════════════════════════════════════════════════════════"
exit 0
