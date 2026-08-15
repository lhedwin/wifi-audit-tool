#!/bin/bash
# Script para iniciar HP Omen Monitor

cd /home/lhedwin/Programacion/Git/MonitoreoPC

echo "Iniciando HP Omen Monitor..."
echo "DISPLAY: $DISPLAY"
echo "Wayland: $WAYLAND_DISPLAY"

# Verificar entorno gráfico
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    echo "Error: No se detectó entorno gráfico"
    echo "Este script debe ejecutarse desde una sesión gráfica"
    exit 1
fi

# Ejecutar el programa
python3 omen_fan_tray.py --debug

echo "HP Omen Monitor iniciado"
