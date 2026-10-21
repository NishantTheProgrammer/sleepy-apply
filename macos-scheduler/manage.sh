#!/usr/bin/env bash
# Sleepy Apply - macOS Native Scheduler
# Uses launchd + caffeinate + pmset (zero third-party dependencies)
# Based on the winter-arc macos-scheduler pattern.
#
# Usage:
#   ./macos-scheduler/manage.sh setup
#   ./macos-scheduler/manage.sh start | stop | status | run-now | logs | uninstall

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.sh"
LOG_FILE="$SCRIPT_DIR/logs/scheduler.log"
LOCK_FILE="$SCRIPT_DIR/logs/scheduler.lock"
RUN_SCRIPT="$SCRIPT_DIR/run_tasks.sh"

AGENT_LABEL="com.sleepyapply.scheduler"
AGENT_PLIST="$HOME/Library/LaunchAgents/${AGENT_LABEL}.plist"

GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; BOLD="\033[1m"; NC="\033[0m"

require_config() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: config.sh not found. Copy config.sh.example and fill in your values.${NC}" >&2
    exit 1
  fi
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  if [ -z "${BACKEND_URL:-}" ] || [ -z "${USER_TOKEN:-}" ]; then
    echo -e "${RED}Error: BACKEND_URL and USER_TOKEN must be set in config.sh${NC}" >&2
    exit 1
  fi
}

cmd_setup() {
  require_config
  mkdir -p "$SCRIPT_DIR/logs"
  chmod +x "$RUN_SCRIPT"

  local interval_minutes=$(( ${RUN_INTERVAL_HOURS:-6} * 60 ))

  # Write LaunchAgent plist
  cat > "$AGENT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>           <string>${AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${RUN_SCRIPT}</string>
    </array>
    <key>StartInterval</key>   <integer>${interval_minutes}</integer>
    <key>RunAtLoad</key>       <false/>
    <key>StandardOutPath</key> <string>${SCRIPT_DIR}/logs/launchd.stdout.log</string>
    <key>StandardErrorPath</key><string>${SCRIPT_DIR}/logs/launchd.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>BACKEND_URL</key>  <string>${BACKEND_URL}</string>
        <key>USER_TOKEN</key>   <string>${USER_TOKEN}</string>
        <key>PROJECT_DIR</key>  <string>${PROJECT_DIR}</string>
        <key>LOG_FILE</key>     <string>${LOG_FILE}</string>
        <key>LOCK_FILE</key>    <string>${LOCK_FILE}</string>
        <key>MAX_RUN_SECONDS</key><string>${MAX_RUN_SECONDS:-600}</string>
    </dict>
</dict>
</plist>
EOF

  launchctl bootout "gui/$(id -u)/${AGENT_LABEL}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST"
  echo -e "${GREEN}${BOLD}✓ Scheduler installed. Runs every ${RUN_INTERVAL_HOURS:-6}h.${NC}"
  echo -e "${YELLOW}Run './macos-scheduler/manage.sh run-now' to test immediately.${NC}"
}

cmd_start() {
  launchctl bootstrap "gui/$(id -u)" "$AGENT_PLIST" 2>/dev/null || \
  launchctl kickstart "gui/$(id -u)/${AGENT_LABEL}" 2>/dev/null || true
  echo -e "${GREEN}✓ Scheduler started.${NC}"
}

cmd_stop() {
  launchctl bootout "gui/$(id -u)/${AGENT_LABEL}" 2>/dev/null || true
  echo -e "${YELLOW}Scheduler stopped.${NC}"
}

cmd_status() {
  echo -e "${BOLD}── Sleepy Apply Scheduler Status ──${NC}"
  if launchctl list "${AGENT_LABEL}" &>/dev/null; then
    echo -e "${GREEN}✓ LaunchAgent: loaded${NC}"
    launchctl list "${AGENT_LABEL}" | grep -E "PID|LastExitStatus" || true
  else
    echo -e "${RED}✗ LaunchAgent: not loaded${NC}"
  fi
  echo ""
  if [ -f "$LOCK_FILE" ]; then
    local pid; pid=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo -e "${YELLOW}⚙ Pipeline running (PID: $pid)${NC}"
    else
      echo "Lock file present but process not running (stale)."
    fi
  fi
  echo ""
  echo -e "${BOLD}Last 10 log lines:${NC}"
  tail -10 "$LOG_FILE" 2>/dev/null || echo "(no logs yet)"
}

cmd_run_now() {
  echo -e "${BOLD}Running pipeline now (foreground)…${NC}"
  bash "$RUN_SCRIPT"
}

cmd_logs() {
  tail -f "$LOG_FILE" 2>/dev/null || echo "No log file yet."
}

cmd_uninstall() {
  launchctl bootout "gui/$(id -u)/${AGENT_LABEL}" 2>/dev/null || true
  rm -f "$AGENT_PLIST" "$LOCK_FILE"
  echo -e "${GREEN}✓ Scheduler uninstalled.${NC}"
}

case "${1:-status}" in
  setup)    cmd_setup ;;
  start)    cmd_start ;;
  stop)     cmd_stop ;;
  restart)  cmd_stop; sleep 1; cmd_start ;;
  status)   cmd_status ;;
  run-now)  cmd_run_now ;;
  logs)     cmd_logs ;;
  uninstall) cmd_uninstall ;;
  help|-h|--help)
    echo "Sleepy Apply macOS Scheduler"
    echo "Usage: $0 {setup|start|stop|restart|status|run-now|logs|uninstall}" ;;
  *)
    echo "Usage: $0 {setup|start|stop|restart|status|run-now|logs|uninstall}" >&2; exit 1 ;;
esac
