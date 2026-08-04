# SPDX-License-Identifier: GPL-3.0-or-later
import os

def generar_reglas_especiales_hashcat(nombre_archivo="append_00_99_special.rule"):
    """
    Genera un archivo de reglas para Hashcat que añade dos dígitos (00-99) 
    seguidos de un carácter especial al final de cada palabra.
    """
    
    # Conjunto de caracteres especiales comunes.
    caracteres_especiales = r"!@#$%^&*()_+-=[]\{}|;':\",./<>?`~" 
    
    reglas = []
    
    # 1. Bucle para los 100 números (00 a 99)
    for i in range(100):
        digitos = f"{i:02d}"
        
        # 2. Bucle para cada carácter especial
        for char in caracteres_especiales:
            # La regla de Hashcat: '$' + texto_a_añadir
            # Por ejemplo: $42!
            regla = f"${digitos}{char}"
            reglas.append(regla)
    
    try:
        # Abre y escribe todas las reglas en el archivo
        with open(nombre_archivo, 'w', encoding='utf-8') as f:
            f.write('\n'.join(reglas) + '\n')
        
        print(f"✅ Archivo de reglas '{nombre_archivo}' generado con éxito.")
        print(f"   Se generaron {len(reglas)} reglas (100 números x {len(caracteres_especiales)} caracteres).")
        print("   ¡Las combinaciones son mucho más potentes ahora! 🚀")
        
    except IOError as e:
        print(f"❌ Error al escribir el archivo: {e}")

if __name__ == "__main__":
    generar_reglas_especiales_hashcat()
