#!/bin/bash
# One-time Mac setup: Python 3.12+ venv, dependencies, and a launchd agent that keeps the
# dashboard (and its Garmin scheduler) running from login.   Undo with: scripts/setup_mac.sh --uninstall
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.bodykaizen.dashboard"

PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

# Earlier installs of this dashboard under another service name: any agent that runs this folder's server.py
remove_old() {
  for P in "$HOME"/Library/LaunchAgents/*.plist; do
    [[ -f "$P" && "$P" != "$PLIST" ]] || continue
    if grep -q "<string>$REPO/app/server.py</string>" "$P"; then
      L="$(basename "$P" .plist)"; launchctl bootout "$DOMAIN/$L" 2>/dev/null || true; rm -f "$P"; echo "Removed an earlier install ($L)."
    fi
  done
}

if [[ "${1:-}" == "--uninstall" ]]; then
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true; remove_old
  rm -f "$PLIST"; echo "Removed the background service. The repo and .venv are untouched."; exit 0
fi

# 1. Python 3.12+ (garminconnect needs it)
PY=""
for c in python3.13 python3.12 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null; then PY="$(command -v "$c")"; break; fi
done
if [[ -z "$PY" ]]; then
  echo "Need Python 3.12 or newer (garminconnect requires it). Install it with:  brew install python@3.12"
  echo "then run this script again."; exit 1
fi
echo "Using $PY ($("$PY" --version))"

# 2. Isolated environment + dependencies
[[ -x "$REPO/.venv/bin/python" ]] || "$PY" -m venv "$REPO/.venv"
"$REPO/.venv/bin/python" -m pip install -q --upgrade pip
"$REPO/.venv/bin/python" -m pip install -q -r "$REPO/requirements.txt"
echo "Dependencies installed in .venv"

# 3. Nothing else may hold the port (an older install of this service is removed first)
remove_old
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1 && ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
  echo "Something is already serving on port 8765 — stop the dashboard you started by hand (Ctrl+C), then rerun."; exit 1
fi

# 4. launchd agent: starts at login, restarts if it stops
mkdir -p "$REPO/logs" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$REPO/.venv/bin/python</string><string>$REPO/app/server.py</string></array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>${FT_DATA:+<key>FT_DATA</key><string>$FT_DATA</string>}</dict>
  <key>StandardOutPath</key><string>$REPO/logs/server.log</string>
  <key>StandardErrorPath</key><string>$REPO/logs/server.log</string>
</dict></plist>
PL
launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST"
echo "Dashboard service running: http://127.0.0.1:8765  (logs: $REPO/logs/server.log)"

if [[ ! -f "$HOME/.garminconnect/garmin_tokens.json" ]]; then
  echo
  echo "Last step — log in to Garmin once (password not stored, MFA code if asked):"
  echo "  $REPO/.venv/bin/python $REPO/scripts/garmin_login.py"
fi
