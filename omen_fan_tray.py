#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
HP Omen Fan Control - System Tray Application
Control de ventiladores con curvas personalizadas y monitoreo en tiempo real
"""

import sys
import os
import json
import time
import threading
import subprocess
import glob
import csv
import shutil
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QSystemTrayIcon, QMenu, 
                             QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QSlider, QCheckBox, 
                             QSpinBox, QDoubleSpinBox, QWidget, QGroupBox,
                             QFormLayout, QLineEdit, QComboBox, QTabWidget,
                             QTextEdit, QProgressBar)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QIcon, QColor

# Importar matplotlib para gráficos
try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("matplotlib no disponible - gráficos deshabilitados")

# Importar numpy para análisis de tendencias
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("numpy no disponible - análisis de tendencias deshabilitado")

# Rutas del sistema (solo monitoreo)
CPU_RPM = Path("/sys/devices/platform/omen-rgb-keyboard/fan/cpu_fan_rpm")
GPU_RPM = Path("/sys/devices/platform/omen-rgb-keyboard/fan/gpu_fan_rpm")
NO_TURBO_PATH = Path("/sys/devices/system/cpu/intel_pstate/no_turbo")

# Detectar automáticamente el hwmon correcto para CPU
def find_cpu_hwmon():
    """Encuentra el hwmon correcto para temperaturas de CPU"""
    for hwmon_num in range(0, 10):  # Buscar en hwmon0-9
        hwmon_path = Path(f"/sys/class/hwmon/hwmon{hwmon_num}")
        if hwmon_path.exists():
            # Verificar si es coretemp (CPU)
            name_file = hwmon_path / "name"
            if name_file.exists():
                try:
                    with open(name_file, 'r') as f:
                        name = f.read().strip()
                    if 'coretemp' in name.lower():
                        return hwmon_path
                except:
                    continue
    
    # Fallback: buscar cualquier hwmon con temp*_input
    for hwmon_num in range(0, 10):
        hwmon_path = Path(f"/sys/class/hwmon/hwmon{hwmon_num}")
        if hwmon_path.exists():
            temp_files = list(hwmon_path.glob("temp*_input"))
            if len(temp_files) >= 2:  # Al menos 2 sensores (probablemente CPU)
                return hwmon_path
    
    return None

CPU_HWMON = find_cpu_hwmon()
if CPU_HWMON:
    TEMP_PATHS = [
        CPU_HWMON / "temp1_input",  # CPU package
        CPU_HWMON / "temp2_input",  # CPU core 0
        CPU_HWMON / "temp3_input",  # CPU core 1
        CPU_HWMON / "temp4_input",  # CPU core 2
        CPU_HWMON / "temp5_input",  # CPU core 3
    ]
else:
    # Fallback a rutas originales
    TEMP_PATHS = [
        Path("/sys/class/hwmon/hwmon6/temp1_input"),
        Path("/sys/class/hwmon/hwmon6/temp2_input"),
        Path("/sys/class/hwmon/hwmon6/temp3_input"),
        Path("/sys/class/hwmon/hwmon6/temp4_input"),
        Path("/sys/class/hwmon/hwmon6/temp5_input"),
    ]

GPU_TEMP_PATHS = [
    Path("/sys/class/drm/card0/device/hwmon/hwmon*/temp1_input"),
    Path("/sys/class/hwmon/hwmon0/temp1_input"),
    Path("/sys/class/hwmon/hwmon3/temp1_input"),  # NVMe GPU
]

CONFIG_FILE = Path.home() / ".config" / "omen-fan-tray" / "config.json"
MAX_RPM = 4800


class SystemChecker:
    """Verifica que el sistema tenga los sensores necesarios para monitoreo"""
    
    @staticmethod
    def check_sensors():
        """Verifica si los sensores de monitoreo están disponibles"""
        warnings = []
        
        # Verificar archivos RPM (importantes para monitoreo)
        if not CPU_RPM.exists():
            warnings.append("Archivo cpu_fan_rpm no encontrado - Monitoreo RPM limitado")
        
        if not GPU_RPM.exists():
            warnings.append("Archivo gpu_fan_rpm no encontrado - Monitoreo RPM limitado")
        
        # Verificar archivos de temperatura
        temp_available = any(path.exists() for path in TEMP_PATHS)
        if not temp_available:
            warnings.append("No se encontraron sensores de temperatura - Monitoreo de temperatura deshabilitado")
        
        return warnings


class MonitorController:
    """Controlador de monitoreo del sistema"""
    
    def __init__(self):
        self.history_max_points = 300  # 5 minutos de historial a 1 segundo
        self.cpu_temp_history = []
        self.gpu_temp_history = []
        self.cpu_rpm_history = []
        self.gpu_rpm_history = []
        self.cpu_usage_history = []
        self.gpu_usage_history = []
        self.memory_usage_history = []
        self.time_history = []
        self.start_time = time.time()
        self.config_manager = None  # Se asignará después
        
    def read_cpu_temps(self):
        """Lee las temperaturas del CPU (package + cores)"""
        cpu_temps = {}
        try:
            # Usar las rutas detectadas automáticamente
            temp_files = sorted(CPU_HWMON.glob("temp*_input")) if CPU_HWMON else []
            
            for i, temp_file in enumerate(temp_files):
                try:
                    with open(temp_file, 'r') as f:
                        temp_millidegrees = int(f.read().strip())
                        temp_celsius = temp_millidegrees / 1000.0
                    
                    if i == 0:
                        cpu_temps['package'] = temp_celsius
                    else:
                        cpu_temps[f'core_{i-1}'] = temp_celsius
                except:
                    continue
            
            # Si no se encontraron temperaturas con el método automático, intentar fallback
            if not cpu_temps:
                for temp_path in TEMP_PATHS:
                    if temp_path.exists():
                        try:
                            with open(temp_path, 'r') as f:
                                temp_millidegrees = int(f.read().strip())
                                temp_celsius = temp_millidegrees / 1000.0
                                if 15 <= temp_celsius <= 120:  # Validar rango de temperatura
                                    cpu_temps[f'temp_{len(cpu_temps)}'] = temp_celsius
                        except:
                            continue
                
        except Exception as e:
            print(f"Error leyendo temperaturas CPU: {e}")
        
        return cpu_temps
    
    def read_gpu_temp(self):
        """Lee la temperatura de la GPU"""
        gpu_temp = None
        
        # Intentar leer desde nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_val = float(result.stdout.strip().split('\n')[0].strip())
                if 15 <= gpu_val <= 120:
                    gpu_temp = gpu_val
        except:
            pass
        
        # GPU alternativa: sysfs
        if gpu_temp is None:
            for pattern in GPU_TEMP_PATHS:
                for path in glob.glob(str(pattern)):
                    try:
                        with open(path, 'r') as f:
                            raw = f.read().strip()
                        if raw:
                            temp_c = int(raw) / 1000.0
                            if 15 <= temp_c <= 120:
                                gpu_temp = temp_c
                                break
                    except:
                        pass
        
        return gpu_temp
    
    def read_rpm(self):
        """Lee las RPM actuales"""
        try:
            cpu_rpm = int(CPU_RPM.read_text().strip()) if CPU_RPM.exists() else 0
            gpu_rpm = int(GPU_RPM.read_text().strip()) if GPU_RPM.exists() else 0
            return cpu_rpm, gpu_rpm
        except:
            return 0, 0
    
    def update_history(self, cpu_temps, gpu_temp, cpu_rpm, gpu_rpm, cpu_usage=0, gpu_usage=0, memory_usage=0):
        """Actualiza el historial de datos"""
        current_time = time.time() - self.start_time
        
        # Obtener temperatura promedio del CPU
        if cpu_temps:
            temps = list(cpu_temps.values())
            avg_cpu_temp = sum(temps) / len(temps)
        else:
            avg_cpu_temp = 0
        
        # Agregar al historial
        self.cpu_temp_history.append(avg_cpu_temp)
        self.gpu_temp_history.append(gpu_temp if gpu_temp else 0)
        self.cpu_rpm_history.append(cpu_rpm)
        self.gpu_rpm_history.append(gpu_rpm)
        self.cpu_usage_history.append(cpu_usage)
        self.gpu_usage_history.append(gpu_usage)
        self.memory_usage_history.append(memory_usage)
        self.time_history.append(current_time)
        
        # Mantener tamaño máximo del historial
        if len(self.time_history) > self.history_max_points:
            self.cpu_temp_history.pop(0)
            self.gpu_temp_history.pop(0)
            self.cpu_rpm_history.pop(0)
            self.gpu_rpm_history.pop(0)
            self.cpu_usage_history.pop(0)
            self.gpu_usage_history.pop(0)
            self.memory_usage_history.pop(0)
            self.time_history.pop(0)
    
    def get_stats(self):
        """Calcula estadísticas del historial"""
        if not self.cpu_temp_history:
            return None
        
        def calc_stats(data):
            if not data:
                return {'min': 0, 'max': 0, 'avg': 0}
            return {
                'min': min(data),
                'max': max(data),
                'avg': sum(data) / len(data)
            }
        
        return {
            'cpu_temp': calc_stats(self.cpu_temp_history),
            'gpu_temp': calc_stats(self.gpu_temp_history),
            'cpu_rpm': calc_stats(self.cpu_rpm_history),
            'gpu_rpm': calc_stats(self.gpu_rpm_history)
        }


class ConfigManager:
    """Gestiona la configuración del programa"""
    
    DEFAULT_CONFIG = {
        "start_minimized": True,
        "auto_start": True,
        "check_interval": 1,  # segundos
        "history_duration": 300,  # segundos (5 minutos)
        
        # Alertas de temperatura
        "alerts_enabled": True,
        "cpu_warning_threshold": 75,  # °C
        "cpu_critical_threshold": 85,  # °C
        "gpu_warning_threshold": 80,  # °C
        "gpu_critical_threshold": 90,  # °C
        
        # Exportación de datos
        "export_enabled": False,
        "export_path": str(Path.home() / "omen_monitor_logs"),
        "export_format": "csv",  # csv, json
        "export_interval": 60,  # segundos
        
        # Dashboard
        "show_stats": True,
        "show_history": True,
        "theme": "dark",  # dark, light
    }
    
    def __init__(self):
        self.config_file = CONFIG_FILE
        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()
    
    def load_config(self):
        """Carga la configuración desde archivo"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
            except Exception as e:
                print(f"Error loading config: {e}")
    
    def save_config(self):
        """Guarda la configuración en archivo"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False


class AlertManager:
    """Gestiona las alertas de temperatura"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.last_alert_time = {}
        self.alert_cooldown = 30  # segundos entre alertas del mismo tipo
    
    def check_alerts(self, cpu_temps, gpu_temp):
        """Verifica si hay alertas de temperatura"""
        alerts = []
        current_time = time.time()
        
        # Verificar temperatura CPU
        if cpu_temps:
            avg_cpu_temp = sum(cpu_temps.values()) / len(cpu_temps)
            config = self.config_manager.config
            
            # Alerta crítica CPU
            if avg_cpu_temp >= config["cpu_critical_threshold"]:
                alert_key = "cpu_critical"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'critical',
                        'source': 'CPU',
                        'value': avg_cpu_temp,
                        'threshold': config["cpu_critical_threshold"],
                        'message': f'¡TEMPERATURA CPU CRÍTICA! {avg_cpu_temp:.1f}°C (umbral: {config["cpu_critical_threshold"]}°C)'
                    })
                    self.last_alert_time[alert_key] = current_time
            
            # Alerta advertencia CPU
            elif avg_cpu_temp >= config["cpu_warning_threshold"]:
                alert_key = "cpu_warning"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'warning',
                        'source': 'CPU',
                        'value': avg_cpu_temp,
                        'threshold': config["cpu_warning_threshold"],
                        'message': f'Temperatura CPU alta: {avg_cpu_temp:.1f}°C (umbral: {config["cpu_warning_threshold"]}°C)'
                    })
                    self.last_alert_time[alert_key] = current_time
        
        # Verificar temperatura GPU
        if gpu_temp:
            config = self.config_manager.config
            
            # Alerta crítica GPU
            if gpu_temp >= config["gpu_critical_threshold"]:
                alert_key = "gpu_critical"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'critical',
                        'source': 'GPU',
                        'value': gpu_temp,
                        'threshold': config["gpu_critical_threshold"],
                        'message': f'¡TEMPERATURA GPU CRÍTICA! {gpu_temp:.1f}°C (umbral: {config["gpu_critical_threshold"]}°C)'
                    })
                    self.last_alert_time[alert_key] = current_time
            
            # Alerta advertencia GPU
            elif gpu_temp >= config["gpu_warning_threshold"]:
                alert_key = "gpu_warning"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'warning',
                        'source': 'GPU',
                        'value': gpu_temp,
                        'threshold': config["gpu_warning_threshold"],
                        'message': f'Temperatura GPU alta: {gpu_temp:.1f}°C (umbral: {config["gpu_warning_threshold"]}°C)'
                    })
                    self.last_alert_time[alert_key] = current_time
        
        return alerts


