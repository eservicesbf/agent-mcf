@echo off
setlocal

:: Script pour desinstaller l'Agent SECeF SIGEL des taches planifiees Windows

set "TASK_NAME=SigelMcfAgent"

echo Arret et suppression de la tache planifiee %TASK_NAME%...

:: Suppression de la tâche planifiée via PowerShell
powershell -Command "Unregister-ScheduledTask -TaskName '%TASK_NAME%' -Confirm:$false" 2>nul

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS: L'agent a ete desinstalle avec succes.
    echo Il ne demarrera plus automatiquement.
) else (
    echo.
    echo NOTE: La tache n'existait pas ou a deja ete supprimee.
)

pause
