"""
Módulo para manejar la conexión con el PLC Siemens S7-1200
"""
import snap7
from snap7.util import *
import struct
import logging

class PLCConnection:
    def __init__(self):
        self.client = snap7.client.Client()
        self.connected = False
        self.ip_address = "192.168.1.100"  # IP por defecto, se puede cambiar
        self.rack = 0
        self.slot = 1
        
        # Configurar logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def connect(self, ip_address=None, rack=0, slot=1):
        """Conectar al PLC S7-1200"""
        try:
            if ip_address:
                self.ip_address = ip_address
            self.rack = rack
            self.slot = slot
            
            self.client.connect(self.ip_address, self.rack, self.slot)
            self.connected = True
            self.logger.info(f"Conectado al PLC en {self.ip_address}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error al conectar: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Desconectar del PLC"""
        try:
            if self.connected:
                self.client.disconnect()
                self.connected = False
                self.logger.info("Desconectado del PLC")
        except Exception as e:
            self.logger.error(f"Error al desconectar: {e}")
    
    def is_connected(self):
        """Verificar si está conectado"""
        return self.connected and self.client.get_connected()
    
    def read_db(self, db_number, start, size):
        """Leer datos de un Data Block"""
        
        try:
            if not self.is_connected():
                return None
            
            data = self.client.db_read(db_number, start, size)
            return data
            
        except Exception as e:
            self.logger.error(f"Error leyendo DB{db_number}: {e}")
            return None
    
    def write_db(self, db_number, start, data):
        """Escribir datos a un Data Block"""
        try:
            if not self.is_connected():
                return False
            
            self.client.db_write(db_number, start, data)
            return True
            
        except Exception as e:
            self.logger.error(f"Error escribiendo DB{db_number}: {e}")
            return False
    
    def read_bool(self, db_number, start, bit):
        """Leer un valor booleano"""
        try:
            data = self.read_db(db_number, start, 1)
            if data:
                return get_bool(data, 0, bit)
            return False
        except Exception as e:
            self.logger.error(f"Error leyendo bool: {e}")
            return False
    
    def write_bool(self, db_number, start, bit, value):
        """Escribir un valor booleano"""
        try:
            data = self.read_db(db_number, start, 1)
            if data:
                set_bool(data, 0, bit, value)
                return self.write_db(db_number, start, data)
            return False
        except Exception as e:
            self.logger.error(f"Error escribiendo bool: {e}")
            return False
    
    def read_int(self, db_number, start):
        """Leer un valor entero (16 bits)"""
        try:
            data = self.read_db(db_number, start, 2)
            if data:
                return get_int(data, 0)
            return 0
        except Exception as e:
            self.logger.error(f"Error leyendo int: {e}")
            return 0
    
    def write_int(self, db_number, start, value):
        """Escribir un valor entero (16 bits)"""
        try:
            data = bytearray(2)
            set_int(data, 0, value)
            return self.write_db(db_number, start, data)
        except Exception as e:
            self.logger.error(f"Error escribiendo int: {e}")
            return False
    
    def read_real(self, db_number, start):
        """Leer un valor real (32 bits float)"""
        try:
            data = self.read_db(db_number, start, 4)
            if data:
                return get_real(data, 0)
            return 0.0
        except Exception as e:
            self.logger.error(f"Error leyendo real: {e}")
            return 0.0
    
    def write_real(self, db_number, start, value):
        """Escribir un valor real (32 bits float)"""
        try:
            data = bytearray(4)
            set_real(data, 0, value)
            return self.write_db(db_number, start, data)
        except Exception as e:
            self.logger.error(f"Error escribiendo real: {e}")
            return False
    
    def get_cpu_info(self):
        """Obtener información del CPU"""
        try:
            if self.is_connected():
                return self.client.get_cpu_info()
            return None
        except Exception as e:
            self.logger.error(f"Error obteniendo info CPU: {e}")
            return None
    
    # ========== MÉTODOS PARA TAGS GLOBALES ==========
    
    def read_input(self, address, bit=None):
        """Leer entrada digital (I) - Ejemplo: I0.0, I1.2"""
        try:
            if not self.is_connected():
                return None
            
            if bit is not None:
                # Leer bit específico
                data = self.client.eb_read(address, 1)
                return get_bool(data, 0, bit)
            else:
                # Leer byte completo
                return self.client.eb_read(address, 1)
                
        except Exception as e:
            self.logger.error(f"Error leyendo entrada I{address}.{bit}: {e}")
            return None
    
    def read_output(self, address, bit=None):
        """Leer salida digital (Q) - Ejemplo: Q0.0, Q1.2"""
        try:
            if not self.is_connected():
                return None
            
            if bit is not None:
                # Leer bit específico
                data = self.client.ab_read(address, 1)
                return get_bool(data, 0, bit)
            else:
                # Leer byte completo
                return self.client.ab_read(address, 1)
                
        except Exception as e:
            self.logger.error(f"Error leyendo salida Q{address}.{bit}: {e}")
            return None
    
    def write_output(self, address, bit, value):
        """Escribir salida digital (Q) - Ejemplo: Q0.0 = True"""
        try:
            if not self.is_connected():
                return False
            
            # Leer el byte actual
            data = self.client.ab_read(address, 1)
            if data is None:
                self.logger.error(f"No se pudo leer Q{address} para escritura")
                return False
            
            # Convertir a bytearray si es necesario
            if not isinstance(data, bytearray):
                data = bytearray(data)
            
            # Modificar el bit específico
            set_bool(data, 0, bit, value)
            # Escribir de vuelta (address, size, data)
            result = self.client.ab_write(address, len(data), data)
            return result == 0
            
        except Exception as e:
            self.logger.error(f"Error escribiendo salida Q{address}.{bit}: {e}")
            return False
    
    def read_memory(self, address, bit=None):
        """Leer marca de memoria (M) - Ejemplo: M0.0, M1.2"""
        try:
            if not self.is_connected():
                return None
            
            if bit is not None:
                # Leer bit específico
                data = self.client.mb_read(address, 1)
                return get_bool(data, 0, bit)
            else:
                # Leer byte completo
                return self.client.mb_read(address, 1)
                
        except Exception as e:
            self.logger.error(f"Error leyendo marca M{address}.{bit}: {e}")
            return None
    
    def write_memory(self, address, bit, value):
        """Escribir marca de memoria (M) - Ejemplo: M0.0 = True"""
        try:
            if not self.is_connected():
                return False
            
            # Leer el byte actual
            data = self.client.mb_read(address, 1)
            if data is None:
                self.logger.error(f"No se pudo leer M{address} para escritura")
                return False
            
            # Asegurar que data es bytearray
            if not isinstance(data, bytearray):
                data = bytearray(data)
            
            # Modificar el bit específico
            set_bool(data, 0, bit, value)
            
            # Escribir usando el método correcto para S7-1200 (address, size, data)
            result = self.client.mb_write(address, len(data), data)
            
            # Verificar resultado
            if result == 0:  # 0 significa éxito en snap7
                return True
            else:
                self.logger.error(f"Error en mb_write: código {result}")
                return False
            
        except Exception as e:
            self.logger.error(f"Error escribiendo marca M{address}.{bit}: {e}")
            return False
    
    def read_analog_input(self, address):
        """Leer entrada analógica (IW) - Ejemplo: IW64"""
        try:
            if not self.is_connected():
                return None
            
            data = self.client.eb_read(address, 2)
            return get_int(data, 0)
            
        except Exception as e:
            self.logger.error(f"Error leyendo entrada analógica IW{address}: {e}")
            return None
    
    def read_analog_output(self, address):
        """Leer salida analógica (QW) - Ejemplo: QW64"""
        try:
            if not self.is_connected():
                return None
            
            data = self.client.ab_read(address, 2)
            return get_int(data, 0)
            
        except Exception as e:
            self.logger.error(f"Error leyendo salida analógica QW{address}: {e}")
            return None
    
    def write_analog_output(self, address, value):
        """Escribir salida analógica (QW) - Ejemplo: QW64 = 1000"""
        try:
            if not self.is_connected():
                return False
            
            data = bytearray(2)
            set_int(data, 0, value)
            result = self.client.ab_write(address, len(data), data)
            return result == 0
            
        except Exception as e:
            self.logger.error(f"Error escribiendo salida analógica QW{address}: {e}")
            return False
    
    def read_global_tag(self, tag_type, address, bit=None):
        """Método genérico para leer tags globales
        
        Args:
            tag_type: 'I', 'Q', 'M', 'IW', 'QW', 'MW', 'DB'
            address: dirección del tag
            bit: bit específico (solo para tipos digitales)
        """
        try:
            if tag_type.upper() == 'I':
                return self.read_input(address, bit)
            elif tag_type.upper() == 'Q':
                return self.read_output(address, bit)
            elif tag_type.upper() == 'M':
                return self.read_memory(address, bit)
            elif tag_type.upper() == 'IW':
                return self.read_analog_input(address)
            elif tag_type.upper() == 'QW':
                return self.read_analog_output(address)
            elif tag_type.upper() == 'MW':
                # Leer palabra de memoria
                data = self.client.mb_read(address, 2)
                return get_int(data, 0)
            else:
                self.logger.error(f"Tipo de tag no soportado: {tag_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error leyendo tag global {tag_type}{address}: {e}")
            return None
    
    def write_global_tag(self, tag_type, address, value, bit=None):
        """Método genérico para escribir tags globales
        
        Args:
            tag_type: 'Q', 'M', 'QW', 'MW' (solo tags escribibles)
            address: dirección del tag
            value: valor a escribir
            bit: bit específico (solo para tipos digitales)
        """
        try:
            if tag_type.upper() == 'Q':
                return self.write_output(address, bit, value)
            elif tag_type.upper() == 'M':
                return self.write_memory(address, bit, value)
            elif tag_type.upper() == 'QW':
                return self.write_analog_output(address, value)
            elif tag_type.upper() == 'MW':
                # Escribir palabra de memoria
                data = bytearray(2)
                set_int(data, 0, value)
                result = self.client.mb_write(address, len(data), data)
                return result == 0
            else:
                self.logger.error(f"Tipo de tag no escribible o no soportado: {tag_type}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error escribiendo tag global {tag_type}{address}: {e}")
            return False
    
    # ========== MÉTODOS DE DIAGNÓSTICO ==========
    
    def test_address_range(self, tag_type, start_addr=0, end_addr=10):
        """Probar rango de direcciones para encontrar las disponibles"""
        available_addresses = []
        
        if not self.is_connected():
            self.logger.error("No hay conexión para probar direcciones")
            return available_addresses
        
        for addr in range(start_addr, end_addr + 1):
            try:
                if tag_type.upper() == 'I':
                    data = self.client.eb_read(addr, 1)
                elif tag_type.upper() == 'Q':
                    data = self.client.ab_read(addr, 1)
                elif tag_type.upper() == 'M':
                    data = self.client.mb_read(addr, 1)
                elif tag_type.upper() == 'DB':
                    data = self.client.db_read(addr, 0, 1)
                else:
                    continue
                
                if data is not None:
                    available_addresses.append(addr)
                    self.logger.info(f"Dirección disponible: {tag_type}{addr}")
                    
            except Exception as e:
                self.logger.debug(f"Dirección no disponible: {tag_type}{addr} - {e}")
                continue
        
        return available_addresses
    
    def get_plc_status(self):
        """Obtener estado detallado del PLC"""
        if not self.is_connected():
            return None
        
        try:
            cpu_info = self.client.get_cpu_info()
            cpu_state = self.client.get_cpu_state()
            
            status = {
                'cpu_info': cpu_info,
                'cpu_state': cpu_state,
                'connection': 'OK'
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error obteniendo estado del PLC: {e}")
            return {'error': str(e)}
    
    def safe_read_test(self):
        """Realizar pruebas seguras de lectura"""
        test_results = {
            'I': [],
            'Q': [],
            'M': [],
            'DB': []
        }
        
        if not self.is_connected():
            return test_results
        
        # Probar direcciones básicas
        for tag_type in ['I', 'Q', 'M']:
            test_results[tag_type] = self.test_address_range(tag_type, 0, 5)
        
        # Probar algunos DBs comunes
        for db_num in [1, 2, 10, 100]:
            try:
                data = self.client.db_read(db_num, 0, 1)
                if data is not None:
                    test_results['DB'].append(db_num)
            except:
                continue
        
        return test_results
