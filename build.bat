@echo off
set APP_NAME=sigel-mcf-agent
set MAIN_SCRIPT=mcf_agent.py

echo --- BUILDING EXECUTABLE FOR WINDOWS (SEPARATE FOLDER) ---

:: Créer l'environnement virtuel si besoin
if not exist venv (
    echo Creation de l'environnement virtuel...
    python -m venv venv
)

:: Activation
call venv\Scripts\activate.bat

:: Installer les dépendances
echo Installation des dependances...
pip install -r requirements.txt

:: Créer l'exécutable
echo Generation de l'executable avec PyInstaller...
pyinstaller --onefile ^
            --name "%APP_NAME%" ^
            --hidden-import="flask" ^
            --hidden-import="flask_cors" ^
            --hidden-import="serial" ^
            "%MAIN_SCRIPT%"

if %ERRORLEVEL% EQU 0 (
    echo SUCCESS: L'executable est disponible dans le dossier 'dist\'
) else (
    echo ERROR: La generation a echoue.
)

pause
