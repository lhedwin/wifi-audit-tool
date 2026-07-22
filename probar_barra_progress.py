#!/usr/bin/env python3
"""
Herramienta independiente que toma el ETA inicial real de Hashcat desde su salida
de texto estándar y lo usa para mover la barra de progreso de forma 100% matemática.

Corrige el bucle de reinicios constantes bloqueando la estampa de tiempo inicial.
"""

import os
import sys
import time
import shlex
import shutil
import subprocess
import re
import threading
import signal
import pty
import select
from pathlib import Path

WORK_DIR = Path(__file__).resolve().parent
state_lock = threading.Lock()

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def cprint(msg, color=Colors.ENDC, end='\n'):
    print(f"{color}{msg}{Colors.ENDC}", end=end)


def run_cmd(cmd, timeout=30, capture=True):
    try:
        if isinstance(cmd, str):
            cmd_list = shlex.split(cmd)
        else:
            cmd_list = cmd
        result = subprocess.run(cmd_list, capture_output=capture, text=True, timeout=timeout)
        return result.stdout, result.stderr, result.returncode
    except:
        return "", "ERROR", -1


def _fmt_time(secs):
    if secs is None or secs < 0 or secs == float('inf'):
        return '--:--:--'
    secs = int(secs)
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
    return f"{h}h:{m:02d}m:{s:02d}s" if h else f"{m:02d}m:{s:02d}s"


def get_interpolated_progress(state, now=None):
    now = now or time.time()
    with state_lock:
        elapsed_total = now - state['start_time']
        eta_base = state['hashcat_eta_secs']
        saw_eta = state['saw_eta']

    if saw_eta and eta_base > 0:
        pct = (elapsed_total / eta_base) * 100.0
        pct = min(99.5, max(pct, 0.0))
        
        remaining_secs = max(0, eta_base - elapsed_total)
        eta_str = _fmt_time(remaining_secs)
    else:
        pct = 0.0
        eta_str = "Calculando..."

    return pct, eta_str


def build_progress_line(state, cols=None):
    if cols is None:
        try: cols = shutil.get_terminal_size((80, 20)).columns
        except Exception: cols = 80

    now = time.time()
    with state_lock:
        elapsed = now - state['start_time']
        status = state.get('status', 'Iniciando...')[:10]
    
    elapsed_s = _fmt_time(elapsed)
    pct, eta_str = get_interpolated_progress(state, now)

    if cols < 80:
        bar_width = 16
    elif cols < 100:
        bar_width = 20
    else:
        bar_width = 24
        
    filled = int(bar_width * pct / 100.0)
    bar = '█' * filled + '░' * (bar_width - filled)

    return (f"\r  {Colors.CYAN}[{bar}]{Colors.ENDC} {Colors.BOLD}{pct:6.2f}%{Colors.ENDC} "
            f"{Colors.WARNING}ETA:{Colors.ENDC}{eta_str:13} "
            f"{Colors.CYAN}T:{Colors.ENDC}{elapsed_s:7} [{status}]")


def redraw_progress(state):
    line = build_progress_line(state)
    sys.stderr.write(line + '\033[0K')
    sys.stderr.flush()


def select_input_file():
    files = sorted([p.name for p in WORK_DIR.iterdir() if p.is_file() and p.suffix in {'.hc22000', '.cap', '.txt', '.hash', '.pot'}])
    if not files:
        cprint('[!] No hay archivos de prueba en el directorio.', Colors.FAIL)
        sys.exit(1)

    cprint('\n[+] Archivos disponibles:', Colors.CYAN)
    for idx, name in enumerate(files, 1):
        cprint(f'    {idx}. {name}', Colors.BLUE)

    while True:
        try:
            choice = input('\n[?] Selecciona un archivo (numero): ').strip()
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return WORK_DIR / files[idx]
        except:
            pass
        cprint('[!] Opcion invalida. Intentalo de nuevo.', Colors.FAIL)


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


