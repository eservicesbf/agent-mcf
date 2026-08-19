import serial
import serial.tools.list_ports
import threading
import time
import logging
import os

class BinaryMcfProtocol:
    """
    Protocole Binaire SECEF BF ST 1.0 (Orange BF).
    Gère la trame SOH, LEN, SEQ, CMD, DATA, AMB, BCC, ETX.
    """
    def __init__(self, port_hint="/dev/cu.usbmodem14101", baudrate=9600):
        self.port_hint = port_hint
        self.baudrate = baudrate
        self.ser = None
        self.lock = threading.Lock()
        self.seq = 0x20  # Début à 0x20 selon spec

    def find_port(self):
        ports = serial.tools.list_ports.comports()
        for p in ports:
            if self.port_hint in p.device:
                return p.device
        return None

    def connect(self):
        with self.lock:
            try:
                if self.ser and self.ser.is_open:
                    if os.path.exists(self.ser.port):
                        return True
                    else:
                        self.close_internal()

                target_port = self.find_port() or self.port_hint
                if not os.path.exists(target_port):
                    return False

                self.ser = serial.Serial(target_port, self.baudrate, timeout=1)
                # Purge initiale
                self.ser.read_all()
                return True
            except Exception as e:
                logging.error(f"Erreur de connexion: {e}")
                self.ser = None
                return False

    def close_internal(self):
        if self.ser:
            try: self.ser.close()
            except: pass
            self.ser = None

    def echapper(self, texte: str) -> str:
        """Échappe les caractères réservés selon la spec."""
        if not texte: return ""
        replacements = {
            '\r': '^xa;',
            '\n': '^xd;',
            ',':  '^x2c;',
            '<':  '^lt;',
            '>':  '^gt;',
            '&':  '^amp;'
        }
        for char, repl in replacements.items():
            texte = texte.replace(char, repl)
        return texte

    def calculer_bcc(self, payload: bytes) -> bytes:
        """Calcul du BCC sur 4 octets (quartets + 0x30)."""
        somme = sum(payload) & 0xFFFF
        bcc = bytearray(4)
        for i in range(3, -1, -1):
            bcc[i] = (somme & 0x0F) + 0x30
            somme >>= 4
        return bytes(bcc)

    def construire_trame(self, cmd_byte: int, data_str: str = "") -> bytes:
        """Construit une trame binaire complète."""
        data_bytes = data_str.encode('utf-8') if data_str else b''
        # LEN = length(DATA) + 4 + 0x20
        len_byte = len(data_bytes) + 4 + 0x20
        # Payload pour BCC: LEN, SEQ, CMD, DATA, AMB
        payload = bytes([len_byte, self.seq, cmd_byte]) + data_bytes + bytes([0x05])
        bcc = self.calculer_bcc(payload)
        
        frame = bytes([0x01]) + payload + bcc + bytes([0x03])
        return frame

    def send_binary_command(self, cmd_byte: int, data_str: str = "", timeout=5.0):
        """Envoie une commande binaire et gère NAK/SYN."""
        if not self.connect():
            return None, "Erreur connexion port série"

        with self.lock:
            try:
                frame = self.construire_trame(cmd_byte, data_str)
                logging.debug(f"--> [SEND BIN] CMD={hex(cmd_byte)} DATA='{data_str}' HEX={frame.hex()}")
                
                # Tentatives (max 3 NAK)
                for attempt in range(3):
                    self.ser.read_all() # Clean buffer
                    self.ser.write(frame)
                    
                    # Lecture réponse
                    resp_data, err = self.lire_reponse(timeout)
                    if err == "NAK":
                        logging.warning(f"NAK reçu, nouvelle tentative ({attempt+1}/3)...")
                        continue
                    return resp_data, err
                
                return None, "Échec après 3 tentatives (NAK persistant)"
            except Exception as e:
                logging.error(f"Erreur envoi binaire: {e}")
                self.close_internal()
                return None, str(e)
            finally:
                # Incrémenter SEQ seulement pour les nouvelles commandes (hors tentatives NAK)
                self.seq = (self.seq + 1) if self.seq < 0xFF else 0x20

    def lire_reponse(self, timeout=5.0):
        """Lit la réponse en gérant SYN (0x16) et NAK (0x15)."""
        start_time = time.time()
        resp_bytes = b""
        
        while (time.time() - start_time) < timeout:
            char = self.ser.read(1)
            if not char:
                continue
            
            val = char[0]
            if val == 0x15: # NAK
                return None, "NAK"
            elif val == 0x16: # SYN
                logging.debug("MCF occupé (SYN)...")
                time.sleep(0.1)
                continue
            elif val == 0x01: # SOH (Début réponse)
                # Lire jusqu'à ETX (0x03)
                resp_bytes = char + self.ser.read_until(b'\x03')
                logging.debug(f"<-- [RECV BIN] HEX={resp_bytes.hex()}")
                
                # Parsing basique de la DATA de réponse
                # Format: SOH, LEN, SEQ, CMD, DATA, BRK, STA, AMB, BCC, ETX
                # DATA est entre l'index 4 et l'index de BRK (0x04)
                try:
                    brk_idx = resp_bytes.find(0x04)
                    if brk_idx != -1:
                        data_part = resp_bytes[4:brk_idx]
                        return data_part.decode('utf-8', errors='ignore'), None
                    return "", None
                except Exception as e:
                    return None, f"Erreur parsing: {e}"
        
        return None, "Timeout réponse"

    def close(self):
        with self.lock:
            self.close_internal()
