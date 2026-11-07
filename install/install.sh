#!/bin/sh
# Body Kaizen installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/craigbennett1981/body-kaizen/main/install/install.sh | sh
#
# It installs uv (a small tool that fetches its own Python, so you don't need one), installs Body Kaizen with
# the Garmin and LibreLinkUp syncs, starts the dashboard at login, adds a "Body Kaizen" launcher, and opens the
# dashboard in your browser, signed in. Your data folder is chosen on that first page.
#
# Again later to update. To remove (your data folder and ~/.body-kaizen are left alone):
#   curl -fsSL https://raw.githubusercontent.com/craigbennett1981/body-kaizen/main/install/install.sh | sh -s -- --uninstall
#
# Settings, for testing:  BK_SOURCE=<pip spec or path> (what to install), BK_PORT (default 8765),
#                         BK_NO_SERVICE=1 (don't start at login), BK_NO_OPEN=1 (don't open the browser)
set -eu

REPO="https://github.com/craigbennett1981/body-kaizen"
PORT="${BK_PORT:-8765}"
LABEL="app.bodykaizen.dashboard"
OS="$(uname -s)"
say() { printf '\033[1m%s\033[0m\n' "$*"; }
die() { printf 'Body Kaizen install: %s\n' "$*" >&2; exit 1; }

case "$OS" in Darwin|Linux) ;; *) die "this installer is for macOS and Linux. On Windows use install.ps1 (see the README)." ;; esac

UV_BIN="$HOME/.local/bin"
export PATH="$UV_BIN:$HOME/.cargo/bin:$PATH"

# ---------- remove ----------
if [ "${1:-}" = "--uninstall" ]; then
  if [ "$OS" = Darwin ]; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
    rm -rf "$HOME/Applications/Body Kaizen.app"
  else
    systemctl --user disable --now body-kaizen.service 2>/dev/null || true
    rm -f "$HOME/.config/systemd/user/body-kaizen.service" "$HOME/.local/share/applications/body-kaizen.desktop"
    rm -f "$HOME/.local/share/icons/hicolor/256x256/apps/body-kaizen.png"
  fi
  command -v uv >/dev/null 2>&1 && uv tool uninstall body-kaizen 2>/dev/null || true
  say "Body Kaizen removed. Your data folder and ~/.body-kaizen (settings, sign-in key) are still there."
  exit 0
fi

# ---------- 1. uv ----------
if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (it brings its own Python)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null || die "couldn't install uv: see https://docs.astral.sh/uv/"
fi
command -v uv >/dev/null 2>&1 || die "uv was installed but isn't on PATH: open a new terminal and run this again."

# ---------- 2. Body Kaizen ----------
# From PyPI when it's there, else the latest code on GitHub. Python 3.12: the Garmin sync needs it.
say "Installing Body Kaizen..."
if [ -n "${BK_SOURCE:-}" ]; then
  [ -d "$BK_SOURCE" ] && BK_SOURCE="file://$(cd "$BK_SOURCE" && pwd)"   # a folder (a clone): install that code
  uv tool install --force --python 3.12 "body-kaizen[all] @ $BK_SOURCE" || die "couldn't install from $BK_SOURCE"
elif ! uv tool install --force --python 3.12 "body-kaizen[all]" 2>/dev/null; then
  uv tool install --force --python 3.12 "body-kaizen[all] @ $REPO/archive/refs/heads/main.zip" || die "couldn't install Body Kaizen"
fi
BK="$(uv tool dir --bin 2>/dev/null)/body-kaizen"
[ -x "$BK" ] || BK="$(command -v body-kaizen)" || die "installed, but the body-kaizen command wasn't found"
"$BK" --version

