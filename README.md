# WiFi Audit Tool - Herramienta de Auditoría WiFi

![License](https://img.shields.io/badge/license-GPLv3-blue.svg) ![Python](https://img.shields.io/badge/python-3.x-blue.svg) ![Security](https://img.shields.io/badge/security-audit-red.svg)

Herramienta de auditoría WiFi automatizada para pruebas de seguridad en redes wireless.

## 📋 Descripción del Proyecto

Este proyecto es una herramienta de Python que automatiza el proceso de auditoría de redes WiFi, desde la identificación de interfaces hasta el análisis de seguridad mediante técnicas de seguridad wireless. La aplicación permite:

- **Detección automática de interfaces**: Identifica PHY, driver, chipset y bandas soportadas
- **Activación de modo monitor**: Configura interfaces WiFi para captura de tráfico
- **Escaneo de redes**: Detecta y muestra redes ordenadas por intensidad de señal
- **Selección múltiple de redes**: Permite auditar varias redes en una sola sesión
- **Captura de handshake**: Implementa ataques de deautenticación para capturar WPA/WPA2
- **Análisis de seguridad**: Convierte y analiza handshakes con herramientas especializadas
- **Aceleración por GPU**: Utiliza GPU NVIDIA si está disponible
- **Guardado de resultados**: Registra contraseñas y hallazgos en archivos estructurados

## 🎯 Características Principales

- ✅ Interfaz de línea de comandos interactiva
- ✅ Detección automática de hardware WiFi con información detallada
- ✅ Recomendación de interfaz basada en compatibilidad
- ✅ Selección múltiple de redes usando rangos (ej: 1,3,5-8)
- ✅ Captura inteligente de handshake con múltiples fases
- ✅ Detección en tiempo real de handshake durante el proceso
- ✅ Auto-detección y uso de GPU NVIDIA para aceleración
- ✅ Barra de progreso con ETA durante análisis
- ✅ Guardado automático de resultados en archivos estructurados
- ✅ Integración con herramientas de seguridad estándar (aircrack-ng, hcxtools, hashcat)

## 📁 Estructura del Proyecto

```
/home/lhedwin/Hacking/wifi/
├── README.md                           # Este archivo
├── auditar_wifi.py                    # Aplicación principal de auditoría
├── passwords_encontradas.txt         # Resultados de análisis
├── aircrack-ng/                       # Directorio para archivos temporales
├── diccionarios/                      # Wordlists para análisis
├── Documentacion/                     # Documentación adicional
└── rules/                             # Reglas y configuraciones
```

## 🔧 Requisitos del Sistema

### Sistema Operativo
- **Linux** (probado en CachyOS/Arch Linux)
- Compatible con distribuciones basadas en systemd
- Entorno de línea de comandos

### Software Requerido

#### Python 3.x
```bash
# Verificar versión de Python
python3 --version

# Instalar Python 3 si no está instalado
sudo pacman -S python  # Arch/CachyOS
sudo apt install python3  # Debian/Ubuntu
sudo dnf install python3  # Fedora
```

#### Herramientas de Seguridad WiFi
```bash
# Instalar aircrack-ng
sudo pacman -S aircrack-ng  # Arch/CachyOS
sudo apt install aircrack-ng  # Debian/Ubuntu
sudo dnf install aircrack-ng  # Fedora

# Instalar hcxtools
sudo pacman -S hcxtools  # Arch/CachyOS
sudo apt install hcxtools  # Debian/Ubuntu

# Instalar hashcat
sudo pacman -S hashcat  # Arch/CachyOS
sudo apt install hashcat  # Debian/Ubuntu
sudo dnf install hashcat  # Fedora
```

### Hardware Requerido

#### Hardware WiFi Compatible
- **Tarjeta WiFi** con soporte de modo monitor
- **Chipset** compatible con aircrack-ng (Atheros, Realtek, Intel)
- **Antena** WiFi externa recomendada para mejor captura
- **Interfaz** que no esté en uso por otras aplicaciones

#### Hardware Opcional
- **GPU NVIDIA** para aceleración de hashcat (CUDA)
- **Adaptador WiFi USB** adicional para captura simultánea

### Permisos del sistema
- **Root/sudo**: Requerido para manipulación de interfaces de red
- **Acceso a hardware WiFi**: Control de modo monitor e inyección de paquetes
- **Escritura en directorios de trabajo**: Para guardar resultados

## 📦 Instalación

### 1. Verificar Dependencias

```bash
# Verificar Python 3
python3 --version

# Verificar herramientas de seguridad
airmon-ng --version
hcxpcapngtool --version
hashcat --version
```

### 2. Instalar Dependencias Faltantes

```bash
# Arch/CachyOS
sudo pacman -S python aircrack-ng hcxtools hashcat

# Debian/Ubuntu
sudo apt update
sudo apt install python3 aircrack-ng hcxtools hashcat

# Fedora
sudo dnf install python3 aircrack-ng hcxtools hashcat
```

### 3. Verificar Hardware WiFi

```bash
# Listar interfaces WiFi
iwconfig

# Verificar modo monitor
sudo airmon-ng

# Verificar capacidades de inyección
sudo aireplay-ng --test
```

## 🚀 Uso

### Ejecución Principal (requiere root)

```bash
cd /home/lhedwin/Hacking/wifi
sudo python3 auditar_wifi.py
```

### Flujo de Operación

1. **Identificar interfaces WiFi**: Detecta interfaces disponibles con información completa
2. **Activar modo monitor**: Configura la interfaz seleccionada para captura de tráfico
3. **Escanear redes**: Realiza escaneo de 15 segundos y muestra redes por intensidad
4. **Seleccionar redes**: Permite selección múltiple usando rangos (ej: 1,3,5-8)
5. **Capturar handshake**: Utiliza deautenticación para capturar WPA/WPA2
6. **Convertir formato**: Convierte .cap a .hc22000 usando hcxpcapngtool
7. **Analizar seguridad**: Realiza análisis con hashcat y GPU si está disponible
8. **Mostrar resultados**: Despliega hallazgos y guarda en archivo estructurado

### Selección de Redes

El sistema soporta selección múltiple usando diferentes formatos:
- **Individual**: `1` (solo red 1)
- **Múltiple**: `1,3,5` (redes 1, 3 y 5)
- **Rangos**: `2-6` (redes 2, 3, 4, 5 y 6)
- **Combinado**: `1,3,5-8,10` (redes 1, 3, 5, 6, 7, 8 y 10)

## ⚙️ Configuración

### Configuración Predeterminada

```python
WORK_DIR = Path("/home/lhedwin/Hacking/wifi")
AIRCRACK_DIR = WORK_DIR / "aircrack-ng"
PASSWORDS_FILE = WORK_DIR / "passwords_encontradas.txt"
SCAN_DURATION = 15  # segundos
DEAUTH_PACKETS = 3  # paquetes de deautenticación
POST_DEAUTH_WAIT = 12  # segundos de espera
```

### Personalización

Puedes modificar estos parámetros en `auditar_wifi.py` según tus necesidades:
- **SCAN_DURATION**: Duración del escaneo de redes
- **DEAUTH_PACKETS**: Cantidad de paquetes de deautenticación
- **POST_DEAUTH_WAIT**: Tiempo de espera después de deautenticación
- **WORK_DIR**: Directorio de trabajo principal

## 📊 Análisis de Seguridad

### Tipos de Análisis

- **WPA/WPA2 Handshake**: Captura y análisis de handshake 4-way
- **WPS**: Análisis de vulnerabilidades WPS (si está disponible)
- **WEP**: Análisis de redes WEP (obsoleto pero soportado)
- **Open Networks**: Identificación de redes sin seguridad

### Máscaras de Análisis

La herramienta utiliza máscaras optimizadas para:
- **8 dígitos numéricos**: Contraseñas de routers comunes
- **Diccionarios personalizados**: Wordlists en directorio `diccionarios/`
- **Patrones específicos**: Contraseñas basadas en SSID

## 🛠️ Solución de Problemas

### No se detectan interfaces WiFi

**Solución**: Verificar que la tarjeta WiFi esté conectada:
```bash
iwconfig
ls /sys/class/net/
```

### Error al activar modo monitor

**Solución**: Verificar que no hay procesos usando la interfaz:
```bash
sudo airmon-ng check kill
sudo airmon-ng start wlan0
```

### No se captura handshake

**Solución**: 
- Aumentar `DEAUTH_PACKETS` en configuración
- Verificar que haya clientes conectados a la red
- Acercarse al punto de acceso para mejor señal
- Usar antena WiFi externa

### hashcat no detecta GPU

**Solución**: Verificar instalación de drivers CUDA:
```bash
nvidia-smi
hashcat -I
```

## ⚠️ Notas Importantes de Seguridad

### Uso Ético y Legal

- ⚠️ **Solo redes propias**: Usa esta herramienta únicamente en redes que poseas
- ⚠️ **Autorización explícita**: Requiere permiso del propietario de la red
- ⚠️ **Cumplimiento legal**: El uso no autorizado es ilegal en la mayoría de jurisdicciones
- ⚠️ **Responsabilidad**: El usuario es responsable del uso de esta herramienta

### Riesgos de Seguridad

- Manipulación de interfaces de red puede afectar conectividad
- Ataques de deautenticación pueden interrumpir servicio WiFi
- El análisis puede ser detectado por sistemas de detección de intrusos
- Requiere permisos administrativos que otorgan acceso completo al sistema

### Recomendaciones

- Usa solo en entornos de laboratorio o redes propias
- Desconecta de redes públicas durante análisis
- Notifica a usuarios de redes antes de realizar pruebas
- Mantén herramientas actualizadas con últimos parches

## 📊 Especificaciones Técnicas

- **Protocolos soportados**: WPA, WPA2, WPA3 (limitado), WEP, Open
- **Frecuencias**: 2.4GHz, 5GHz (depende del hardware)
- **Formatos de captura**: .cap, .hccapx, .hc22000
- **Aceleración**: CUDA (NVIDIA), OpenCL (AMD/Intel)
- **Sistemas de archivos**: CAP, HCCAPX, HC22000, PMKID

## 🔐 Seguridad

- **Permisos elevados**: Requiere root/sudo para operaciones de red
- **Manipulación de hardware**: Control directo de interfaces WiFi
- **Captura de tráfico**: Intercepta paquetes de red
- **Almacenamiento de datos**: Guarda contraseñas y handshakes en disco
- **Sin encriptación de resultados**: Archivos almacenados en texto plano

## 📝 Archivos Generados

### Resultados de Análisis
- `passwords_encontradas.txt` - Contraseñas y hallazgos
- `aircrack-ng/*.cap` - Capturas de tráfico de red
- `aircrack-ng/*.hc22000` - Handshakes convertidos para análisis

### Logs y Directorios
- `aircrack-ng/` - Archivos temporales de captura
- `diccionarios/` - Wordlists para análisis de fuerza bruta
- `Documentacion/` - Documentación adicional y manuales

## 🤝 Estado del Proyecto

### Funcionalidades Actuales ✅
- Detección automática de interfaces WiFi
- Activación de modo monitor
- Escaneo y selección de redes
- Captura de handshake WPA/WPA2
- Conversión de formatos
- Análisis con hashcat
- Aceleración por GPU
- Guardado de resultados

### Funcionalidades Futuras 🚧
- Soporte WPA3 completo
- Análisis automático de vulnerabilidades
- Generación de reportes en PDF
- Interfaz gráfica
- Modo automatizado sin interacción
- Integración con bases de datos de contraseñas comprometidas

## 📄 Licencia

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)