def main():
    cprint('\n' + '=' * 60, Colors.HEADER)
    cprint('  PROBADOR DE BARRA BASADO EN EL ETA TEXTO DE HASHCAT', Colors.HEADER)
    cprint('=' * 60, Colors.HEADER)

    input_file = select_input_file()
    cprint(f'\n[*] Archivo seleccionado: {input_file.name}', Colors.GREEN)

    state = {
        'done': False,
        'start_time': time.time(),
        'status': 'Iniciando',
        'hashcat_eta_secs': 0,
        'saw_eta': False,
        'cracked_key': None,
        'error_log': []
    }

    redraw_progress(state)

    def draw_progress_loop():
        while not state['done']:
            redraw_progress(state)
            time.sleep(0.1)

    progress_thread = threading.Thread(target=draw_progress_loop, daemon=True)
    progress_thread.start()

    outfile = WORK_DIR / f"{input_file.stem}_resultado.txt"
    
    cmd = [
        'hashcat', '-m', '22000', '-a', '3',
        str(input_file),
        '?d?d?d?d?d?d?d?d',
        '-w', '3',
        '--outfile', str(outfile),
        '--outfile-format=2',
        '--status',
        '--status-timer=1'
    ]

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
        cprint('[!] hashcat no encontrado.', Colors.FAIL)
        sys.exit(1)

    def read_process_output():
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue

            with state_lock:
                state['error_log'].append(line)

            if 'Bypass' in line or 'Status: Bypass' in line:
                with state_lock: state['status'] = 'Bypass'
                continue

            # SOLUCIÓN: Solo extrae y fija el ETA inicial si no ha sido guardado previamente
            if not state['saw_eta']:
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
                                state['start_time'] = time.time()  # Fijo para evitar loops infinitos


    reader_thread = threading.Thread(target=read_process_output, daemon=True)
    reader_thread.start()

    try:
        proc.wait()
    finally:
        state['done'] = True
        reader_thread.join(timeout=1)
        progress_thread.join(timeout=1)
        
        # Verificar si hubo éxito encontrando contraseña
        if outfile.exists() and outfile.stat().st_size > 0:
            try:
                state['cracked_key'] = outfile.read_text().strip()
                state['status'] = 'Cracked!'
                outfile.unlink()
            except:
                pass
        
        sys.stderr.write('\n')
        
        with state_lock:
            if state['status'] in ('Ejecutando', 'Iniciando'):
                state['status'] = 'Agotado'
        
        filled_bar = '█' * 24
        elapsed_final = _fmt_time(time.time() - state['start_time'])
        print(f"  {Colors.CYAN}[{filled_bar}]{Colors.ENDC} {Colors.BOLD}100.00%{Colors.ENDC} "
              f"{Colors.WARNING}ETA:{Colors.ENDC}00m:00s       {Colors.CYAN}T:{Colors.ENDC}{elapsed_final} [{state['status']}]")

    # Reporte de resultados final en la terminal
    print()
    if state['status'] == 'Cracked!' and state['cracked_key']:
        cprint('=' * 60, Colors.GREEN)
        cprint(f'  ¡CONTRASEÑA ENCONTRADA EXITOSAMENTE!', Colors.GREEN + Colors.BOLD)
        cprint(f'  Clave descifrada: {state["cracked_key"]}', Colors.BOLD)
        cprint('=' * 60, Colors.GREEN)
    elif state['status'] == 'Bypass':
        cprint('  [*] El archivo ya estaba resuelto en el historial (Bypass).', Colors.WARNING)
        cprint('  [!] Ejecuta "hashcat --show" para visualizar las credenciales.', Colors.CYAN)
    elif not state['saw_eta'] and len(state['error_log']) > 0:
        cprint('  [!] Hashcat se cerró inesperadamente durante el inicio. Registro de salida:', Colors.FAIL)
        for err_line in state['error_log'][-5:]:
            print(f"      > {err_line}")
    else:
        cprint('  [!] El proceso terminó pero no se recuperó ninguna contraseña.', Colors.FAIL)


if __name__ == '__main__':
    main()
