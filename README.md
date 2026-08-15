# HP Omen Monitor - Sistema de Monitoreo de Hardware

![License](https://img.shields.io/badge/license-GPLv3-blue.svg) ![Python](https://img.shields.io/badge/python-3.x-blue.svg) ![Security](https://img.shields.io/badge/security-monitoring-green.svg)

Sistema de monitoreo en tiempo real para laptops HP OMEN con control de temperaturas, ventiladores y rendimiento. Diseñado específicamente para portátiles OMEN con hardware restringido donde el control manual de fans no está disponible.

## 📋 Descripción del Proyecto

Este proyecto es una aplicación de escritorio (systray) que proporciona monitoreo continuo del sistema para laptops HP OMEN, con especial énfasis en el control térmico dado que estos portátiles tienden a tener problemas de sobrecalentamiento. La aplicación permite:

- **Monitoreo de temperaturas**: CPU (package + cores individuales) y GPU NVIDIA
- **Control de ventiladores**: RPM de CPU y GPU en tiempo real
- **Control de Turbo Boost**: Integración con control de Intel Turbo Boost para gestión térmica
- **Análisis de tendencias**: Predicción de temperaturas futuras y detección de patrones
- **Alertas inteligentes**: Sistema de alertas con acciones automáticas de software
- **Gráficos en tiempo real**: Visualización matplotlib de temperaturas, RPM y uso de recursos
- **Exportación de datos**: Guardado automático de métricas en CSV/JSON
- **Dashboard detallado**: Vista completa del estado del sistema con estadísticas

## 🎯 Características Principales

- ✅ **Icono dinámico en systray**: Cambia de color según temperatura (verde/amarillo/naranja/rojo)
- ✅ **Control de Turbo Boost**: Integración gráfica para desactivar Turbo Boost cuando el CPU se calienta
- ✅ **Gráficos en tiempo real**: Visualización matplotlib con temperaturas, RPM y uso de CPU/GPU
- ✅ **Análisis de tendencias**: Predicción de temperaturas futuras y detección de patrones
- ✅ **Alertas inteligentes**: Alertas basadas en temperatura + uso combinado con acciones automáticas
- ✅ **Refresco de sensores**: Solución para problemas de sensores no disponibles al inicio
- ✅ **Monitoreo de uso de recursos**: CPU, GPU y memoria en tiempo real
- ✅ **Exportación de datos**: Guardado automático con metadatos enriquecidos
- ✅ **Detección automática de hardware**: Encuentra automáticamente hwmon correcto para temperaturas
- ✅ **Integración con CoolerControl**: Trabaja junto con CoolerControl como único controlador de fans
- ✅ **Control de luces RGB**: Compatible con servicio HPM RGB para teclado OMEN

## 📁 Estructura del Proyecto

```
/home/lhedwin/Programacion/Git/MonitoreoPC/
├── README.md                           # Este archivo
├── omen_fan_tray.py                    # Aplicación principal de monitoreo
├── iniciar_omen_monitor.sh              # Script de inicio del programa
├── .config/omen-fan-tray/              # Directorio de configuración
│   └── config.json                     # Archivo de configuración
└── omen_monitor_logs/                  # Directorio de exportación de datos (si está habilitado)
```

## 🔧 Requisitos del Sistema

### Sistema Operativo
- **Linux** (probado en CachyOS/Arch Linux)
- **Desktop Environment**: KDE Plasma, GNOME, u otro entorno gráfico
- **Hardware**: HP OMEN 15-dh1070wm o similar (con control de fans restringido)

### Software Requerido

#### Python 3.x
```bash
# Verificar versión de Python
python3 --version

# Instalar Python 3 si no está instalado
sudo pacman -S python3  # Arch/CachyOS
sudo apt install python3  # Debian/Ubuntu
sudo dnf install python3  # Fedora
```

#### Dependencias de Python
```bash
# PyQt6 (interfaz gráfica)
sudo pacman -S python-pyqt6  # Arch/CachyOS
sudo apt install python3-pyqt6  # Debian/Ubuntu

# matplotlib (gráficos - opcional)
sudo pacman -S python-matplotlib  # Arch/CachyOS
sudo apt install python3-matplotlib  # Debian/Ubuntu

# numpy (análisis de tendencias - opcional)
sudo pacman -s python-numpy  # Arch/CachyOS
sudo apt install python3-numpy  # Debian/Ubuntu
```

### Hardware Requerido

#### Hardware OMEN Compatible
- **Laptop HP OMEN** (serie 15-dh1xxx o similar)
- **Sensores de temperatura**: coretemp para CPU, nvidia-smi para GPU
- **Sensores de RPM**: /sys/devices/platform/omen-rgb-keyboard/fan/
- **Control de Turbo Boost**: /sys/devices/system/cpu/intel_pstate/no_turbo
- **GPU NVIDIA**: GTX 1660 Ti Mobile o similar

#### Hardware Opcional
- **CoolerControl**: Recomendado como único controlador de fans
- **pkexec**: Para solicitud gráfica de contraseña (sistema polkit)

### Permisos del sistema
- **Lectura de sensores**: /sys/class/hwmon/, /sys/devices/platform/
- **Escritura en sysfs**: Para control de Turbo Boost (requiere sudo/pkexec)
- **Entorno gráfico**: DISPLAY configurado para interfaz de systray

## 📦 Instalación

### 1. Verificar Dependencias

```bash
# Verificar Python 3
python3 --version

# Verificar PyQt6
python3 -c "from PyQt6.QtWidgets import QApplication; print('PyQt6 disponible')"

# Verificar matplotlib y numpy (opcional)
python3 -c "import matplotlib; import numpy; print('matplotlib y numpy disponibles')"
```

### 2. Instalar Dependencias Faltantes

```bash
# Arch/CachyOS
sudo pacman -S python-pyqt6 python-matplotlib python-numpy

# Debian/Ubuntu
sudo apt update
sudo apt install python3-pyqt6 python3-matplotlib python3-numpy

# Fedora
sudo dnf install python3-pyqt6 python3-matplotlib python-numpy
```

### 3. Verificar Hardware OMEN

```bash
# Verificar sensores de temperatura
ls /sys/class/hwmon/hwmon*/temp*_input

# Verificar sensores de RPM
ls /sys/devices/platform/omen-rgb-keyboard/fan/

# Verificar control de Turbo Boost
ls /sys/devices/system/cpu/intel_pstate/no_turbo

# Verificar CoolerControl
systemctl status coolercontrold
```

## 🚀 Uso

### Ejecución Principal

```bash
cd /home/lhedwin/Programacion/Git/MonitoreoPC
python3 omen_fan_tray.py

# Con modo debug para ver información detallada
python3 omen_fan_tray.py --debug

# Usando el script de inicio
./iniciar_omen_monitor.sh
```

### Flujo de Operación

1. **Inicio automático**: El programa se minimiza al systray y comienza monitoreo
2. **Detección de sensores**: Detecta automáticamente hwmon correcto para temperaturas
3. **Monitoreo continuo**: Actualiza temperaturas, RPM y uso de recursos cada segundo
4. **Icono dinámico**: Cambia de color según temperatura del CPU
5. **Alertas inteligentes**: Notifica cuando la temperatura alcanza umbrales críticos
6. **Gráficos en tiempo real**: Muestra visualización detallada del sistema
7. **Control de Turbo Boost**: Permite desactivar Turbo Boost cuando el CPU se calienta
8. **Exportación de datos**: Guarda métricas automáticamente si está habilitado

### Control de Turbo Boost

**Cuando el CPU llegue a 98°C (temperatura crítica):**
1. Click derecho en el icono del programa
2. Desmarcar "⚡ Turbo Boost: Habilitado (Modo Rendimiento)"
3. Ingresar contraseña cuando se solicite (gráficamente via pkexec)
4. Verás notificación: "Turbo Boost Desactivado - Modo ahorro activado"

**Cuando la temperatura baje y quieras rendimiento máximo:**
1. Click derecho en el icono
2. Marcar "⚡ Turbo Boost: Deshabiitado (Modo Ahorro)"
3. Ingresar tu contraseña
4. Verás notificación: "Turbo Boost Activado - Modo rendimiento máximo activo"

### Opciones del Menú Contextual

- **🔄 Refrescar Sensores**: Fuerza lectura de sensores (soluciona problemas al inicio)
- **⚡ Turbo Boost**: Control de Intel Turbo Boost (requiere contraseña)
- **Dashboard...**: Vista completa del estado actual del sistema
- **📊 Gráficos en Tiempo Real...**: Gráficos matplotlib con temperaturas, RPM y uso
- **📈 Análisis de Historial...**: Análisis de tendencias y predicciones
- **Alertas**: Activar/desactivar alertas de temperatura
- **Exportación**: Activar/desactivar exportación de datos
- **Configuración...**: Configuración de umbrales, intervalos, etc.
- **Salir**: Cerrar la aplicación

## ⚙️ Configuración

### Configuración Predeterminada

```python
# Rutas del sistema (detección automática)
CPU_HWMON = find_cpu_hwmon()  # Detecta automáticamente hwmon correcto
NO_TURBO_PATH = "/sys/devices/system/cpu/intel_pstate/no_turbo"

# Configuración de monitoreo
check_interval = 1  # segundos entre actualizaciones
history_duration = 300  # segundos de historial (5 minutos)
history_max_points = 300  # puntos de historial

# Umbrales de alerta
cpu_warning_threshold = 75  # °C
cpu_critical_threshold = 85  # °C
gpu_warning_threshold = 80  # °C
gpu_critical_threshold = 90  # °C

# Exportación de datos
export_enabled = False
export_path = str(Path.home() / "omen_monitor_logs")
export_format = "csv"  # csv, json
export_interval = 60  # segundos
```

### Personalización

Puedes modificar estos parámetros en el archivo de configuración `~/.config/omen-fan-tray/config.json`:

```json
{
  "start_minimized": true,
  "auto_start": true,
  "check_interval": 1,
  "alerts_enabled": true,
  "cpu_warning_threshold": 75,
  "cpu_critical_threshold": 85,
  "gpu_warning_threshold": 80,
  "gpu_critical_threshold": 90,
  "export_enabled": false,
  "export_path": "/home/lhedwin/omen_monitor_logs",
  "export_format": "csv",
  "export_interval": 60,
  "show_stats": true,
  "show_history": true,
  "theme": "dark"
}
```

## 📊 Monitoreo y Análisis

### Métricas Monitoreadas

- **Temperaturas CPU**: Package y cores individuales (coretemp)
- **Temperatura GPU**: NVIDIA GPU vía nvidia-smi
- **Velocidad de ventiladores**: RPM de CPU y GPU
- **Uso de CPU**: Porcentaje de uso del procesador
- **Uso de GPU**: Porcentaje de uso de la tarjeta gráfica
- **Uso de memoria**: Porcentaje de RAM utilizada
- **Load average**: Carga promedio del sistema

### Análisis de Tendencias

- **Predicción de temperatura**: Estima temperatura futura basada en tendencia
- **Detección de patrones**: Identifica si la temperatura está aumentando consistentemente
- **Tiempo a umbral**: Calcula tiempo estimado para alcanzar umbrales críticos
- **Comparación histórica**: Comparación con datos de los últimos 5 minutos

### Alertas Inteligentes

- **Alertas combinadas**: Considera temperatura + uso de CPU/GPU
- **Acciones automáticas**: Reducción de frecuencia CPU o potencia GPU cuando hay sobrecarga
- **Notificaciones visuales**: Mensajes en systray con diferentes iconos
- **Cooldown**: Evita spam de alertas con intervalo de 30 segundos

## 🛠️ Solución de Problemas

### No se detectan sensores de temperatura

**Solución**: El programa detecta automáticamente el hwmon correcto. Si falla:
```bash
# Verificar sensores disponibles
ls /sys/class/hwmon/hwmon*/temp*_input

# Verificar que coretemp está disponible
ls /sys/class/hwmon/hwmon*/name
cat /sys/class/hwmon/hwmon*/name
```

### Icono no aparece en systray

**Solución**: Verificar entorno gráfico:
```bash
# Verificar DISPLAY
echo $DISPLAY

# Verificar que el programa se está ejecutando
ps aux | grep omen_fan_tray
```

### Gráficos no muestran datos

**Solución**: Verificar dependencias:
```bash
# Verificar matplotlib
python3 -c "import matplotlib; print('matplotlib disponible')"

# Verificar numpy
python3 -c "import numpy; print('numpy disponible')"
```

### Control de Turbo Boost no funciona

**Solución**: Verificar disponibilidad y permisos:
```bash
# Verificar que no_turbo existe
ls /sys/devices/system/cpu/intel_pstate/no_turbo

# Verificar estado actual
cat /sys/devices/system/cpu/intel_pstate/no_turbo

# Probar cambio manual (requiere contraseña)
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
```

### RPM no se muestran

**Solución**: Verificar que los sensores de RPM existen:
```bash
# Verificar sensores de RPM
ls /sys/devices/platform/omen-rgb-keyboard/fan/

# Leer valores manualmente
cat /sys/devices/platform/omen-rgb-keyboard/fan/cpu_fan_rpm
cat /sys/devices/platform/omen-rgb-keyboard/fan/gpu_fan_rpm
```

## ⚠️ Notas Importantes

### Limitaciones de Hardware

- **Control de fans restringido**: En algunos modelos OMEN, el control manual de fans no está disponible
- **Solo monitoreo**: Este programa está diseñado para monitoreo y control térmico, no control de fans
- **Compatibilidad**: Probado en HP OMEN 15-dh1070wm, puede funcionar en modelos similares

### Control de Turbo Boost

- **Requiere permisos**: El control de Turbo Boost requiere permisos de administrador (sudo/pkexec)
- **Solicitud gráfica**: Usa pkexec para solicitar contraseña de forma gráfica
- **Reversibilidad**: Los cambios son inmediatos y reversibles
- **Práctica recomendada**: Desactivar Turbo Boost cuando CPU > 95°C para proteger el hardware

### Dependencias Opcionales

- **matplotlib**: Si no está disponible, los gráficos se muestran en versión texto
- **numpy**: Si no está disponible, el análisis de tendencias se deshabilita
- **pkexec**: Si no está disponible, se requiere contraseña manual en terminal

## 📊 Especificaciones Técnicas

- **Lenguaje**: Python 3.x
- **Framework GUI**: PyQt6
- **Gráficos**: matplotlib (opcional)
- **Análisis**: numpy (opcional)
- **Sistema de archivos**: sysfs para lectura de sensores
- **Desktop Environment**: KDE Plasma, GNOME, otros entornos gráficos
- **Protocolos**: sysfs, polkit (pkexec) para permisos elevados

## 🔐 Seguridad

- **Lectura de sensores**: Solo lectura de directorios del sistema
- **Control de Turbo Boost**: Requiere permisos administrativos (pkexec/sudo)
- **Sin almacenamiento de contraseñas**: No guarda credenciales ni datos sensibles
- **Red local**: No hace conexiones de red externas
- **Privacidad de datos**: Todos los datos se mantienen localmente

## 📝 Archivos Generados

### Configuración
- `~/.config/omen-fan-tray/config.json` - Configuración del usuario

### Exportación de Datos (si está habilitada)
- `~/omen_monitor_logs/omen_monitor_enhanced_YYYYMMDD_HHMMSS.csv` - Datos en formato CSV
- `~/omen_monitor_logs/omen_monitor_enhanced_YYYYMMDD_HHMMSS.json` - Datos en formato JSON

### Logs
- Salida estándar del programa a consola (en modo debug)

## 🤝 Estado del Proyecto

### Funcionalidades Actuales ✅
- Monitoreo de temperaturas CPU (package + cores individuales)
- Monitoreo de temperatura GPU NVIDIA
- Monitoreo de RPM de ventiladores
- Monitoreo de uso de CPU/GPU/memoria
- Icono dinámico según temperatura
- Control de Turbo Boost con solicitud gráfica de contraseña
- Gráficos en tiempo real con matplotlib
- Análisis de tendencias y predicciones
- Alertas inteligentes con acciones automáticas
- Exportación de datos en CSV/JSON
- Dashboard detallado con estadísticas
- Detección automática de hardware
- Control de luces RGB vía HPM RGB service
- Sistema de reintentos para sensores no disponibles
- Integración con CoolerControl

### Funcionalidades Futuras 🚧
- Integración con control de fans cuando el hardware lo permita
- Interfaz web para monitoreo remoto
- Sistema de perfiles automáticos (gaming, trabajo, etc.)
- Notificaciones push a móvil
- Comparación de rendimiento entre diferentes configuraciones
- Base de datos histórica de métricas
- Recomendaciones automáticas basadas en patrones de uso

## 🔗 Recursos Relacionados

- [Documentación de PyQt6](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [Documentación de matplotlib](https://matplotlib.org/stable/)
- [Documentación de CoolerControl](https://gitlab.com/CoolerControl/CoolerControl)
- [Documentación de sysfs](https://www.kernel.org/doc/Documentation/filesystems/sysfs.txt)
- [Intel Turbo Boost documentation](https://www.intel.com/content/www/us/en/docs/overclocking-intel-turbo-boost.html)

## 📞 Soporte

Para problemas específicos de monitoreo de hardware, consulta:
- Documentación de CoolerControl
- Documentación de tu distribución Linux
- Foros de la comunidad HP OMEN
- Documentación de sysfs y sensores de hardware

## 🔄 Historial de Mejoras

### Mejoras Recientes (v2.0)
- **Control de Turbo Boost**: Integración gráfica para gestión térmica
- **Gráficos en tiempo real**: Visualización matplotlib con marcadores visibles
- **Análisis de tendencias**: Predicción de temperaturas futuras
- **Alertas inteligentes**: Sistema de alertas con acciones automáticas
- **Monitoreo de uso**: CPU, GPU y memoria en tiempo real
- **Exportación mejorada**: Datos enriquecidos con más metadatos
- **Icono dinámico**: Cambia de color según temperatura
- **Refresco de sensores**: Solución para problemas al inicio
- **Detección automática**: Encuentra hwmon correcto automáticamente

### v1.0 - Versión Inicial
- Monitoreo básico de temperaturas y RPM
- Icono estático en systray
- Dashboard simple
- Exportación básica de datos
- Alertas de temperatura simples

---

**Versión**: 2.0  
**Última actualización**: 14/08/2026  
**Sistema probado**: CachyOS Linux 7.1.8-1-cachyos  
**Hardware**: HP OMEN 15-dh1070wm  
**CPU**: Intel Core i7-10750H @ 2.60GHz  
**GPU**: NVIDIA GeForce GTX 1660 Ti Mobile  
**RAM**: 16GB  
**Estado**: Monitoreo completo funcional con control térmico avanzado