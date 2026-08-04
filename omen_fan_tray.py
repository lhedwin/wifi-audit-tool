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

# Rutas del sistema (solo monitoreo)
CPU_RPM = Path("/sys/devices/platform/omen-rgb-keyboard/fan/cpu_fan_rpm")
GPU_RPM = Path("/sys/devices/platform/omen-rgb-keyboard/fan/gpu_fan_rpm")
TEMP_PATHS = [
    Path("/sys/class/hwmon/hwmon6/temp1_input"),  # CPU package
    Path("/sys/class/hwmon/hwmon6/temp2_input"),  # CPU core 0
    Path("/sys/class/hwmon/hwmon6/temp3_input"),  # CPU core 1
    Path("/sys/class/hwmon/hwmon6/temp4_input"),  # CPU core 2
    Path("/sys/class/hwmon/hwmon6/temp5_input"),  # CPU core 3
]
GPU_TEMP_PATHS = [
    Path("/sys/class/drm/card0/device/hwmon/hwmon*/temp1_input"),
    Path("/sys/class/hwmon/hwmon0/temp1_input"),
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
        self.time_history = []
        self.start_time = time.time()
        
    def read_cpu_temps(self):
        """Lee las temperaturas del CPU (package + cores)"""
        cpu_temps = {}
        try:
            # Leer todos los sensores de temperatura del hwmon6
            temp_files = sorted(Path("/sys/class/hwmon/hwmon6").glob("temp*_input"))
            
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
    
    def update_history(self, cpu_temps, gpu_temp, cpu_rpm, gpu_rpm):
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
        self.time_history.append(current_time)
        
        # Mantener tamaño máximo del historial
        if len(self.time_history) > self.history_max_points:
            self.cpu_temp_history.pop(0)
            self.gpu_temp_history.pop(0)
            self.cpu_rpm_history.pop(0)
            self.gpu_rpm_history.pop(0)
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
        
        current_layout.addWidget(self.cpu_temp_label)
        current_layout.addWidget(self.gpu_temp_label)
        current_layout.addWidget(self.cpu_rpm_label)
        current_layout.addWidget(self.gpu_rpm_label)
        
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


class ChartsDialog(QDialog):
    """Diálogo de historial de datos (versión simplificada sin gráficos)"""
    
    def __init__(self, controller, config_manager, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.config_manager = config_manager
        self.setup_ui()
        self.update_data()
    
    def setup_ui(self):
        self.setWindowTitle("HP Omen Monitor - Historial de Datos")
        self.setMinimumWidth(700)
        
        layout = QVBoxLayout()
        
        # Historial de temperaturas
        temp_group = QGroupBox("Historial de Temperaturas (Últimos 5 minutos)")
        temp_layout = QVBoxLayout()
        
        self.temp_history_text = QTextEdit()
        self.temp_history_text.setReadOnly(True)
        self.temp_history_text.setMaximumHeight(200)
        temp_layout.addWidget(self.temp_history_text)
        
        temp_group.setLayout(temp_layout)
        layout.addWidget(temp_group)
        
        # Historial de RPM
        rpm_group = QGroupBox("Historial de Ventiladores (Últimos 5 minutos)")
        rpm_layout = QVBoxLayout()
        
        self.rpm_history_text = QTextEdit()
        self.rpm_history_text.setReadOnly(True)
        self.rpm_history_text.setMaximumHeight(200)
        rpm_layout.addWidget(self.rpm_history_text)
        
        rpm_group.setLayout(rpm_layout)
        layout.addWidget(rpm_group)
        
        # Estadísticas
        stats_group = QGroupBox("Estadísticas del Período")
        stats_layout = QVBoxLayout()
        
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.stats_text.setMaximumHeight(150)
        stats_layout.addWidget(self.stats_text)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def update_data(self):
        """Actualiza los datos del historial"""
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
        
        # Estadísticas
        stats = self.controller.get_stats()
        if stats:
            stats_text = (
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
            self.stats_text.setText(stats_text)
        else:
            self.stats_text.setText("No hay datos suficientes para calcular estadísticas.")


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


def create_fan_icon():
    """Icono de ventilador estático"""
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush
    from PyQt6.QtCore import Qt
    
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    
    # Color según temperatura (usaremos azul por defecto)
    painter.setBrush(QBrush(Qt.GlobalColor.blue))
    painter.setPen(QPen(Qt.GlobalColor.black, 1))
    
    # Dibujar aspas del ventilador (estático)
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
    return QIcon(pixmap)


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
        self.alert_manager = AlertManager(self.config_manager)
        self.data_exporter = DataExporter(self.config_manager)
        self.signals = StatusSignals()
        
        # Datos actuales
        self.current_data = {
            'cpu_temps': {},
            'gpu_temp': None,
            'cpu_rpm': 0,
            'gpu_rpm': 0,
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
        
        # Usar el icono de ventilador
        icon = create_fan_icon()
        
        self.tray.setIcon(icon)
        self.tray.setToolTip("HP Omen Monitor")
        
        # Menú contextual
        menu = QMenu()
        
        # Información de estado
        self.status_action = QAction("Estado: Iniciando...", self.app)
        self.status_action.setEnabled(False)
        menu.addAction(self.status_action)
        
        menu.addSeparator()
        
        # Dashboard
        dashboard_action = QAction("Dashboard...", self.app)
        dashboard_action.triggered.connect(self.show_dashboard)
        menu.addAction(dashboard_action)
        
        # Gráficos
        charts_action = QAction("Gráficos en Tiempo Real...", self.app)
        charts_action.triggered.connect(self.show_charts)
        menu.addAction(charts_action)
        
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
        
        # Actualizar historial
        self.controller.update_history(cpu_temps, gpu_temp, cpu_rpm, gpu_rpm)
        
        # Calcular estadísticas
        stats = self.controller.get_stats()
        
        # Actualizar datos actuales
        self.current_data = {
            'cpu_temps': cpu_temps,
            'gpu_temp': gpu_temp,
            'cpu_rpm': cpu_rpm,
            'gpu_rpm': gpu_rpm,
            'stats': stats
        }
        
        # Calcular temperatura promedio del CPU
        if cpu_temps:
            avg_cpu_temp = sum(cpu_temps.values()) / len(cpu_temps)
        else:
            avg_cpu_temp = 0
        
        # Actualizar tooltip
        gpu_str = f"{gpu_temp:.1f}°C" if gpu_temp else "N/A"
        tooltip = f"HP Omen Monitor\nCPU: {avg_cpu_temp:.1f}°C | {cpu_rpm} RPM\nGPU: {gpu_str} | {gpu_rpm} RPM"
        self.tray.setToolTip(tooltip)
        
        # Actualizar acción de estado
        self.status_action.setText(f"CPU: {avg_cpu_temp:.1f}°C | GPU: {gpu_str} | CPU RPM: {cpu_rpm}")
        
        # Verificar alertas
        if self.config_manager.config["alerts_enabled"]:
            alerts = self.alert_manager.check_alerts(cpu_temps, gpu_temp)
            for alert in alerts:
                self.signals.alert_triggered.emit(alert)
    
    def export_data(self):
        """Exporta datos actuales"""
        if self.config_manager.config["export_enabled"]:
            self.data_exporter.export_data(
                self.current_data['cpu_temps'],
                self.current_data['gpu_temp'],
                self.current_data['cpu_rpm'],
                self.current_data['gpu_rpm']
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
        dialog = ChartsDialog(self.controller, self.config_manager)
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
    # Verificar permisos y continuar
    app = MonitorTrayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