class DataExporter:
    """Exporta datos del monitoreo a archivos"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.current_csv_file = None
        self.csv_writer = None
        self.last_export_time = 0
    
    def start_export(self):
        """Inicia la exportación de datos"""
        if not self.config_manager.config["export_enabled"]:
            return False
        
        try:
            export_path = Path(self.config_manager.config["export_path"])
            export_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if self.config_manager.config["export_format"] == "csv":
                self.current_csv_file = export_path / f"omen_monitor_{timestamp}.csv"
                self.csv_writer = None
            else:
                self.current_csv_file = export_path / f"omen_monitor_{timestamp}.json"
            
            return True
        except Exception as e:
            print(f"Error iniciando exportación: {e}")
            return False
    
    def export_data(self, cpu_temps, gpu_temp, cpu_rpm, gpu_rpm):
        """Exporta datos actuales"""
        if not self.config_manager.config["export_enabled"]:
            return
        
        current_time = time.time()
        if current_time - self.last_export_time < self.config_manager.config["export_interval"]:
            return
        
        self.last_export_time = current_time
        
        try:
            timestamp = datetime.now().isoformat()
            
            if self.config_manager.config["export_format"] == "csv":
                if not self.current_csv_file or not self.current_csv_file.exists():
                    self.start_export()
                
                if self.current_csv_file:
                    mode = 'a' if self.current_csv_file.exists() else 'w'
                    with open(self.current_csv_file, mode, newline='') as f:
                        writer = csv.writer(f)
                        if mode == 'w':
                            writer.writerow(['timestamp', 'cpu_package', 'cpu_cores', 'gpu_temp', 'cpu_rpm', 'gpu_rpm'])
                        
                        cpu_package = cpu_temps.get('package', 0) if cpu_temps else 0
                        cpu_cores = json.dumps({k: v for k, v in cpu_temps.items() if k != 'package'}) if cpu_temps else '{}'
                        
                        writer.writerow([
                            timestamp,
                            f"{cpu_package:.2f}",
                            cpu_cores,
                            f"{gpu_temp:.2f}" if gpu_temp else 'N/A',
                            cpu_rpm,
                            gpu_rpm
                        ])
            
            elif self.config_manager.config["export_format"] == "json":
                if not self.current_csv_file or not self.current_csv_file.exists():
                    self.start_export()
                
                if self.current_csv_file:
                    data = {
                        'timestamp': timestamp,
                        'cpu_temps': cpu_temps,
                        'gpu_temp': gpu_temp,
                        'cpu_rpm': cpu_rpm,
                        'gpu_rpm': gpu_rpm
                    }
                    
                    mode = 'a' if self.current_csv_file.exists() else 'w'
                    with open(self.current_csv_file, mode) as f:
                        if mode == 'w':
                            f.write('[\n')
                        else:
                            f.write(',\n')
                        f.write(json.dumps(data, indent=2))
        
        except Exception as e:
            print(f"Error exportando datos: {e}")


class SystemUsageMonitor:
    """Monitorea uso de CPU y GPU"""
    
    def __init__(self):
        self.prev_idle = None
        self.prev_total = None
    
    def read_cpu_usage(self):
        """Lee el uso actual de CPU"""
        try:
            with open('/proc/stat', 'r') as f:
                lines = f.readlines()
            
            cpu_line = lines[0].split()
            idle = int(cpu_line[4])
            total = sum(int(x) for x in cpu_line[1:8])
            
            if self.prev_idle is not None and self.prev_total is not None:
                idle_diff = idle - self.prev_idle
                total_diff = total - self.prev_total
                if total_diff > 0:
                    usage = (1.0 - idle_diff / total_diff) * 100
                else:
                    usage = 0
            else:
                usage = 0
            
            self.prev_idle = idle
            self.prev_total = total
            return usage
        except Exception as e:
            print(f"Error leyendo uso CPU: {e}")
            return 0
    
    def read_gpu_usage(self):
        """Lee el uso actual de GPU"""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as e:
            print(f"Error leyendo uso GPU: {e}")
        return 0
    
    def read_memory_usage(self):
        """Lee el uso de memoria"""
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = dict((i.split()[0].rstrip(':'), int(i.split()[1])) 
                              for i in f.readlines())
            
            total = meminfo['MemTotal']
            available = meminfo['MemAvailable']
            used = total - available
            return (used / total) * 100
        except Exception as e:
            print(f"Error leyendo uso memoria: {e}")
            return 0


class TrendAnalyzer:
    """Analiza tendencias de temperatura"""
    
    def __init__(self, controller):
        self.controller = controller
    
    def predict_temperature(self, temp_history, seconds_ahead=60):
        """Predice temperatura futura basada en tendencia"""
        if len(temp_history) < 10 or not NUMPY_AVAILABLE:
            return None
        
        try:
            times = np.array(range(len(temp_history)))
            temps = np.array(temp_history)
            
            # Ajustar línea de tendencia
            slope, intercept = np.polyfit(times, temps, 1)
            
            # Predecir temperatura futura
            future_temp = slope * (len(temp_history) + seconds_ahead) + intercept
            return future_temp
        except Exception as e:
            print(f"Error prediciendo temperatura: {e}")
            return None
    
    def check_rising_trend(self, temp_history, threshold=0.5):
        """Verifica si la temperatura está aumentando consistentemente"""
        if len(temp_history) < 5:
            return False
        
        recent = temp_history[-5:]
        return all(recent[i] < recent[i+1] for i in range(len(recent)-1))
    
    def get_time_to_threshold(self, temp_history, threshold):
        """Calcula tiempo estimado para alcanzar umbral de temperatura"""
        if len(temp_history) < 10 or not NUMPY_AVAILABLE:
            return None
        
        try:
            times = np.array(range(len(temp_history)))
            temps = np.array(temp_history)
            slope, _ = np.polyfit(times, temps, 1)
            
            if slope > 0:
                current_temp = temps[-1]
                if current_temp < threshold:
                    seconds_to_threshold = (threshold - current_temp) / slope
                    return max(0, int(seconds_to_threshold))
        except Exception as e:
            print(f"Error calculando tiempo a umbral: {e}")
        
        return None


class AdvancedAlertManager:
    """Alertas con acciones de software"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.last_alert_time = {}
        self.alert_cooldown = 30
    
    def check_alerts(self, cpu_temps, gpu_temp, cpu_usage, gpu_usage):
        """Verifica alertas con múltiples factores"""
        alerts = []
        current_time = time.time()
        config = self.config_manager.config
        
        # Alerta de CPU: temperatura alta + uso alto
        if cpu_temps:
            avg_cpu_temp = sum(cpu_temps.values()) / len(cpu_temps)
            if avg_cpu_temp >= config["cpu_critical_threshold"] and cpu_usage > 80:
                alert_key = "cpu_critical_overload"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'critical',
                        'source': 'CPU',
                        'message': f'¡SOBRECARGA CPU! {avg_cpu_temp:.1f}°C al {cpu_usage:.0f}% uso',
                        'action': 'reduce_performance'
                    })
                    self.last_alert_time[alert_key] = current_time
            
            # Alerta advertencia CPU
            elif avg_cpu_temp >= config["cpu_warning_threshold"]:
                alert_key = "cpu_warning"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'warning',
                        'source': 'CPU',
                        'message': f'Temperatura CPU alta: {avg_cpu_temp:.1f}°C al {cpu_usage:.0f}% uso',
                        'action': None
                    })
                    self.last_alert_time[alert_key] = current_time
        
        # Alerta de GPU: temperatura alta + uso alto
        if gpu_temp:
            if gpu_temp >= config["gpu_critical_threshold"] and gpu_usage > 90:
                alert_key = "gpu_critical_overload"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'critical',
                        'source': 'GPU',
                        'message': f'¡SOBRECARGA GPU! {gpu_temp:.1f}°C al {gpu_usage:.0f}% uso',
                        'action': 'reduce_gpu_power'
                    })
                    self.last_alert_time[alert_key] = current_time
            
            # Alerta advertencia GPU
            elif gpu_temp >= config["gpu_warning_threshold"]:
                alert_key = "gpu_warning"
                if current_time - self.last_alert_time.get(alert_key, 0) > self.alert_cooldown:
                    alerts.append({
                        'type': 'warning',
                        'source': 'GPU',
                        'message': f'Temperatura GPU alta: {gpu_temp:.1f}°C al {gpu_usage:.0f}% uso',
                        'action': None
                    })
                    self.last_alert_time[alert_key] = current_time
        
        return alerts
    
    def execute_alert_action(self, action):
        """Ejecuta acción de alerta (sin control de fans)"""
        if action == 'reduce_performance':
            # Reducir frecuencia de CPU
            subprocess.run(["cpupower", "frequency-set", "-u", "2.4GHz"], check=False)
            print("Acción ejecutada: Reducir rendimiento CPU")
        
        elif action == 'reduce_gpu_power':
            # Limitar potencia de GPU
            subprocess.run(["nvidia-smi", "-pl", "50"], check=False)
            print("Acción ejecutada: Reducir potencia GPU")


