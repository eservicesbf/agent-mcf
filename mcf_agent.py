from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import logging
import configparser
import os
import time
import serial.tools.list_ports
from mcf_protocol import BinaryMcfProtocol

# Configuration des logs
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log")
    ]
)

app = Flask(__name__)
CORS(app)

class McfAgent:
    def __init__(self, config_path="config.ini"):
        self.config = configparser.ConfigParser()
        if os.path.exists(config_path):
            self.config.read(config_path)
        
        # Détection du port par défaut selon l'OS
        default_port = "COM1" if os.name == 'nt' else "/dev/cu.usbmodem14101"
        
        self.port = self.config.get("MCF", "port", fallback=default_port)
        self.baudrate = self.config.getint("MCF", "baudrate", fallback=9600)
        self.web_port = self.config.getint("MCF", "web_port", fallback=5006)
        self.simulation = self.config.getboolean("MCF", "simulation", fallback=False)
        self.ifu_fixe = self.config.get("MCF", "ifu_fixe", fallback="00187728H")
        self.isf_default = self.config.get("MCF", "isf", fallback="SIGEL001")
        
        self.mcf = BinaryMcfProtocol(self.port, self.baudrate)
        
    def save_config(self, settings):
        """Met à jour le fichier config.ini avec les nouveaux réglages"""
        if 'MCF' not in self.config:
            self.config['MCF'] = {}
            
        self.config['MCF']['port'] = settings.get('port', self.port)
        self.config['MCF']['baudrate'] = settings.get('baudrate', str(self.baudrate))
        self.config['MCF']['simulation'] = str(settings.get('simulation', self.simulation)).lower()
        self.config['MCF']['ifu_fixe'] = settings.get('ifu_fixe', self.ifu_fixe)
        self.config['MCF']['isf'] = settings.get('isf', self.isf_default)
        
        with open("config.ini", "w") as configfile:
            self.config.write(configfile)
        
        # Recharger les variables locales
        self.port = settings.get('port', self.port)
        self.simulation = str(settings.get('simulation', self.simulation)).lower() == 'true'
        self.ifu_fixe = settings.get('ifu_fixe', self.ifu_fixe)
        self.isf_default = settings.get('isf', self.isf_default)
        
        # Réinitialiser le protocole si le port a changé
        self.mcf = BinaryMcfProtocol(self.port, self.baudrate)
        return True
        
    def certifier_facture(self, data):
        if self.simulation:
            logging.info("--- SIMULATION DE CERTIFICATION ---")
            time.sleep(1)
            return {
                "sig": "SIG_SIMULATED_" + os.urandom(4).hex().upper(),
                "nim": "EL02000030",
                "dt": time.strftime("%Y%m%d%H%M%S"),
                "fc": "123",
                "tc": "456",
                "ft": "FV",
                "fn": data.get('num_facture', 'FAC-001'),
                "ifu": self.ifu_fixe
            }

        try:
            logging.info(f"Début certification binaire pour {data.get('num_facture')}...")
            
            # --- Étape 0 : Annulation session précédente au cas où ---
            self.mcf.send_binary_command(0x38, "C") 
            
            # --- Étape 0.5 : C3h - Informations Client (OBLIGATOIRE avant C0h) ---
            client = data.get('client')
            if client:
                ctype = client.get('ctype', 'CC')
                cifu = client.get('ifu', '')
                cnom = self.mcf.echapper(client.get('nom', ''))
                cadd = self.mcf.echapper(client.get('adresse', ''))
                ctel = client.get('telephone', '')
                ceml = client.get('email', '')
                crccm = client.get('rccm', '')
                c3_data = f"{ctype},{cifu},{cnom},{cadd},{ctel},{ceml},{crccm}"
            else:
                c3_data = "" # Client comptant par défaut
            
            resp, err = self.mcf.send_binary_command(0xC3, c3_data)
            if err: return {"error": f"C3h (Délai): {err}"}
            if resp.startswith("E:"): return {"error": f"C3h (HW): {resp[2:].strip()}"}
            logging.info("C3h (Client) OK")

            # --- Étape 1 : C0h - Début de facture ---
            # Format FV/FT/EV/ET : OPID,OPN,IFU,VT,PMODE,ISF,FN
            # Format FA/EA (avoir): OPID,OPN,IFU,VT,NATURE,RN,PMODE,ISF,FN
            op = data.get('operateur', {})
            op_id = op.get('id', '1')
            op_name = self.mcf.echapper(op.get('nom', 'Admin'))
            ifu = self.ifu_fixe
            v_type = data.get('type_facture', 'FV')
            p_mode = "TTC" # Forcé en TTC car SIGEL envoie montant_ttc
            isf_id = data.get('isf') or self.isf_default
            fn = data.get('num_facture')
            
            if v_type in ['FA', 'EA']:
                # Avoir: NATURE et RN s'insèrent entre VT et PMODE
                rn = data.get('rn', '')
                nature = data.get('nature', 'RAN')
                c0_data = f"{op_id},{op_name},{ifu},{v_type},{nature},{rn},{p_mode},{isf_id},{fn}"
                logging.info(f"C0h Avoir: nature={nature}, rn={rn}, c0_data={c0_data}")
            else:
                c0_data = f"{op_id},{op_name},{ifu},{v_type},{p_mode},{isf_id},{fn}"
            resp, err = self.mcf.send_binary_command(0xC0, c0_data)
            if err: return {"error": f"C0h (Délai): {err}"}
            if resp.startswith("E:"): return {"error": f"C0h (HW): {resp[2:].strip()}"}
            logging.info(f"C0h OK: {resp}")

            # --- Étape 2 : 31h - Articles ---
            # Utilise 'articles' (clé envoyée par SIGEL)
            articles = data.get('articles', [])
            if not articles:
                self.mcf.send_binary_command(0x38, "C")
                return {"error": "Aucun article dans la facture"}

            for item in articles:
                nom = self.mcf.echapper(item.get('nom', 'Article'))
                itype = item.get('itype', 'LOCBIE')
                tax_grp = item.get('tax', 'B')
                taux = f"{float(item.get('taux', 18)):.2f}"
                
                montant = float(item.get('montant', 0))
                qty = float(item.get('quantite', 1))
                
                # Le boîtier exige un montant entier (pas de décimales)
                # On arrondit le montant, puis on recalcule le prix à partir 
                # du montant arrondi pour garantir : prix * qty = montant exact
                montant_int = round(montant)
                prix = montant_int / qty if qty > 0 else montant_int
                
                # Format original qui fonctionne avec le boîtier :
                # NOM \t ITYPE,TAXtaux%montant \t prix*qty
                data_31 = f"{nom}\x09{itype},{tax_grp}{taux}%{montant_int}\x09{prix:.2f}*{qty:.3f}"
                
                logging.info(f"31h trame: {data_31}")
                resp, err = self.mcf.send_binary_command(0x31, data_31)
                if err: 
                    self.mcf.send_binary_command(0x38, "C")
                    return {"error": f"31h ({nom}) (Délai): {err}"}
                if resp.startswith("E:"):
                    self.mcf.send_binary_command(0x38, "C")
                    return {"error": f"31h ({nom}) (HW): {resp[2:].strip()}"}
                logging.info(f"31h OK: {nom}")

            # --- Étape 3 : 33h - Sous-total ---
            resp, err = self.mcf.send_binary_command(0x33, "")
            if err: 
                self.mcf.send_binary_command(0x38, "C")
                return {"error": f"33h (Délai): {err}"}
            if resp.startswith("E:"):
                self.mcf.send_binary_command(0x38, "C")
                return {"error": f"33h (HW): {resp[2:].strip()}"}
            
            # On extrait le montant total calculé par le MCF
            try:
                mcf_total = resp.split(',')[0]
                if not mcf_total: raise ValueError("Total vide")
                logging.info(f"33h OK - Total MCF: {mcf_total}")
            except Exception as e:
                logging.warning(f"Impossible de lire le total MCF, utilisation du total SIGEL: {e}")
                mcf_total = f"{data.get('montant_total', 0):.2f}"

            # --- Étape 4 : 35h - Paiement ---
            # On peut boucler sur les paiements envoyés par SIGEL
            paiements = data.get('paiements', [])
            if not paiements:
                # Espèces par défaut sur le reste si vide
                self.mcf.send_binary_command(0x35, f"E{mcf_total}")
            else:
                for p in paiements:
                    mode = p.get('mode', 'E')
                    mt = p.get('montant') or mcf_total # Si montant Null, on prend tout
                    resp, err = self.mcf.send_binary_command(0x35, f"{mode}{mt}")
                    if err or resp.startswith("E:"):
                        logging.warning(f"Erreur paiement {mode}: {err or resp}")
                        # On continue car le MCF gère le reste en espèces au besoin

            # --- Étape 5 : 38h - Fin de facture (Certification) ---
            # MV doit correspondre exactement au total retourné par 33h
            resp, err = self.mcf.send_binary_command(0x38, f"{float(mcf_total):.2f}")
            if err: 
                self.mcf.send_binary_command(0x38, "C")
                return {"error": f"38h (Délai): {err}"}
            if resp.startswith("E:"):
                self.mcf.send_binary_command(0x38, "C")
                return {"error": f"38h (HW): {resp[2:].strip()}"}
            
            logging.info(f"38h SUCCESS: {resp}")

            # Parsing réponse 38h: FC,TC,FT,DT,NIM,IFU,SIG[,FN]
            parts = resp.split(',')
            if len(parts) >= 7:
                return {
                    "sig": parts[6],
                    "nim": parts[4],
                    "dt": parts[3],
                    "fc": parts[0],
                    "tc": parts[1],
                    "ft": parts[2],
                    "fn": parts[7] if len(parts) > 7 else data.get('num_facture'),
                    "ifu": parts[5]
                }
            
            return {"error": f"Réponse 38h malformée (champs={len(parts)})"}

        except Exception as e:
            logging.error(f"Erreur fatale certification: {e}")
            self.mcf.send_binary_command(0x38, "C")
            import traceback
            logging.error(traceback.format_exc())
            return {"error": str(e)}

    def generer_rapport(self, report_type):
        """Génère un rapport fiscal via le boîtier MCF.
        
        Commandes matérielles ST 1.0 :
        - 0x40 : Rapport X (état provisoire, pas de remise à zéro)
        - 0x41 : Rapport Z (clôture journalière, remise à zéro)
        - 0x42 : Rapport A (audit)
        
        Format réponse ST 1.0 (CSV) :
        NR, MontantA, MontantB, MontantC, MontantD, TaxeA, TaxeB, TaxeC, TaxeD, Date
        """
        cmd_map = {
            'X': 0x40,
            'Z': 0x41,
            'A': 0x42,
        }
        
        rtype = report_type.upper()
        cmd = cmd_map.get(rtype)
        if not cmd:
            return {"error": f"Type de rapport inconnu: {report_type}. Valeurs acceptées: X, Z, A"}
        
        labels = {
            'X': 'Rapport X — État provisoire',
            'Z': 'Rapport Z — Clôture journalière',
            'A': 'Rapport A — Audit',
        }
        
        if self.simulation:
            logging.info(f"--- SIMULATION RAPPORT {rtype} ---")
            time.sleep(0.5)
            return {
                "type": rtype,
                "label": labels[rtype],
                "mode": "SIMULATION",
                "date_rapport": time.strftime("%d/%m/%Y %H:%M:%S"),
                "data_brute": "SIMULATION_DATA",
                "_notice": "Données de simulation — le mode simulation est activé dans l'agent."
            }
        
        try:
            logging.info(f"Envoi commande rapport {rtype} (cmd={hex(cmd)}) au boîtier...")
            
            resp, err = self.mcf.send_binary_command(cmd, "", timeout=15.0)
            
            if err:
                return {"error": f"Rapport {rtype} — Erreur: {err}"}
            
            if resp and resp.startswith("E:"):
                return {"error": f"Rapport {rtype} — Rejet matériel: {resp[2:].strip()}"}
            
            logging.info(f"Rapport {rtype} reçu: {resp}")
            
            # Parser la réponse CSV du boîtier
            parsed = self._parser_rapport(rtype, resp or "", labels[rtype])
            return parsed
            
        except Exception as e:
            logging.error(f"Erreur fatale rapport {rtype}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return {"error": str(e)}

    def _parser_rapport(self, rtype, raw_data, label):
        """Parse la réponse brute CSV du boîtier en données structurées.
        
        Format X (10 champs) : NR, MontantA..D, TaxeA..D, Date
        Format Z (8 champs) : MontantA..D, TaxeA..D
        """
        parts = [p.strip() for p in raw_data.split(',')]
        
        result = {
            "type": rtype,
            "label": label,
            "date_rapport": time.strftime("%d/%m/%Y %H:%M:%S"),
            "data_brute": raw_data,
        }
        
        if not raw_data:
            result["_notice"] = "Réponse vide. (Commande non autorisée ou non supportée en mode test)"
            return result
            
        if len(parts) == 8:
            nb_factures = '—'
            m_idx = 0
            t_idx = 4
            date_formatee = time.strftime("%d/%m/%Y")
        elif len(parts) >= 10:
            try:
                nb_factures = int(parts[0])
            except ValueError:
                nb_factures = '—'
            m_idx = 1
            t_idx = 5
            date_raw = parts[9]
            if len(date_raw) == 8:
                date_formatee = f"{date_raw[0:2]}/{date_raw[2:4]}/{date_raw[4:8]}"
            else:
                date_formatee = date_raw
        else:
            result["_notice"] = f"Format inattendu ({len(parts)} champs). Données brutes retournées."
            return result
        
        try:
            # Montants TTC par groupe de taxation (en centimes → diviser par 100)
            montant_a = int(parts[m_idx]) / 100
            montant_b = int(parts[m_idx+1]) / 100
            montant_c = int(parts[m_idx+2]) / 100
            montant_d = int(parts[m_idx+3]) / 100
            
            # Taxes par groupe
            taxe_a = int(parts[t_idx]) / 100
            taxe_b = int(parts[t_idx+1]) / 100
            taxe_c = int(parts[t_idx+2]) / 100
            taxe_d = int(parts[t_idx+3]) / 100
            
            # Totaux calculés
            total_montant = montant_a + montant_b + montant_c + montant_d
            total_taxe = taxe_a + taxe_b + taxe_c + taxe_d
            
            result.update({
                "nb_factures": nb_factures,
                "date_boitier": date_formatee,
                "groupes": {
                    "A": {"montant": f"{montant_a:,.0f}", "taxe": f"{taxe_a:,.0f}"},
                    "B": {"montant": f"{montant_b:,.0f}", "taxe": f"{taxe_b:,.0f}"},
                    "C": {"montant": f"{montant_c:,.0f}", "taxe": f"{taxe_c:,.0f}"},
                    "D": {"montant": f"{montant_d:,.0f}", "taxe": f"{taxe_d:,.0f}"},
                },
                "totaux": {
                    "montant_ttc": f"{total_montant:,.0f}",
                    "total_taxes": f"{total_taxe:,.0f}",
                    "montant_ht": f"{(total_montant - total_taxe):,.0f}",
                },
            })
            
        except (ValueError, IndexError) as e:
            logging.warning(f"Erreur parsing rapport: {e}")
            result["_notice"] = f"Parsing partiel — erreur: {str(e)}"
        
        return result

agent = McfAgent()

@app.route('/status', methods=['GET'])
def get_status():
    """Endpoint pour vérifier si l'agent répond"""
    return jsonify({
        "status": "ready",
        "port": agent.port,
        "simulation": agent.simulation
    })

@app.route('/certifier', methods=['POST', 'OPTIONS'])
def certifier():
    """Route principale appelée par SIGEL pour signer une facture"""
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.json
    logging.info(f"Requête de certification reçue pour facture: {data.get('num_facture')}")
    
    result = agent.certifier_facture(data)
    
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/rapport', methods=['POST', 'OPTIONS'])
def rapport():
    """Route pour générer les rapports fiscaux X, Z, A"""
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.json or {}
    report_type = data.get('type', 'X')
    logging.info(f"Requête de rapport fiscal reçue: type={report_type}")
    
    result = agent.generer_rapport(report_type)
    
    if "error" in result:
        return jsonify(result), 500
    return jsonify(result)

@app.route('/', methods=['GET'])
def index():
    html_content = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard Agent SECeF - SIGEL</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --primary: #3b82f6;
            --accent: #22c55e;
            --text: #f8fafc;
        }
        body {
            font-family: 'Outfit', sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            width: 100%;
            max-width: 600px;
            background: var(--card);
            padding: 2.5rem;
            border-radius: 20px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            border: 1px solid rgba(255,255,255,0.1);
        }
        h1 { font-weight: 600; margin-bottom: 0.5rem; color: var(--primary); }
        .status { 
            display: inline-block; padding: 0.2rem 0.8rem; border-radius: 20px; 
            font-size: 0.8rem; background: rgba(59, 130, 246, 0.2); 
            color: var(--primary); margin-bottom: 2rem;
        }
        .status.simulation { background: rgba(34, 197, 94, 0.2); color: var(--accent); }
        
        .field { margin-bottom: 1.5rem; }
        label { display: block; margin-bottom: 0.5rem; font-size: 0.9rem; opacity: 0.8; }
        input, select {
            width: 100%; padding: 0.8rem; border-radius: 10px; border: 1px solid rgba(255,255,255,0.2);
            background: #0f172a; color: white; display: block; box-sizing: border-box;
        }
        .btn {
            background: var(--primary); color: white; border: none; padding: 1rem;
            width: 100%; border-radius: 10px; cursor: pointer; font-weight: 600;
            transition: transform 0.2s, background 0.2s; margin-top: 1rem;
        }
        .btn:hover { background: #2563eb; transform: translateY(-2px); }
        .btn:active { transform: translateY(0); }
        
        .row { display: flex; gap: 1rem; }
        .row .field { flex: 1; }
        
        .scan-btn {
            background: transparent; border: 1px solid var(--primary); color: var(--primary);
            padding: 0.5rem; border-radius: 5px; cursor: pointer; font-size: 0.7rem;
            margin-top: 0.5rem; display: inline-block;
        }
        #toast {
            position: fixed; bottom: 20px; right: 20px; padding: 1rem 2rem;
            background: var(--accent); color: white; border-radius: 10px;
            transform: translateY(100px); transition: transform 0.3s;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Configuration Agent MCF</h1>
        <div id="status-badge" class="status">Prêt</div>
        
        <form id="config-form">
            <div class="field">
                <label>Port Série (Boîtier MCF)</label>
                <select id="port" name="port">
                    <option value="">Chargement...</option>
                </select>
                <div class="scan-btn" onclick="loadPorts()">Scanner les ports</div>
            </div>
            
            <div class="row">
                <div class="field">
                    <label>IFU Entreprise</label>
                    <input type="text" id="ifu_fixe" name="ifu_fixe" placeholder="00187728H">
                </div>
                <div class="field">
                    <label>ID Logiciel (ISF)</label>
                    <input type="text" id="isf" name="isf" placeholder="SIGEL001">
                </div>
            </div>
            
            <div class="field">
                <label>Mode Simulation</label>
                <select id="simulation" name="simulation">
                    <option value="false">Désactivé (Réel)</option>
                    <option value="true">Activé (Tests virtuels)</option>
                </select>
            </div>
            
            <button type="submit" class="btn">Enregistrer la Configuration</button>
        </form>
    </div>

    <div id="toast">Réglages enregistrés !</div>

    <script>
        async function loadPorts() {
            const resp = await fetch('/api/ports');
            const data = await resp.json();
            const select = document.getElementById('port');
            const current = select.value;
            select.innerHTML = '';
            data.ports.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.device;
                opt.textContent = `${p.device} (${p.description})`;
                if(p.device === current) opt.selected = true;
                select.appendChild(opt);
            });
        }

        async function loadConfig() {
            const resp = await fetch('/api/config');
            const data = await resp.json();
            document.getElementById('port').value = data.port;
            document.getElementById('ifu_fixe').value = data.ifu_fixe;
            document.getElementById('isf').value = data.isf;
            document.getElementById('simulation').value = data.simulation.toString();
            
            const badge = document.getElementById('status-badge');
            if(data.simulation) {
                badge.textContent = "Mode Simulation";
                badge.classList.add('simulation');
            } else {
                badge.textContent = "Prêt (Boîtier)";
                badge.classList.remove('simulation');
            }
            
            // Re-load ports to ensure current one is in list
            await loadPorts();
            document.getElementById('port').value = data.port;
        }

        document.getElementById('config-form').onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            
            const resp = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            
            if(resp.ok) {
                const toast = document.getElementById('toast');
                toast.style.transform = 'translateY(0)';
                setTimeout(() => toast.style.transform = 'translateY(100px)', 3000);
                loadConfig();
            }
        };

        loadConfig();
    </script>
