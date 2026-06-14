#!/usr/bin/env bash
set -euo pipefail

UTIL_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$UTIL_DIR/../.." && pwd)"
LABEL="com.mundial.descargador"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "Este instalador usa launchd y solo aplica a macOS."
    echo "En Linux crea un cron o systemd timer que ejecute: $PROJECT_ROOT/run.sh"
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_ROOT/run.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$PROJECT_ROOT</string>

    <key>StartInterval</key>
    <integer>1800</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$PROJECT_ROOT/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_ROOT/launchd_stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PROJECT_ROOT/venv/bin</string>
        <key>LANG</key>
        <string>es_AR.UTF-8</string>
    </dict>

    <key>KeepAlive</key>
    <false/>

    <key>TimeOut</key>
    <integer>7200</integer>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"

echo "Tarea instalada: $LABEL"
echo "Se ejecutara cada 30 minutos y el script decidira que partidos ya estan listos."
