#!/bin/bash

# Script pour désinstaller l'Agent SECeF SIGEL des services d'arrière-plan macOS

SERVICE_NAME="com.sigel.mcfagent"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

echo "Désinstallation du service SIGEL Agent..."

if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH"
    rm "$PLIST_PATH"
    echo "Service arrêté et supprimé."
else
    echo "Le service n'est pas installé."
fi
