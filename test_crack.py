#!/usr/bin/env python3
import os
import sys
cwd = os.path.dirname(__file__)
env = os.environ.copy()
env['PATH'] = cwd + os.pathsep + env.get('PATH', '')
# Crear archivo hc22000 dummy
hc = os.path.join(cwd, 'test.hc22000')
with open(hc, 'w') as f:
    f.write('FAKEHASH')

# Ejecutar la función crack_password del script principal
sys.path.insert(0, cwd)
import auditar_wifi

print('\n== INICIANDO PRUEBA DE crack_password() CON SIMULADOR ==\n')
res = auditar_wifi.crack_password(hc, 'TEST_ESSID')
print('\n== RESULTADO DE PRUEBA ==')
print('password devuelto:', res)
