# auditar_wifi

Herramienta de auditoría WiFi automatizada.

Uso rápido
--------

Requisitos:

- Python 3
- aircrack-ng, hcxtools (hcxpcapngtool), hashcat

Ejecutar (como root):

```bash
sudo python3 auditar_wifi.py
```

Prueba local sin herramientas (simulador incluido):

1. Ejecuta el test harness que usa un `fake_hashcat` incluido:

```bash
python3 test_crack.py
```

Notas
-----

- La rama principal contiene mejoras a la barra de progreso y cálculo de ETA.
- Para contribuir: crea una rama, realiza cambios y abre un PR.

Licencia
-------

Revisa el repositorio antes de usarlo en entornos reales. Esta herramienta requiere permisos administrativos y herramientas externas.

