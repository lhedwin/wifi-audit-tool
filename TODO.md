# TODO - Implementar menú principal en auditar_wifi.py

## Pasos a completar

- [x] 1. Analizar el código actual y crear plan
- [x] 2. Confirmar plan con el usuario
- [x] 3. Agregar función `show_menu()` con 3 opciones
- [x] 4. Agregar función `menu_capturar_handshake()` con flujo completo de captura + mostrar .hc22000
- [x] 5. Agregar función `menu_descifrar_password()` para descifrar .hc22000 existente (con submenú de métodos de ataque)
- [x] 6. Refactorizar `main()` para usar el loop del menú
- [x] 7. Verificar sintaxis con `python3 -m py_compile auditar_wifi.py`
- [x] 8. Restaurar `crack_password_hibrido_espanol()` (ataque híbrido diccionario español + sufijo 4 dígitos)
- [x] 9. Restaurar `save_password()` y reparar código corrupto
- [x] 10. Corregir bug en opción 2 del submenú (falta `with open(...)`)
- [x] 11. Corregir import roto `from . import parse_duration_to_seconds`
- [x] 12. Manejar el retorno `"__VOLVER__"` en `menu_capturar_handshake()`

## Tarea adicional: Opción 7 del submenú permite elegir diccionario

- [x] Agregar parámetro `diccionario_path=None` a `crack_password_hibrido_espanol()` (usa español.txt por defecto)
- [x] Crear función auxiliar `seleccionar_diccionario()` reutilizable
- [x] Refactorizar opciones 5 y 6 para usar `seleccionar_diccionario()`
- [x] Modificar opción 7 para permitir elegir el diccionario antes del ataque híbrido
- [x] Verificar sintaxis (`py_compile` OK)
- [x] Agregar lectura de temperaturas CPU/GPU a la barra de progreso de la opción 7 (híbrido)
- [x] Renombrar opciones del submenú de ataques con los nombres nuevos (1-7)

## Estado: COMPLETADO

## Resumen de cambios en auditar_wifi.py (3296 líneas)

- **`show_menu()`**: Menú principal con 3 opciones (1-Capturar, 2-Descifrar, 3-Salir)
- **`menu_capturar_handshake()`**: Flujo completo de captura + muestra nombre del archivo .hc22000
- **`menu_descifrar_password()`**: Selección de archivo .hc22000 + submenú con 9 métodos de ataque
- **`main()`**: Loop del menú principal que retorna al inicio tras cada operación
- **`crack_password_hibrido_espanol()`**: Restaurada (ataque híbrido diccionario español + sufijo 4 dígitos)
- **`save_password()`**: Restaurada correctamente