class TurboBoostController:
    """Controlador de Intel Turbo Boost"""
    
    def __init__(self):
        self.no_turbo_path = NO_TURBO_PATH
        self.current_state = None
    
    def is_available(self):
        """Verifica si el control de Turbo Boost está disponible"""
        return self.no_turbo_path.exists()
    
    def get_current_state(self):
        """Lee el estado actual de Turbo Boost"""
        if not self.is_available():
            return None
        
        try:
            with open(self.no_turbo_path, 'r') as f:
                value = int(f.read().strip())
            return value  # 0 = Turbo Boost activo, 1 = Turbo Boost desactivado
        except Exception as e:
            print(f"Error leyendo estado Turbo Boost: {e}")
            return None
    
    def set_turbo_boost(self, enable=True):
        """Activa o desactiva Turbo Boost"""
        if not self.is_available():
            print("Intel Turbo Boost no está disponible en este sistema")
            return False
        
        try:
            # enable=True → no_turbo=0 (activar Turbo Boost)
            # enable=False → no_turbo=1 (desactivar Turbo Boost)
            value = 0 if enable else 1
            
            # Intentar usar pkexec para solicitud gráfica de contraseña
            try:
                result = subprocess.run(
                    ["pkexec", "sh", "-c", f"echo {value} | tee {self.no_turbo_path}"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    self.current_state = value
                    state_str = "activado" if enable else "desactivado"
                    print(f"Turbo Boost {state_str} correctamente (via pkexec)")
                    return True
                else:
                    print(f"pkexec falló, intentando método alternativo: {result.stderr}")
                    raise Exception("pkexec failed")
                    
            except Exception as pkexec_error:
                # Fallback a sudo si pkexec no está disponible
                print(f"pkexec no disponible: {pkexec_error}")
                result = subprocess.run(
                    ["sudo", "tee", str(self.no_turbo_path)],
                    input=str(value),
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    self.current_state = value
                    state_str = "activado" if enable else "desactivado"
                    print(f"Turbo Boost {state_str} correctamente (requirió contraseña manual)")
                    return True
                else:
                    print(f"Error cambiando Turbo Boost: {result.stderr}")
                    return False
                
        except Exception as e:
            print(f"Error cambiando Turbo Boost: {e}")
            return False
    
    def disable_turbo_boost(self):
        """Desactiva Turbo Boost (noboosts)"""
        return self.set_turbo_boost(enable=False)
    
    def enable_turbo_boost(self):
        """Activa Turbo Boost (boost)"""
        return self.set_turbo_boost(enable=True)


class AdvancedDataExporter:
    """Exportación avanzada con más metadatos"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.current_csv_file = None
        self.csv_writer = None
        self.last_export_time = 0
    
    def start_export(self):
        """Inicia la exportación de datos"""
        if not self.config_manager.config["export_enabled"]:
            return False
        
        try:
            export_path = Path(self.config_manager.config["export_path"])
            export_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if self.config_manager.config["export_format"] == "csv":
                self.current_csv_file = export_path / f"omen_monitor_enhanced_{timestamp}.csv"
                self.csv_writer = None
            else:
                self.current_csv_file = export_path / f"omen_monitor_enhanced_{timestamp}.json"
            
            return True
        except Exception as e:
            print(f"Error iniciando exportación: {e}")
            return False
    
    def export_enhanced_data(self, cpu_temps, gpu_temp, cpu_rpm, gpu_rpm, 
                            cpu_usage, gpu_usage, memory_usage):
        """Exporta datos enriquecidos"""
        if not self.config_manager.config["export_enabled"]:
            return
        
        current_time = time.time()
        if current_time - self.last_export_time < self.config_manager.config["export_interval"]:
            return
        
        self.last_export_time = current_time
        
        try:
            timestamp = datetime.now().isoformat()
            
            enhanced_data = {
                'timestamp': timestamp,
                'cpu': {
                    'temperatures': cpu_temps,
                    'rpm': cpu_rpm,
                    'usage_percent': cpu_usage
                },
                'gpu': {
                    'temperature': gpu_temp,
                    'rpm': gpu_rpm,
                    'usage_percent': gpu_usage
                },
                'memory': {
                    'usage_percent': memory_usage
                },
                'system': {
                    'load_avg': os.getloadavg(),
                    'uptime': self.get_uptime()
                }
            }
            
            if self.config_manager.config["export_format"] == "json":
                self.export_json(enhanced_data)
            else:
                self.export_csv(enhanced_data)
                
        except Exception as e:
            print(f"Error exportando datos enriquecidos: {e}")
    
    def export_json(self, data):
        """Exporta datos en formato JSON"""
        if not self.current_csv_file or not self.current_csv_file.exists():
            self.start_export()
        
        if self.current_csv_file:
            mode = 'a' if self.current_csv_file.exists() else 'w'
            with open(self.current_csv_file, mode) as f:
                if mode == 'w':
                    f.write('[\n')
                else:
                    f.write(',\n')
                f.write(json.dumps(data, indent=2))
    
    def export_csv(self, data):
        """Exporta datos en formato CSV"""
        if not self.current_csv_file or not self.current_csv_file.exists():
            self.start_export()
        
        if self.current_csv_file:
            mode = 'a' if self.current_csv_file.exists() else 'w'
            with open(self.current_csv_file, mode, newline='') as f:
                writer = csv.writer(f)
                if mode == 'w':
                    writer.writerow([
                        'timestamp', 'cpu_package_temp', 'cpu_usage', 'cpu_rpm',
                        'gpu_temp', 'gpu_usage', 'gpu_rpm', 'memory_usage', 'load_avg'
                    ])
                
                cpu_package = data['cpu']['temperatures'].get('package', 0) if data['cpu']['temperatures'] else 0
                
                writer.writerow([
                    data['timestamp'],
                    f"{cpu_package:.2f}",
                    f"{data['cpu']['usage_percent']:.1f}",
                    data['cpu']['rpm'],
                    f"{data['gpu']['temperature']:.2f}" if data['gpu']['temperature'] else 'N/A',
                    f"{data['gpu']['usage_percent']:.1f}",
                    data['gpu']['rpm'],
                    f"{data['memory']['usage_percent']:.1f}",
                    f"{data['system']['load_avg'][0]:.2f}"
                ])
    
    def get_uptime(self):
        """Obtiene tiempo de actividad del sistema"""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
            return uptime_seconds
        except:
            return 0


class StatusSignals(QObject):
    """Señales para comunicación entre hilos"""
    update_status = pyqtSignal(dict)  # Diccionario con todos los datos
    alert_triggered = pyqtSignal(dict)  # Alerta de temperatura


class DashboardDialog(QDialog):
    """Diálogo de dashboard de monitoreo"""
    
    def __init__(self, current_data, config_manager, parent=None):
        super().__init__(parent)
        self.current_data = current_data
        self.config_manager = config_manager
        self.setup_ui()
        self.update_dashboard()
    
    def setup_ui(self):
        self.setWindowTitle("HP Omen Monitor - Dashboard")
        self.setMinimumWidth(600)
        
        layout = QVBoxLayout()
        
        # Información actual
        current_group = QGroupBox("Estado Actual")
        current_layout = QVBoxLayout()
        
        self.cpu_temp_label = QLabel("CPU Temp: --")
        self.gpu_temp_label = QLabel("GPU Temp: --")
        self.cpu_rpm_label = QLabel("CPU RPM: --")
        self.gpu_rpm_label = QLabel("GPU RPM: --")
        self.cpu_usage_label = QLabel("CPU Usage: --")
        self.gpu_usage_label = QLabel("GPU Usage: --")
        self.memory_usage_label = QLabel("Memory Usage: --")
        
        current_layout.addWidget(self.cpu_temp_label)
        current_layout.addWidget(self.gpu_temp_label)
        current_layout.addWidget(self.cpu_rpm_label)
        current_layout.addWidget(self.gpu_rpm_label)
        current_layout.addWidget(self.cpu_usage_label)
        current_layout.addWidget(self.gpu_usage_label)
        current_layout.addWidget(self.memory_usage_label)
        
        current_group.setLayout(current_layout)
        layout.addWidget(current_group)
        
        # Estadísticas
        if self.config_manager.config["show_stats"] and self.current_data.get('stats'):
            stats_group = QGroupBox("Estadísticas (Últimos 5 minutos)")
            stats_layout = QVBoxLayout()
            
            stats = self.current_data['stats']
            self.stats_label = QLabel(
                f"CPU Temp: Min {stats['cpu_temp']['min']:.1f}°C | "
                f"Max {stats['cpu_temp']['max']:.1f}°C | "
                f"Avg {stats['cpu_temp']['avg']:.1f}°C\n"
                f"GPU Temp: Min {stats['gpu_temp']['min']:.1f}°C | "
                f"Max {stats['gpu_temp']['max']:.1f}°C | "
                f"Avg {stats['gpu_temp']['avg']:.1f}°C\n"
                f"CPU RPM: Min {stats['cpu_rpm']['min']} | "
                f"Max {stats['cpu_rpm']['max']} | "
                f"Avg {stats['cpu_rpm']['avg']:.0f}\n"
                f"GPU RPM: Min {stats['gpu_rpm']['min']} | "
                f"Max {stats['gpu_rpm']['max']} | "
                f"Avg {stats['gpu_rpm']['avg']:.0f}"
            )
            
            stats_layout.addWidget(self.stats_label)
            stats_group.setLayout(stats_layout)
            layout.addWidget(stats_group)
        
        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def update_dashboard(self):
        """Actualiza el dashboard con datos actuales"""
        cpu_temps = self.current_data.get('cpu_temps', {})
        gpu_temp = self.current_data.get('gpu_temp')
        cpu_rpm = self.current_data.get('cpu_rpm', 0)
        gpu_rpm = self.current_data.get('gpu_rpm', 0)
        cpu_usage = self.current_data.get('cpu_usage', 0)
        gpu_usage = self.current_data.get('gpu_usage', 0)
        memory_usage = self.current_data.get('memory_usage', 0)
        
        if cpu_temps:
            avg_cpu_temp = sum(cpu_temps.values()) / len(cpu_temps)
            self.cpu_temp_label.setText(f"CPU Temp: {avg_cpu_temp:.1f}°C")
            
            # Mostrar cores individuales
            for core, temp in cpu_temps.items():
                if core != 'package':
                    self.cpu_temp_label.setText(f"{self.cpu_temp_label.text()}\n  {core.upper()}: {temp:.1f}°C")
        else:
            self.cpu_temp_label.setText("CPU Temp: N/A")
        
        self.gpu_temp_label.setText(f"GPU Temp: {gpu_temp:.1f}°C" if gpu_temp else "GPU Temp: N/A")
        self.cpu_rpm_label.setText(f"CPU RPM: {cpu_rpm}")
        self.gpu_rpm_label.setText(f"GPU RPM: {gpu_rpm}")
        self.cpu_usage_label.setText(f"CPU Usage: {cpu_usage:.1f}%")
        self.gpu_usage_label.setText(f"GPU Usage: {gpu_usage:.1f}%" if gpu_usage > 0 else "GPU Usage: N/A")
        self.memory_usage_label.setText(f"Memory Usage: {memory_usage:.1f}%")


class RealTimeChartsDialog(QDialog):
    """Gráficos en tiempo real con matplotlib"""
    
    def __init__(self, controller, config_manager, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config_manager = config_manager
        self.paused = False
        self.setup_ui()
        self.setup_charts()
        
        # Timer para actualización
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_charts)
        self.timer.start(1000)  # Actualizar cada segundo
    
    def setup_ui(self):
        self.setWindowTitle("Gráficos en Tiempo Real")
        self.setMinimumSize(900, 600)
        
        layout = QVBoxLayout()
        
        if MATPLOTLIB_AVAILABLE:
            # Crear figura matplotlib
            self.figure = Figure(figsize=(10, 8))
            self.canvas = FigureCanvasQTAgg(self.figure)
            layout.addWidget(self.canvas)
            
            # Botones de control
            btn_layout = QHBoxLayout()
            
            self.pause_btn = QPushButton("Pausar")
            self.pause_btn.clicked.connect(self.toggle_pause)
            btn_layout.addWidget(self.pause_btn)
            
            refresh_btn = QPushButton("Actualizar Ahora")
            refresh_btn.clicked.connect(self.force_update)
            btn_layout.addWidget(refresh_btn)
            
            layout.addLayout(btn_layout)
        else:
            # Fallback a versión texto si matplotlib no está disponible
            warning_label = QLabel("matplotlib no disponible - usando versión texto")
            warning_label.setStyleSheet("color: orange; font-weight: bold;")
            layout.addWidget(warning_label)
            
            self.temp_history_text = QTextEdit()
            self.temp_history_text.setReadOnly(True)
            self.temp_history_text.setMaximumHeight(200)
            layout.addWidget(self.temp_history_text)
            
            self.rpm_history_text = QTextEdit()
            self.rpm_history_text.setReadOnly(True)
            self.rpm_history_text.setMaximumHeight(200)
            layout.addWidget(self.rpm_history_text)
        
        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close_dialog)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def setup_charts(self):
        """Configura los gráficos iniciales"""
        if not MATPLOTLIB_AVAILABLE:
            return
        
        self.figure.clear()
        
        # Gráfico de temperaturas
        self.ax_temp = self.figure.add_subplot(311)
        self.ax_temp.set_title("Temperaturas")
        self.ax_temp.set_ylabel("°C")
        self.ax_temp.grid(True, alpha=0.3)
        
        # Gráfico de RPM
        self.ax_rpm = self.figure.add_subplot(312)
        self.ax_rpm.set_title("Velocidad de Ventiladores")
        self.ax_rpm.set_ylabel("RPM")
        self.ax_rpm.grid(True, alpha=0.3)
        
        # Gráfico de uso
        self.ax_usage = self.figure.add_subplot(313)
        self.ax_usage.set_title("Uso de CPU/GPU")
        self.ax_usage.set_ylabel("%")
        self.ax_usage.set_xlabel("Tiempo (s)")
        self.ax_usage.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
    
    def update_charts(self):
        """Actualiza los gráficos con datos actuales"""
        if self.paused or not self.controller.time_history:
            return
        
        if not MATPLOTLIB_AVAILABLE:
            self.update_text_version()
            return
        
        if len(self.controller.time_history) < 2:
            return
        
        # Actualizar temperaturas
        self.ax_temp.clear()
        self.ax_temp.set_title("Temperaturas")
        self.ax_temp.set_ylabel("°C")
        self.ax_temp.grid(True, alpha=0.3)
        
        if self.controller.cpu_temp_history and self.controller.gpu_temp_history:
            self.ax_temp.plot(self.controller.time_history, 
                             self.controller.cpu_temp_history, 'r-', label='CPU', linewidth=2)
            self.ax_temp.plot(self.controller.time_history, 
                             self.controller.gpu_temp_history, 'b-', label='GPU', linewidth=2)
            
            # Mostrar valores actuales en el título
            current_cpu = self.controller.cpu_temp_history[-1]
            current_gpu = self.controller.gpu_temp_history[-1]
            self.ax_temp.set_title(f"Temperaturas - CPU: {current_cpu:.1f}°C | GPU: {current_gpu:.1f}°C")
            
            self.ax_temp.legend()
        else:
            self.ax_temp.text(0.5, 0.5, 'No hay datos de temperatura', 
                           transform=self.ax_temp.transAxes, ha='center', va='center')
        
        # Agregar líneas de alerta
        config = self.config_manager.config
        self.ax_temp.axhline(y=config["cpu_warning_threshold"], color='orange', 
                           linestyle='--', alpha=0.5, label='Alerta CPU')
        self.ax_temp.axhline(y=config["cpu_critical_threshold"], color='red', 
                           linestyle='--', alpha=0.5, label='Crítico CPU')
        self.ax_temp.axhline(y=config["gpu_warning_threshold"], color='purple', 
                           linestyle=':', alpha=0.5, label='Alerta GPU')
        
        # Actualizar RPM
        self.ax_rpm.clear()
        self.ax_rpm.set_title("Velocidad de Ventiladores")
        self.ax_rpm.set_ylabel("RPM")
        self.ax_rpm.grid(True, alpha=0.3)
        
        # Verificar si hay datos de RPM
        if self.controller.cpu_rpm_history and self.controller.gpu_rpm_history:
            # Graficar RPM con puntos para mejor visibilidad
            self.ax_rpm.plot(self.controller.time_history, 
                            self.controller.cpu_rpm_history, 'r--', label='CPU RPM', linewidth=2, marker='o', markersize=3)
            self.ax_rpm.plot(self.controller.time_history, 
                            self.controller.gpu_rpm_history, 'b--', label='GPU RPM', linewidth=2, marker='s', markersize=3)
            
            # Mostrar valores actuales en el título
            current_cpu_rpm = self.controller.cpu_rpm_history[-1]
            current_gpu_rpm = self.controller.gpu_rpm_history[-1]
            self.ax_rpm.set_title(f"Ventiladores - CPU: {current_cpu_rpm} RPM | GPU: {current_gpu_rpm} RPM")
            
            # Ajustar escala del eje Y para mostrar mejor las variaciones
            all_rpm = self.controller.cpu_rpm_history + self.controller.gpu_rpm_history
            if all_rpm:
                min_rpm = min(all_rpm)
                max_rpm = max(all_rpm)
                if max_rpm > min_rpm:
                    # Añadir margen del 10%
                    margin = (max_rpm - min_rpm) * 0.1
                    self.ax_rpm.set_ylim(max(0, min_rpm - margin), max_rpm + margin)
                else:
                    # Si todos los valores son iguales, mostrar escala fija
                    self.ax_rpm.set_ylim(0, max_rpm * 1.2)
            
            self.ax_rpm.legend()
        else:
            self.ax_rpm.text(0.5, 0.5, 'No hay datos de RPM', 
                           transform=self.ax_rpm.transAxes, ha='center', va='center')
        
        # Actualizar uso (si hay datos)
        if hasattr(self.controller, 'cpu_usage_history') and hasattr(self.controller, 'gpu_usage_history'):
            self.ax_usage.clear()
            self.ax_usage.set_title("Uso de CPU/GPU")
            self.ax_usage.set_ylabel("%")
            self.ax_usage.set_xlabel("Tiempo (s)")
            self.ax_usage.grid(True, alpha=0.3)
            
            # Asegurar que los arrays tengan el mismo tamaño
            min_len = min(len(self.controller.time_history), 
                         len(self.controller.cpu_usage_history),
                         len(self.controller.gpu_usage_history))
            
            if min_len > 0:
                self.ax_usage.plot(self.controller.time_history[:min_len], 
                                 self.controller.cpu_usage_history[:min_len], 
                                 'r-', label='CPU %', linewidth=2, marker='o', markersize=3)
                self.ax_usage.plot(self.controller.time_history[:min_len], 
                                 self.controller.gpu_usage_history[:min_len], 
                                 'b-', label='GPU %', linewidth=2, marker='s', markersize=3)
                
                # Mostrar valores actuales en el título
                current_cpu_usage = self.controller.cpu_usage_history[min_len-1]
                current_gpu_usage = self.controller.gpu_usage_history[min_len-1]
                self.ax_usage.set_title(f"Uso de CPU/GPU - CPU: {current_cpu_usage:.1f}% | GPU: {current_gpu_usage:.1f}%")
                
                self.ax_usage.legend()
            else:
                self.ax_usage.text(0.5, 0.5, 'No hay datos de uso', 
                                 transform=self.ax_usage.transAxes, ha='center', va='center')
        
        self.figure.tight_layout()
        self.canvas.draw()
    
    def update_text_version(self):
        """Versión texto cuando matplotlib no está disponible"""
        # Historial de temperaturas
        temp_text = "Tiempo | CPU Temp | GPU Temp\n"
        temp_text += "-" * 40 + "\n"
        
        for i, time_point in enumerate(self.controller.time_history):
            cpu_temp = self.controller.cpu_temp_history[i]
            gpu_temp = self.controller.gpu_temp_history[i]
            temp_text += f"{time_point:.1f}s | {cpu_temp:.1f}°C | {gpu_temp:.1f}°C\n"
        
        self.temp_history_text.setText(temp_text)
        
        # Historial de RPM
        rpm_text = "Tiempo | CPU RPM | GPU RPM\n"
        rpm_text += "-" * 40 + "\n"
        
        for i, time_point in enumerate(self.controller.time_history):
            cpu_rpm = self.controller.cpu_rpm_history[i]
            gpu_rpm = self.controller.gpu_rpm_history[i]
            rpm_text += f"{time_point:.1f}s | {cpu_rpm} | {gpu_rpm}\n"
        
        self.rpm_history_text.setText(rpm_text)
    
    def toggle_pause(self):
        """Alterna la pausa de actualización"""
        self.paused = not self.paused
        self.pause_btn.setText("Reanudar" if self.paused else "Pausar")
    
    def force_update(self):
        """Fuerza una actualización inmediata"""
        self.paused = False
        self.pause_btn.setText("Pausar")
        self.update_charts()
    
    def close_dialog(self):
        """Cierra el diálogo"""
        self.timer.stop()
        self.accept()


class AdvancedHistoryDialog(QDialog):
    """Historial avanzado con análisis estadístico"""
    
    def __init__(self, controller, config_manager, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config_manager = config_manager
        self.trend_analyzer = TrendAnalyzer(controller)
        self.setup_ui()
        self.update_analysis()
    
    def setup_ui(self):
        self.setWindowTitle("Análisis de Historial")
        self.setMinimumSize(700, 600)
        
        layout = QVBoxLayout()
        
        # Información general
        info_group = QGroupBox("Resumen del Período")
        info_layout = QVBoxLayout()
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        info_layout.addWidget(self.summary_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Análisis de tendencias
        trend_group = QGroupBox("Análisis de Tendencias")
        trend_layout = QVBoxLayout()
        self.trend_label = QLabel()
        self.trend_label.setWordWrap(True)
        trend_layout.addWidget(self.trend_label)
        trend_group.setLayout(trend_layout)
        layout.addWidget(trend_group)
        
        # Predicciones
        prediction_group = QGroupBox("Predicciones")
        prediction_layout = QVBoxLayout()
        self.prediction_label = QLabel()
        self.prediction_label.setWordWrap(True)
        prediction_layout.addWidget(self.prediction_label)
        prediction_group.setLayout(prediction_layout)
        layout.addWidget(prediction_group)
        
        # Botón refrescar
        refresh_btn = QPushButton("Actualizar Análisis")
        refresh_btn.clicked.connect(self.update_analysis)
        layout.addWidget(refresh_btn)
        
        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def update_analysis(self):
        """Actualiza el análisis estadístico"""
        stats = self.controller.get_stats()
        if not stats:
            self.summary_label.setText("No hay datos suficientes para análisis.")
            return
        
        # Resumen
        duration = len(self.controller.time_history)
        summary = f"""
<b>Período de análisis:</b> {duration} segundos
<b>Temperatura CPU:</b> Min {stats['cpu_temp']['min']:.1f}°C | Max {stats['cpu_temp']['max']:.1f}°C | Avg {stats['cpu_temp']['avg']:.1f}°C
<b>Temperatura GPU:</b> Min {stats['gpu_temp']['min']:.1f}°C | Max {stats['gpu_temp']['max']:.1f}°C | Avg {stats['gpu_temp']['avg']:.1f}°C
<b>Velocidad CPU:</b> Min {stats['cpu_rpm']['min']} RPM | Max {stats['cpu_rpm']['max']} RPM | Avg {stats['cpu_rpm']['avg']:.0f} RPM
<b>Velocidad GPU:</b> Min {stats['gpu_rpm']['min']} RPM | Max {stats['gpu_rpm']['max']} RPM | Avg {stats['gpu_rpm']['avg']:.0f} RPM
"""
        self.summary_label.setText(summary)
        
        # Análisis de tendencias
        cpu_rising = self.trend_analyzer.check_rising_trend(self.controller.cpu_temp_history)
        gpu_rising = self.trend_analyzer.check_rising_trend(self.controller.gpu_temp_history)
        
        trend_text = f"""
<b>Tendencia CPU:</b> {'📈 Aumentando' if cpu_rising else '📉 Estable/Disminuyendo'}
<b>Tendencia GPU:</b> {'📈 Aumentando' if gpu_rising else '📉 Estable/Disminuyendo'}
"""
        self.trend_label.setText(trend_text)
        
        # Predicciones
        config = self.config_manager.config
        cpu_time_to_warning = self.trend_analyzer.get_time_to_threshold(
            self.controller.cpu_temp_history, config["cpu_warning_threshold"]
        )
        gpu_time_to_warning = self.trend_analyzer.get_time_to_threshold(
            self.controller.gpu_temp_history, config["gpu_warning_threshold"]
        )
        
        prediction_text = ""
        if cpu_time_to_warning is not None:
            prediction_text += f"<b>Tiempo estimado hasta alerta CPU:</b> {cpu_time_to_warning}s si continúa tendencia\n"
        else:
            prediction_text += "<b>Tiempo estimado hasta alerta CPU:</b> No disponible (tendencia estable)\n"
        
        if gpu_time_to_warning is not None:
            prediction_text += f"<b>Tiempo estimado hasta alerta GPU:</b> {gpu_time_to_warning}s si continúa tendencia"
        else:
            prediction_text += "<b>Tiempo estimado hasta alerta GPU:</b> No disponible (tendencia estable)"
        
        self.prediction_label.setText(prediction_text)


class ConfigDialog(QDialog):
    """Diálogo de configuración"""
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Configuración")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # Crear tabs
        tabs = QTabWidget()
        
        # Tab General
        general_tab = QWidget()
        general_layout = QFormLayout()
        
        interval_spin = QSpinBox()
        interval_spin.setRange(1, 60)
        interval_spin.setValue(self.config_manager.config["check_interval"])
        interval_spin.setSuffix(" segundos")
        general_layout.addRow("Intervalo de actualización:", interval_spin)
        
        start_minimized = QCheckBox()
        start_minimized.setChecked(self.config_manager.config["start_minimized"])
        general_layout.addRow("Iniciar minimizado:", start_minimized)
        
        auto_start = QCheckBox()
        auto_start.setChecked(self.config_manager.config["auto_start"])
        general_layout.addRow("Iniciar al arrancar:", auto_start)
        
        general_tab.setLayout(general_layout)
        tabs.addTab(general_tab, "General")
        
        # Tab Alertas
        alerts_tab = QWidget()
        alerts_layout = QFormLayout()
        
        alerts_enabled = QCheckBox()
        alerts_enabled.setChecked(self.config_manager.config["alerts_enabled"])
        alerts_layout.addRow("Habilitar alertas:", alerts_enabled)
        
        cpu_warning_spin = QSpinBox()
        cpu_warning_spin.setRange(50, 100)
        cpu_warning_spin.setValue(self.config_manager.config["cpu_warning_threshold"])
        cpu_warning_spin.setSuffix(" °C")
        alerts_layout.addRow("Umbral advertencia CPU:", cpu_warning_spin)
        
        cpu_critical_spin = QSpinBox()
        cpu_critical_spin.setRange(60, 100)
        cpu_critical_spin.setValue(self.config_manager.config["cpu_critical_threshold"])
        cpu_critical_spin.setSuffix(" °C")
        alerts_layout.addRow("Umbral crítico CPU:", cpu_critical_spin)
        
        gpu_warning_spin = QSpinBox()
        gpu_warning_spin.setRange(50, 100)
        gpu_warning_spin.setValue(self.config_manager.config["gpu_warning_threshold"])
        gpu_warning_spin.setSuffix(" °C")
        alerts_layout.addRow("Umbral advertencia GPU:", gpu_warning_spin)
        
        gpu_critical_spin = QSpinBox()
        gpu_critical_spin.setRange(60, 100)
        gpu_critical_spin.setValue(self.config_manager.config["gpu_critical_threshold"])
        gpu_critical_spin.setSuffix(" °C")
        alerts_layout.addRow("Umbral crítico GPU:", gpu_critical_spin)
        
        alerts_tab.setLayout(alerts_layout)
        tabs.addTab(alerts_tab, "Alertas")
        
        # Tab Exportación
        export_tab = QWidget()
        export_layout = QFormLayout()
        
        export_enabled = QCheckBox()
        export_enabled.setChecked(self.config_manager.config["export_enabled"])
        export_layout.addRow("Habilitar exportación:", export_enabled)
        
        export_path_edit = QLineEdit()
        export_path_edit.setText(self.config_manager.config["export_path"])
        export_layout.addRow("Ruta de exportación:", export_path_edit)
        
        export_format_combo = QComboBox()
        export_format_combo.addItems(["csv", "json"])
        export_format_combo.setCurrentText(self.config_manager.config["export_format"])
        export_layout.addRow("Formato:", export_format_combo)
        
        export_interval_spin = QSpinBox()
        export_interval_spin.setRange(10, 3600)
        export_interval_spin.setValue(self.config_manager.config["export_interval"])
        export_interval_spin.setSuffix(" segundos")
        export_layout.addRow("Intervalo de exportación:", export_interval_spin)
        
        export_tab.setLayout(export_layout)
        tabs.addTab(export_tab, "Exportación")
        
        layout.addWidget(tabs)
        
        # Botones
        button_layout = QHBoxLayout()
        ok_btn = QPushButton("Guardar")
        cancel_btn = QPushButton("Cancelar")
        
        ok_btn.clicked.connect(lambda: self.save_config(
            interval_spin.value(), start_minimized.isChecked(), auto_start.isChecked(),
            alerts_enabled.isChecked(), cpu_warning_spin.value(), cpu_critical_spin.value(),
            gpu_warning_spin.value(), gpu_critical_spin.value(),
            export_enabled.isChecked(), export_path_edit.text(),
            export_format_combo.currentText(), export_interval_spin.value()
        ))
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def save_config(self, interval, start_minimized, auto_start,
                   alerts_enabled, cpu_warning, cpu_critical,
                   gpu_warning, gpu_critical,
                   export_enabled, export_path, export_format, export_interval):
        """Guarda la configuración"""
        self.config_manager.config["check_interval"] = interval
        self.config_manager.config["start_minimized"] = start_minimized
        self.config_manager.config["auto_start"] = auto_start
        self.config_manager.config["alerts_enabled"] = alerts_enabled
        self.config_manager.config["cpu_warning_threshold"] = cpu_warning
        self.config_manager.config["cpu_critical_threshold"] = cpu_critical
        self.config_manager.config["gpu_warning_threshold"] = gpu_warning
        self.config_manager.config["gpu_critical_threshold"] = gpu_critical
        self.config_manager.config["export_enabled"] = export_enabled
        self.config_manager.config["export_path"] = export_path
        self.config_manager.config["export_format"] = export_format
        self.config_manager.config["export_interval"] = export_interval
        
        self.config_manager.save_config()
        self.accept()


def create_dynamic_fan_icon(avg_temp=0):
    """Crea icono dinámico según temperatura"""
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush
    from PyQt6.QtCore import Qt
    
    # Determinar color según temperatura
    if avg_temp < 50:
        color = Qt.GlobalColor.green
        status = "Normal"
    elif avg_temp < 70:
        color = Qt.GlobalColor.yellow
        status = "Cálido"
    elif avg_temp < 85:
        color = Qt.GlobalColor.orange
        status = "Caliente"
    else:
        color = Qt.GlobalColor.red
        status = "Crítico"
    
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    
    # Color según temperatura
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(Qt.GlobalColor.black, 1))
    
    # Dibujar aspas del ventilador
    painter.save()
    painter.translate(16, 16)
    
    for i in range(4):
        painter.drawRect(-2, -12, 4, 24)
        painter.rotate(90)
    
    painter.restore()
    
    # Círculo central
    painter.setBrush(QBrush(Qt.GlobalColor.darkGray))
    painter.drawEllipse(12, 12, 8, 8)
    
    painter.end()
    
    return QIcon(pixmap), status


class MonitorTrayApp:
    """Aplicación principal de monitoreo en systray"""
    
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Verificar sensores antes de iniciar
        warnings = SystemChecker.check_sensors()
        if warnings:
            print("Advertencias del sistema:")
            for warning in warnings:
                print(f"  - {warning}")
        
        self.controller = MonitorController()
        self.config_manager = ConfigManager()
        self.controller.config_manager = self.config_manager  # Referencia para análisis
        
        # Usar los nuevos componentes mejorados
        self.usage_monitor = SystemUsageMonitor()
        self.trend_analyzer = TrendAnalyzer(self.controller)
        self.alert_manager = AdvancedAlertManager(self.config_manager)
        self.data_exporter = AdvancedDataExporter(self.config_manager)
        self.turbo_controller = TurboBoostController()
        self.signals = StatusSignals()
        
        # Datos actuales
        self.current_data = {
            'cpu_temps': {},
            'gpu_temp': None,
            'cpu_rpm': 0,
            'gpu_rpm': 0,
            'cpu_usage': 0,
            'gpu_usage': 0,
            'memory_usage': 0,
            'stats': None
        }
        
        # Iniciar exportación si está habilitada
        if self.config_manager.config["export_enabled"]:
            self.data_exporter.start_export()
        
        # Crear systray
        self.create_tray()
        
        # Timer para actualización
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(self.config_manager.config["check_interval"] * 1000)
        
        # Timer para exportación
        self.export_timer = QTimer()
        self.export_timer.timeout.connect(self.export_data)
        self.export_timer.start(self.config_manager.config["export_interval"] * 1000)
        
        # Conectar señales
        self.signals.alert_triggered.connect(self.show_alert)
        
        # Estado inicial
        self.running = True
        self.retry_count = 0  # Para reintentos de lectura de sensores
    
    def show_sensors_warning(self, warnings):
        """Muestra advertencias de sensores"""
        if not warnings:
            return
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Advertencias del Sistema")
        msg.setText("Algunas funciones de monitoreo pueden estar limitadas:")
        msg.setDetailedText("\n".join(warnings))
        msg.exec()
    
    def create_tray(self):
        """Crea el icono de systray"""
        self.tray = QSystemTrayIcon()
        
        # Usar el icono de ventilador dinámico
        icon, status = create_dynamic_fan_icon(0)
        
        self.tray.setIcon(icon)
        self.tray.setToolTip("HP Omen Monitor")
        
        # Menú contextual
        menu = QMenu()
        
        # Información de estado
        self.status_action = QAction("Estado: Iniciando...", self.app)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        
        menu.addSeparator()
        
        # Opción de refrescar (para solucionar problema de sensores al inicio)
        refresh_action = QAction("🔄 Refrescar Sensores", self.app)
        refresh_action.triggered.connect(self.force_refresh)
        menu.addAction(refresh_action)
        
        menu.addSeparator()
        
        # Control de Turbo Boost
        turbo_available = self.turbo_controller.is_available()
        if turbo_available:
            current_turbo_state = self.turbo_controller.get_current_state()
            turbo_state_str = "Deshabilitado (Modo Ahorro)" if current_turbo_state == 1 else "Habilitado (Modo Rendimiento)"
            
            self.turbo_action = QAction(f"⚡ Turbo Boost: {turbo_state_str}", self.app)
            self.turbo_action.setCheckable(True)
            self.turbo_action.setChecked(current_turbo_state == 0)  # 0 = activo
            self.turbo_action.triggered.connect(self.toggle_turbo_boost)
            menu.addAction(self.turbo_action)
        else:
            # Si no está disponible, mostrar opción deshabilitada
            turbo_action = QAction("⚡ Turbo Boost: No disponible", self.app)
            turbo_action.setEnabled(False)
            menu.addAction(turbo_action)
        
        menu.addSeparator()
        
        # Dashboard
        dashboard_action = QAction("Dashboard...", self.app)
        dashboard_action.triggered.connect(self.show_dashboard)
        menu.addAction(dashboard_action)
        
        # Gráficos en tiempo real
        charts_action = QAction("📊 Gráficos en Tiempo Real...", self.app)
        charts_action.triggered.connect(self.show_charts)
        menu.addAction(charts_action)
        
        # Análisis de historial
        history_action = QAction("📈 Análisis de Historial...", self.app)
        history_action.triggered.connect(self.show_history_analysis)
        menu.addAction(history_action)
        
        menu.addSeparator()
        
        # Alertas
        self.alerts_action = QAction("Alertas: Activadas", self.app)
        self.alerts_action.setCheckable(True)
        self.alerts_action.setChecked(self.config_manager.config["alerts_enabled"])
        self.alerts_action.triggered.connect(self.toggle_alerts)
        menu.addAction(self.alerts_action)
        
        # Exportación
        self.export_action = QAction("Exportación: Desactivada", self.app)
        self.export_action.setCheckable(True)
        self.export_action.setChecked(self.config_manager.config["export_enabled"])
        self.export_action.triggered.connect(self.toggle_export)
        menu.addAction(self.export_action)
        
        menu.addSeparator()
        
        # Configuración
        config_action = QAction("Configuración...", self.app)
        config_action.triggered.connect(self.show_config)
        menu.addAction(config_action)
        
        menu.addSeparator()
        
        # Salir
        quit_action = QAction("Salir", self.app)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray.setContextMenu(menu)
        
        # Tooltip al pasar el mouse
        self.tray.setToolTip("HP Omen Monitor - Iniciando...")
        
        self.tray.show()
    
    def update_status(self):
        """Actualiza el estado y tooltip"""
        cpu_temps = self.controller.read_cpu_temps()
        gpu_temp = self.controller.read_gpu_temp()
        cpu_rpm, gpu_rpm = self.controller.read_rpm()
        
        # Leer uso de CPU/GPU/memoria
        cpu_usage = self.usage_monitor.read_cpu_usage()
        gpu_usage = self.usage_monitor.read_gpu_usage()
        memory_usage = self.usage_monitor.read_memory_usage()
        
        # Verificar si tenemos datos válidos
        has_valid_data = (cpu_temps or gpu_temp) and (cpu_rpm > 0 or gpu_rpm > 0)
        
        if not has_valid_data:
            self.retry_count += 1
            if self.retry_count <= 5:  # Reintentar hasta 5 veces
                print(f"Intento {self.retry_count}/5: Sensores no listos, reintentando...")
                return
            else:
                print("Sensores no disponibles después de reintentos")
                # Continuar con datos parciales
        else:
            self.retry_count = 0  # Resetear contador si tenemos datos válidos
        
        # Actualizar historial con datos enriquecidos
        self.controller.update_history(cpu_temps, gpu_temp, cpu_rpm, gpu_rpm, 
                                     cpu_usage, gpu_usage, memory_usage)
        
        # Calcular estadísticas
        stats = self.controller.get_stats()
        
        # Actualizar datos actuales
        self.current_data = {
            'cpu_temps': cpu_temps,
            'gpu_temp': gpu_temp,
            'cpu_rpm': cpu_rpm,
            'gpu_rpm': gpu_rpm,
            'cpu_usage': cpu_usage,
            'gpu_usage': gpu_usage,
            'memory_usage': memory_usage,
            'stats': stats
        }
        
        # Calcular temperatura promedio del CPU
        if cpu_temps:
            avg_cpu_temp = sum(cpu_temps.values()) / len(cpu_temps)
        else:
            avg_cpu_temp = 0
        
        # Actualizar icono dinámico
        icon, status = create_dynamic_fan_icon(avg_cpu_temp)
        self.tray.setIcon(icon)
        
        # Actualizar tooltip con información enriquecida
        gpu_str = f"{gpu_temp:.1f}°C" if gpu_temp else "N/A"
        gpu_usage_str = f"{gpu_usage:.0f}%" if gpu_usage > 0 else "N/A"
        tooltip = f"HP Omen Monitor - {status}\n"
        tooltip += f"CPU: {avg_cpu_temp:.1f}°C ({cpu_usage:.0f}%) | {cpu_rpm} RPM\n"
        tooltip += f"GPU: {gpu_str} ({gpu_usage_str}) | {gpu_rpm} RPM\n"
        tooltip += f"Memoria: {memory_usage:.0f}%"
        self.tray.setToolTip(tooltip)
        
        # Actualizar acción de estado
        self.status_action.setText(f"CPU: {avg_cpu_temp:.1f}°C | GPU: {gpu_str} | CPU RPM: {cpu_rpm}")
        
        # Verificar alertas con el nuevo sistema avanzado
        if self.config_manager.config["alerts_enabled"]:
            alerts = self.alert_manager.check_alerts(cpu_temps, gpu_temp, cpu_usage, gpu_usage)
            for alert in alerts:
                self.signals.alert_triggered.emit(alert)
                
                # Ejecutar acción de alerta si existe
                if alert.get('action'):
                    self.alert_manager.execute_alert_action(alert['action'])
    
    def export_data(self):
        """Exporta datos actuales"""
        if self.config_manager.config["export_enabled"]:
            self.data_exporter.export_enhanced_data(
                self.current_data['cpu_temps'],
                self.current_data['gpu_temp'],
                self.current_data['cpu_rpm'],
                self.current_data['gpu_rpm'],
                self.current_data['cpu_usage'],
                self.current_data['gpu_usage'],
                self.current_data['memory_usage']
            )
    
    def force_refresh(self):
        """Fuerza una actualización inmediata de sensores"""
        print("Forzando actualización de sensores...")
        self.retry_count = 0  # Resetear contador de reintentos
        self.update_status()
        self.tray.showMessage(
            "Sensores Refrescados",
            "Lectura de sensores forzada exitosamente",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )
    
    def toggle_turbo_boost(self, checked):
        """Alterna el estado de Turbo Boost"""
        if checked:
            # Activar Turbo Boost (modo rendimiento)
            success = self.turbo_controller.enable_turbo_boost()
            if success:
                self.turbo_action.setText("⚡ Turbo Boost: Habilitado (Modo Rendimiento)")
                self.tray.showMessage(
                    "Turbo Boost Activado",
                    "Modo rendimiento máximo activado",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
        else:
            # Desactivar Turbo Boost (modo ahorro)
            success = self.turbo_controller.disable_turbo_boost()
            if success:
                self.turbo_action.setText("⚡ Turbo Boost: Deshabilitado (Modo Ahorro)")
                self.tray.showMessage(
                    "Turbo Boost Desactivado",
                    "Modo ahorro activado - temperaturas reducidas",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
    
    def show_alert(self, alert):
        """Muestra alerta de temperatura"""
        if alert['type'] == 'critical':
            self.tray.showMessage(
                f"¡ALERTA CRÍTICA {alert['source']}!",
                alert['message'],
                QSystemTrayIcon.MessageIcon.Critical,
                5000
            )
        else:
            self.tray.showMessage(
                f"Alerta {alert['source']}",
                alert['message'],
                QSystemTrayIcon.MessageIcon.Warning,
                3000
            )
    
    def toggle_alerts(self, checked):
        """Alterna las alertas"""
        self.config_manager.config["alerts_enabled"] = checked
        self.config_manager.save_config()
        self.alerts_action.setText(f"Alertas: {'Activadas' if checked else 'Desactivadas'}")
    
    def toggle_export(self, checked):
        """Alterna la exportación"""
        self.config_manager.config["export_enabled"] = checked
        self.config_manager.save_config()
        self.export_action.setText(f"Exportación: {'Activada' if checked else 'Desactivada'}")
        
        if checked:
            self.data_exporter.start_export()
    
    def show_dashboard(self):
        """Muestra el dashboard de monitoreo"""
        dialog = DashboardDialog(self.current_data, self.config_manager)
        dialog.exec()
    
    def show_charts(self):
        """Muestra los gráficos en tiempo real"""
        dialog = RealTimeChartsDialog(self.controller, self.config_manager)
        dialog.exec()
    
    def show_history_analysis(self):
        """Muestra el análisis de historial"""
        dialog = AdvancedHistoryDialog(self.controller, self.config_manager)
        dialog.exec()
    
    def show_config(self):
        """Muestra la configuración"""
        dialog = ConfigDialog(self.config_manager)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Actualizar timers si cambió el intervalo
            self.update_timer.setInterval(self.config_manager.config["check_interval"] * 1000)
            self.export_timer.setInterval(self.config_manager.config["export_interval"] * 1000)
            
            # Configurar auto-inicio
            self.setup_autostart(self.config_manager.config["auto_start"])
    
    def setup_autostart(self, enable):
        """Configura el inicio automático"""
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_file = autostart_dir / "omen-monitor-tray.desktop"
        
        if enable:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            
            desktop_content = f"""[Desktop Entry]
Type=Application
Name=HP Omen Monitor
Comment=Monitoreo de sistema para HP Omen
Exec=python3 {Path(__file__).absolute()}
Icon=fan
Terminal=false
Categories=System;
"""
            autostart_file.write_text(desktop_content)
        else:
            if autostart_file.exists():
                autostart_file.unlink()
    
    def quit_app(self):
        """Sale de la aplicación"""
        self.running = False
        self.app.quit()
    
    def run(self):
        """Ejecuta la aplicación"""
        # Configurar auto-inicio si está habilitado
        if self.config_manager.config["auto_start"]:
            self.setup_autostart(True)
        
        print("HP Omen Monitor iniciado correctamente en systray")
        print("Presiona Ctrl+C para salir")
        
        return self.app.exec()


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(description='HP Omen Monitor - Monitoreo de sistema')
    parser.add_argument('--debug', action='store_true', help='Modo debug con información detallada')
    parser.add_argument('--no-tray', action='store_true', help='No iniciar icono de systray (testing)')
    args = parser.parse_args()
    
    if args.debug:
        print("Modo debug activado")
        print(f"DISPLAY: {os.environ.get('DISPLAY', 'No establecido')}")
        print(f"CPU_HWMON: {CPU_HWMON}")
        print(f"MATPLOTLIB_AVAILABLE: {MATPLOTLIB_AVAILABLE}")
        print(f"NUMPY_AVAILABLE: {NUMPY_AVAILABLE}")
    
    try:
        # Verificar si estamos en un entorno gráfico
        if not os.environ.get('DISPLAY'):
            print("Error: No se detectó entorno gráfico (DISPLAY no establecido)")
            print("Este programa requiere un entorno gráfico para funcionar")
            print("Asegúrate de estar ejecutando esto en una sesión gráfica")
            return 1
        
        # Verificar permisos y continuar
        app = MonitorTrayApp()
        return app.run()
    except Exception as e:
        print(f"Error fatal: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    main()
