#!/bin/bash

# Configuration
APP_NAME="sigel-mcf-agent"
MAIN_SCRIPT="mcf_agent.py"

echo "--- BUILDING EXECUTABLE IN SEPARATE FOLDER ---"

# Créer l'environnement virtuel si besoin
if [ ! -d "venv" ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv venv
fi

source venv/bin/activate

# Installer les dépendances
echo "Installation des dépendances..."
pip install -r requirements.txt

# Créer l'exécutable
echo "Génération de l'exécutable..."
pyinstaller --onefile \
            --name "$APP_NAME" \
            --hidden-import="flask" \
            --hidden-import="flask_cors" \
            --hidden-import="serial" \
            "$MAIN_SCRIPT"

if [ $? -eq 0 ]; then
    echo "SUCCESS: L'exécutable est disponible dans $(pwd)/dist/"
    echo "Le dossier d'origine agent-mcf est resté propre."
else
    echo "ERROR: La génération a échoué."
    exit 1
fi
