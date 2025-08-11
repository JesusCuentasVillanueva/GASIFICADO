"""
Script de prueba simple para verificar la conexión y escritura al PLC
"""
from plc_connection import PLCConnection
import time

def test_plc_connection():
    print("=== PRUEBA DE CONEXIÓN PLC S7-1200 ===")
    
    # Crear conexión
    plc = PLCConnection()
    
    # Conectar
    print("Intentando conectar al PLC...")
    if plc.connect("192.168.0.6", 0, 1):
        print("✓ Conexión exitosa!")
        
        # Obtener información del PLC
        print("\n--- Información del PLC ---")
        status = plc.get_plc_status()
        if status:
            print(f"Estado: {status}")
        
        # Probar direcciones disponibles
        print("\n--- Probando direcciones disponibles ---")
        test_results = plc.safe_read_test()
        
        for tag_type, addresses in test_results.items():
            if addresses:
                print(f"{tag_type}: {addresses}")
            else:
                print(f"{tag_type}: No disponible")
        
        # Probar escritura simple si hay direcciones M disponibles
        if test_results.get('M'):
            print("\n--- Probando escritura en marcas M ---")
            m_addr = test_results['M'][0]  # Primera dirección M disponible
            
            print(f"Probando escritura en M{m_addr}.0...")
            
            # Leer valor actual
            try:
                current_value = plc.read_memory(m_addr, 0)
                print(f"Valor actual M{m_addr}.0: {current_value}")
                
                # Escribir valor opuesto
                new_value = not current_value if current_value is not None else True
                print(f"Escribiendo valor {new_value} en M{m_addr}.0...")
                
                success = plc.write_memory(m_addr, 0, new_value)
                if success:
                    print("✓ Escritura exitosa!")
                    
                    # Verificar escritura
                    time.sleep(0.1)
                    verify_value = plc.read_memory(m_addr, 0)
                    print(f"Valor verificado M{m_addr}.0: {verify_value}")
                    
                    if verify_value == new_value:
                        print("✓ Verificación exitosa!")
                    else:
                        print("✗ Verificación falló")
                else:
                    print("✗ Error en escritura")
                    
            except Exception as e:
                print(f"✗ Error en prueba de escritura: {e}")
        
        # Desconectar
        plc.disconnect()
        print("\n✓ Desconectado del PLC")
        
    else:
        print("✗ Error de conexión")
        return False
    
    return True

if __name__ == "__main__":
    test_plc_connection()
