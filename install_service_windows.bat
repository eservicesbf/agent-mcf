@echo off
setlocal

:: Script pour installer l'Agent SECeF SIGEL en tant que tâche de fond sur Windows

set "TASK_NAME=SigelMcfAgent"
:: Chemin vers l'exécutable (relativement au dossier packaging)
set "AGENT_EXE=%~dp0dist\sigel-mcf-agent.exe"

echo Installation de l'agent au demarrage de Windows...

:: Création de la tâche planifiée via PowerShell pour une meilleure gestion du lancement au logon
powershell -Command "Unregister-ScheduledTask -TaskName '%TASK_NAME%' -Confirm:$false" 2>nul

powershell -Command "$action = New-ScheduledTaskAction -Execute '%AGENT_EXE%' -WorkingDirectory '%~dp0dist'; $trigger = New-ScheduledTaskTrigger -AtLogOn; Register-ScheduledTask -Action $action -Trigger $trigger -TaskName '%TASK_NAME%' -Description 'Agent SECeF SIGEL' -Settings (New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)"

if %errorlevel% equ 0 (
    echo.
    echo SUCCESS: L'agent est configure pour demarrer automatiquement a chaque ouverture de session.
    echo Vous pouvez le demarrer manuellement maintenant ou redemarrer la session.
) else (
    echo.
    echo ERREUR: Impossible de creer la tache planifiee.
)

pause