# ---------- 3. start at login ----------
port_busy() { curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/"; }   # any answer, a sign-in page included
if [ -z "${BK_NO_SERVICE:-}" ]; then
  if [ "$OS" = Darwin ]; then
    PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && sleep 2 || true   # an earlier install of this: stop it first
    if port_busy; then die "something else is already using port $PORT (a dashboard you started by hand, or scripts/setup_mac.sh). Stop it, or run with BK_PORT=8766."; fi
    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
    cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$BK</string><string>serve</string><string>--no-browser</string><string>--port</string><string>$PORT</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>$UV_BIN:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/body-kaizen.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/body-kaizen.log</string>
</dict></plist>
PL
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
  else
    if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
      mkdir -p "$HOME/.config/systemd/user"
      cat > "$HOME/.config/systemd/user/body-kaizen.service" <<UNIT
[Unit]
Description=Body Kaizen dashboard (http://127.0.0.1:$PORT)

[Service]
ExecStart=$BK serve --no-browser --port $PORT
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
UNIT
      systemctl --user daemon-reload && systemctl --user enable body-kaizen.service && systemctl --user restart body-kaizen.service
    else
      say "No systemd user session here: start the dashboard yourself with  $BK"
    fi
  fi
fi

# ---------- 4. launcher: opens the dashboard signed in (reads the key when clicked; never stores it) ----------
ICON_URL="$REPO/raw/main/install/icon.png"
if [ "$OS" = Darwin ]; then
  APP="$HOME/Applications/Body Kaizen.app"; rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cat > "$APP/Contents/MacOS/body-kaizen" <<SH
#!/bin/sh
exec "$BK" open --port $PORT
SH
  chmod +x "$APP/Contents/MacOS/body-kaizen"
  cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Body Kaizen</string><key>CFBundleDisplayName</key><string>Body Kaizen</string>
  <key>CFBundleIdentifier</key><string>app.bodykaizen.launcher</string><key>CFBundleExecutable</key><string>body-kaizen</string>
  <key>CFBundlePackageType</key><string>APPL</string><key>CFBundleIconFile</key><string>icon</string>
  <key>LSUIElement</key><true/>
</dict></plist>
PL
  # the icon: PNG from the repo, turned into .icns with the Mac's own tools (skipped quietly if anything's missing)
  T="$(mktemp -d)"
  if curl -fsSL "$ICON_URL" -o "$T/icon.png" 2>/dev/null && mkdir -p "$T/icon.iconset"; then
    for s in 16 32 128 256 512; do
      sips -z $s $s "$T/icon.png" --out "$T/icon.iconset/icon_${s}x${s}.png" >/dev/null 2>&1 || true
      sips -z $((s*2)) $((s*2)) "$T/icon.png" --out "$T/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null 2>&1 || true
    done
    iconutil -c icns "$T/icon.iconset" -o "$APP/Contents/Resources/icon.icns" 2>/dev/null || true
  fi
  rm -rf "$T"
  LAUNCHER="$APP (in your Applications folder: drag it to the Dock to keep it handy)"
else
  mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/256x256/apps"
  curl -fsSL "$ICON_URL" -o "$HOME/.local/share/icons/hicolor/256x256/apps/body-kaizen.png" 2>/dev/null || true
  cat > "$HOME/.local/share/applications/body-kaizen.desktop" <<DT
[Desktop Entry]
Type=Application
Name=Body Kaizen
Comment=Your private health dashboard
Exec="$BK" open --port $PORT
Icon=body-kaizen
Terminal=false
Categories=Utility;
DT
  LAUNCHER="Body Kaizen in your applications menu"
fi

# ---------- 5. open it, signed in ----------
if [ -z "${BK_NO_SERVICE:-}" ] && [ -z "${BK_NO_OPEN:-}" ]; then
  i=0; while [ $i -lt 60 ] && ! port_busy; do sleep 0.5; i=$((i+1)); done
  "$BK" open --port "$PORT" || true
fi

say "Body Kaizen is installed."
if [ -z "${BK_NO_SERVICE:-}" ]; then echo "  Dashboard:  http://127.0.0.1:$PORT  (it starts at login)"; else echo "  Dashboard:  start it with  $BK"; fi
echo "  Launcher:   $LAUNCHER: it opens the dashboard signed in, in any browser"
echo "  Next:       set up your AI assistant: $REPO#quick-start"
