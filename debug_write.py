"""
Script para debuggear el problema de escritura con snap7
"""
import snap7
from snap7.util import *

def debug_write():
    print("=== DEBUG ESCRITURA SNAP7 ===")
    
    # Crear cliente
    client = snap7.client.Client()
    
    try:
        # Conectar
        print("Conectando...")
        client.connect("192.168.0.6", 0, 1)
        print("✓ Conectado")
        
        # Leer M0
        print("\nLeyendo M0...")
        data = client.mb_read(0, 1)
        print(f"Datos leídos: {data}, tipo: {type(data)}")
        
        if data:
            # Mostrar valor actual de cada bit
            for bit in range(8):
                try:
                    value = get_bool(data, 0, bit)
                    print(f"M0.{bit} = {value}")
                except Exception as e:
                    print(f"Error leyendo M0.{bit}: {e}")
        
        # Probar diferentes métodos de escritura
        print("\n--- PROBANDO MÉTODOS DE ESCRITURA ---")
        
        # Método 1: Usar la función directa de snap7
        print("\nMétodo 1: Función directa")
        try:
            # Crear datos de prueba
            test_data = bytearray([0b00000001])  # Solo bit 0 en True
            print(f"Datos a escribir: {test_data}")
            
            # Intentar escribir
            result = client.mb_write(0, test_data)
            print(f"Resultado mb_write: {result}")
            
            if result == 0:
                print("✓ Escritura exitosa con método 1")
            else:
                print(f"✗ Error en método 1: código {result}")
                
        except Exception as e:
            print(f"✗ Excepción en método 1: {e}")
        
        # Método 2: Usando bytes
        print("\nMétodo 2: Usando bytes()")
        try:
            test_data = bytearray([0b00000010])  # Solo bit 1 en True
            result = client.mb_write(0, bytes(test_data))
            print(f"Resultado mb_write con bytes(): {result}")
            
            if result == 0:
                print("✓ Escritura exitosa con método 2")
            else:
                print(f"✗ Error en método 2: código {result}")
                
        except Exception as e:
            print(f"✗ Excepción en método 2: {e}")
        
        # Método 3: Usando set_bool
        print("\nMétodo 3: Usando set_bool")
        try:
            # Leer datos actuales
            current_data = client.mb_read(0, 1)
            if current_data:
                # Convertir a bytearray
                data_to_write = bytearray(current_data)
                
                # Modificar bit 2
                set_bool(data_to_write, 0, 2, True)
                print(f"Datos modificados: {data_to_write}")
                
                # Escribir
                result = client.mb_write(0, data_to_write)
                print(f"Resultado mb_write con set_bool: {result}")
                
                if result == 0:
                    print("✓ Escritura exitosa con método 3")
                else:
                    print(f"✗ Error en método 3: código {result}")
            else:
                print("✗ No se pudieron leer datos actuales")
                
        except Exception as e:
            print(f"✗ Excepción en método 3: {e}")
        
        # Verificar resultados
        print("\n--- VERIFICANDO RESULTADOS ---")
        final_data = client.mb_read(0, 1)
        if final_data:
            print(f"Datos finales: {final_data}")
            for bit in range(8):
                try:
                    value = get_bool(final_data, 0, bit)
                    print(f"M0.{bit} = {value}")
                except Exception as e:
                    print(f"Error leyendo M0.{bit}: {e}")
        
    except Exception as e:
        print(f"Error general: {e}")
    
    finally:
        try:
            client.disconnect()
            print("\n✓ Desconectado")
        except:
            pass

if __name__ == "__main__":
    debug_write()
