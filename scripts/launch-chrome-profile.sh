#!/usr/bin/env bash
set -euo pipefail

RESTART=false
PROFILE_NAME="NishantTheProgrammer"
for arg in "$@"; do
  if [[ "$arg" == "--restart" ]]; then
    RESTART=true
  else
    PROFILE_NAME="$arg"
  fi
done

CDP_PORT="${CHROME_CDP_PORT:-9222}"
LOCAL_STATE="$HOME/Library/Application Support/Google/Chrome/Local State"

if curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "Google Chrome remote debugging is already active on port ${CDP_PORT}."
  exit 0
fi

PROFILE_DIR=$(python3 - "$LOCAL_STATE" "$PROFILE_NAME" <<'PY'
import json, sys
local_state, target = sys.argv[1], sys.argv[2].strip().lower()
try:
    with open(local_state, "r", encoding="utf-8") as f:
        cache = json.load(f).get("profile", {}).get("info_cache", {})
    for folder, meta in cache.items():
        if not isinstance(meta, dict):
            continue
        names = [folder, meta.get("name", ""), meta.get("gaia_name", ""), meta.get("shortcut_name", "")]
        if any(str(n).strip().lower() == target for n in names if n):
            print(folder)
            sys.exit(0)
except Exception:
    pass
print("")
PY
)

if pgrep -x "Google Chrome" >/dev/null 2>&1; then
  if [[ "$RESTART" == "true" ]]; then
    echo "Quitting existing Google Chrome so remote debugging (port ${CDP_PORT}) can be enabled..."
    osascript -e 'tell application "Google Chrome" to quit' >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do
      if ! pgrep -x "Google Chrome" >/dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done
  else
    echo "Google Chrome is currently running without remote debugging (port ${CDP_PORT})."
    echo "Run with --restart to relaunch your '${PROFILE_NAME}' profile with CDP enabled:"
    echo "  ./scripts/launch-chrome-profile.sh --restart"
    exit 1
  fi
fi

ARGS=("--remote-debugging-port=${CDP_PORT}")
if [[ -n "$PROFILE_DIR" ]]; then
  echo "Launching Google Chrome profile '${PROFILE_NAME}' (${PROFILE_DIR}) with CDP on port ${CDP_PORT}..."
  ARGS+=("--profile-directory=${PROFILE_DIR}")
else
  echo "Launching Google Chrome with CDP on port ${CDP_PORT}..."
fi

open -a "Google Chrome" --args "${ARGS[@]}"
for _ in $(seq 1 15); do
  if curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
    echo "CDP is active on http://127.0.0.1:${CDP_PORT} — Auto-Apply will now use your '${PROFILE_NAME}' profile!"
    exit 0
  fi
  sleep 0.5
done
echo "Chrome launched; if CDP is not active yet, verify http://127.0.0.1:${CDP_PORT}/json/version"

