#!/bin/bash

# Script pour installer l'Agent SECeF SIGEL en tant que service d'arrière-plan sur macOS

SERVICE_NAME="com.sigel.mcfagent"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"
AGENT_PATH="/Users/macbookair2017/sigel/agent-mcf-packaging/dist/sigel-mcf-agent"
WORKING_DIR="/Users/macbookair2017/sigel/agent-mcf-packaging/dist"

echo "Installation du service LaunchAgent pour macOS..."

# Création du fichier plist
cat <<EOF > "$PLIST_PATH"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${AGENT_PATH}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>${WORKING_DIR}</string>
    <key>StandardOutPath</key>
    <string>${WORKING_DIR}/service_output.log</string>
    <key>StandardErrorPath</key>
    <string>${WORKING_DIR}/service_error.log</string>
</dict>
</plist>
EOF

# Chargement du service
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "Service installé et démarré."
echo "L'agent tournera désormais en arrière-plan à chaque ouverture de session."
echo "Vous pouvez vérifier l'état avec : launchctl list | grep sigel"