Este proyecto está licenciado bajo la **Licencia GNU General Public License v3.0**.

### Texto de la Licencia

```
GNU GENERAL PUBLIC LICENSE
Version 3, 29 June 2007

Copyright (C) 2026 WiFi Audit Tool Project

Este programa es software libre: puede redistribuirlo y/o modificarlo bajo los términos
de la Licencia Pública General de GNU publicada por la Free Software Foundation, ya sea la
versión 3 de la Licencia, o (a su elección) cualquier versión posterior.

Este programa se distribuye con la esperanza de que sea útil, pero SIN NINGUNA GARANTÍA;
ni siquiera la garantía implícita de COMERCIABILIDAD O APTITUD PARA UN PROPÓSITO PARTICULAR.
Véase la Licencia Pública General de GNU para más detalles.

Debería haber recibido una copia de la Licencia Pública General de GNU junto con este programa.
Si no es así, consulte <https://www.gnu.org/licenses/>.
```

### Resumen de la Licencia

✅ **Permitido:**
- Uso comercial
- Modificación
- Distribución
- Uso privado
- Sublicencia (bajo los mismos términos)

❌ **Prohibido:**
- Responsabilidad
- Garantía
- Revocación de libertades
- Propiedad del software por terceros

⚠️ **Requerido:**
- Licencia y aviso de copyright
- Mismos términos (copyleft) en modificaciones
- Código fuente disponible
- Documentar cambios
- Distribuir la licencia con el software

### Características del Copyleft

La licencia GPL v3 es **copyleft**, lo que significa que:
- Cualquier modificación del software debe mantener la misma licencia
- Si distribuyes el software modificado, debes compartir el código fuente
- El software permanece libre para siempre
- Evita que el software se vuelva propietario

## 🔗 Recursos Relacionados

- [Documentación de aircrack-ng](https://www.aircrack-ng.org/documentation.html)
- [Documentación de hcxtools](https://github.com/ZerBea/hcxtools)
- [Documentación de hashcat](https://hashcat.net/wiki/)
- [Documentación/](./Documentacion/) - Documentación adicional del proyecto

## 📞 Soporte

Para problemas específicos de auditoría WiFi, consulta:
- Documentación oficial de aircrack-ng
- Foros de seguridad wireless
- Documentación de tu distribución Linux

---

**Versión**: 1.0  
**Última actualización**: 02/08/2026  
**Sistema probado**: CachyOS Linux 6.18.40-1-cachyos-lts  
**Hardware**: Tarjeta WiFi con modo monitor  
**Estado**: Auditoría funcional para redes propias