# auditar_wifi

Herramienta de auditoría WiFi automatizada para pruebas de seguridad en redes wireless.

## Descripción

**WIFI AUDIT TOOL v1.0** es un script de Python que automatiza el proceso de auditoría de redes WiFi, desde la identificación de interfaces hasta el crackeo de contraseñas mediante fuerza bruta. Utiliza herramientas de seguridad WiFi como aircrack-ng, hcxtools y hashcat.

## Flujo de operación

1. **Identificar interfaces WiFi**: Detecta y muestra las interfaces WiFi disponibles con información completa (PHY, Driver, Chipset, bandas 2.4/5GHz)
2. **Activar modo monitor**: Configura la interfaz seleccionada en modo monitor para capturar tráfico
3. **Escanear redes**: Realiza un escaneo de 15 segundos y muestra las redes ordenadas por intensidad de señal
4. **Seleccionar redes a auditar**: Permite seleccionar múltiples redes desde una lista numerada (puedes usar rangos como 2-6)
5. **Capturar handshake**: Utiliza airodump-ng y aireplay-ng para capturar el handshake WPA/WPA2 mediante ataques de deautenticación
6. **Convertir formato**: Convierte el archivo .cap a .hc22000 usando hcxpcapngtool
7. **Crackear con hashcat**: Realiza ataque de fuerza bruta con máscara de 8 dígitos numéricos
8. **Mostrar resultados**: Muestra la contraseña encontrada o permite continuar con otras redes

## Requisitos

- Python 3
- aircrack-ng (airmon-ng, airodump-ng, aireplay-ng)
- hcxtools (hcxpcapngtool)
- hashcat
- Permisos de root/sudo

## Instalación de dependencias

```bash
sudo apt update
sudo apt install aircrack-ng hcxtools hashcat
```

## Uso

### Ejecución principal (requiere root)

```bash
sudo python3 auditar_wifi.py
```

### Prueba local sin herramientas (simulador)

Para pruebas sin necesidad de hardware WiFi real:

```bash
python3 test_crack.py
```

## Características

- **Detección automática de interfaces**: Identifica PHY, driver, chipset y bandas soportadas
- **Recomendación de interfaz**: Sugiere usar interfaces que no soporten 5GHz para mejor estabilidad en modo monitor
- **Selección múltiple de redes**: Permite auditar varias redes en una sola sesión usando rangos (ej: 1,3,5-8)
- **Captura inteligente de handshake**: Implementa múltiples fases de deautenticación (broadcast y específica por cliente)
- **Detección en tiempo real**: Verifica la captura del handshake durante el proceso
- **Auto-detección de GPU**: Utiliza GPU NVIDIA si está disponible para acelerar el crackeo
- **Barra de progreso con ETA**: Muestra progreso y tiempo estimado restante durante el crackeo
- **Guardado de contraseñas**: Las contraseñas encontradas se guardan en `passwords_encontradas.txt`

## Estructura de archivos

- `auditar_wifi.py` - Script principal de auditoría
- `passwords_encontradas.txt` - Archivo donde se guardan las contraseñas crackeadas
- `aircrack-ng/` - Directorio para archivos temporales de captura
- `diccionarios/` - Directorio con wordlists (español.txt, crackstation.txt, breach.txt, etc.)

## Notas de seguridad

- Esta herramienta debe utilizarse **únicamente** en redes que poseas o tengas autorización explícita para auditar
- El uso no autorizado de herramientas de auditoría WiFi es ilegal en la mayoría de jurisdicciones
- La herramienta requiere permisos administrativos y manipula interfaces de red
- Revise la legislación local antes de usarla en entornos reales

## Contribución

Para contribuir al proyecto:
1. Crea una rama nueva
2. Realiza tus cambios
3. Abre un Pull Request

## Licencia

Revisa el repositorio antes de usarlo en entornos reales. Esta herramienta requiere permisos administrativos y herramientas externas de seguridad.