</body>
</html>
    """
    return render_template_string(html_content)

@app.route('/api/ports', methods=['GET'])
def list_ports():
    ports = serial.tools.list_ports.comports()
    result = []
    for p in ports:
        result.append({
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid
        })
    return jsonify({"ports": result})

@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'GET':
        return jsonify({
            "port": agent.port,
            "baudrate": agent.baudrate,
            "simulation": agent.simulation,
            "ifu_fixe": agent.ifu_fixe,
            "isf": agent.isf_default
        })
    
    data = request.json
    success = agent.save_config(data)
    return jsonify({"success": success})

if __name__ == "__main__":
    print("\n--- AGENT SECeF SIGEL (BINARY MODE) ---")
    print(f"Mode Simulation: {'OUI' if agent.simulation else 'NON'}")
    print(f"Port configuré: {agent.port} ({agent.baudrate} bauds)")
    print(f"Dashboard: http://localhost:{agent.web_port}")
    print("-" * 26)
    
    try:
        app.run(host='0.0.0.0', port=agent.web_port)
    except OSError as e:
        if e.errno == 48 or e.errno == 98: # Address already in use
            print(f"\nERREUR: Le port {agent.web_port} est déjà occupé.")
            print("Vous pouvez changer le port dans 'config.ini' (option web_port).")
        else:
            raise e
