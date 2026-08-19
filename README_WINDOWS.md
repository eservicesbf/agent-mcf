# Génération de l'exécutable Windows

Pour obtenir un fichier `.exe` pour Windows, vous devez exécuter la procédure de "build" sur un ordinateur Windows (on ne peut pas générer un `.exe` depuis un Mac).

### Étapes à suivre sur votre PC Windows :

1. **Récupérer le dossier de packaging** : Copiez le dossier `agent-mcf-packaging` sur votre PC Windows.
2. **Lancer le build** : Double-cliquez sur le fichier `build.bat`.
   - Le script va créer un environnement virtuel Python.
   - Il va installer les dépendances nécessaires (`Flask`, `PySerial`, `PyInstaller`).
   - Il va générer le fichier `sigel-mcf-agent.exe`.
3. **Récupérer le résultat** : Votre exécutable sera disponible dans le sous-dossier `dist/`.

### Déploiement client :
Une fois le `.exe` généré, il vous suffit de copier deux fichiers sur le poste de votre client :
- `sigel-mcf-agent.exe`
- `config.ini` (pour les réglages du port COM et de l'IFU).
