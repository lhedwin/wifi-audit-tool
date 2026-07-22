import os

def generar_reglas_hashcat(nombre_archivo="append_00_99.rule"):
    """
    Genera un archivo de reglas para Hashcat que añade dos dígitos 
    (00-99) al final de cada palabra de la lista.
    """
    
    # Lista para almacenar las reglas
    reglas = []
    
    # El bucle va de 0 a 99 (100 iteraciones)
    for i in range(100):
        # Formatea el número a dos dígitos, rellenando con un cero a la izquierda si es necesario.
        # Por ejemplo: 0 -> '00', 5 -> '05', 99 -> '99'
        digitos = f"{i:02d}"
        
        # La regla de Hashcat para añadir texto: '$' + el texto a añadir
        # Por ejemplo, para añadir '42', la regla es $42
        regla = f"${digitos}"
        
        reglas.append(regla)
    
    try:
        # Abre y escribe todas las reglas en el archivo
        with open(nombre_archivo, 'w') as f:
            f.write('\n'.join(reglas) + '\n') # Escribe todas las reglas separadas por saltos de línea
        
        print(f"✅ Archivo de reglas '{nombre_archivo}' generado con éxito.")
        print(f"   Se generaron {len(reglas)} reglas (del $00 al $99).")
        print("   ¡Listo para usar con Hashcat!")
        
    except IOError as e:
        print(f"❌ Error al escribir el archivo: {e}")

if __name__ == "__main__":
    generar_reglas_hashcat()
