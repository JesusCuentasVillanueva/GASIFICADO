# Monitor PLC S7-1200 con PyQt5

Esta aplicación permite conectarse y monitorear un PLC Siemens S7-1200 usando una interfaz gráfica desarrollada en PyQt5.

## Características

- **Conexión TCP/IP**: Conecta al PLC usando la librería snap7
- **Monitoreo en tiempo real**: Visualiza valores de tags automáticamente
- **Lectura/Escritura**: Lee y escribe valores booleanos, enteros y reales
- **Interfaz intuitiva**: Interfaz gráfica moderna con tema oscuro
- **Tags dinámicos**: Agrega nuevos tags sin reiniciar la aplicación

## Requisitos

- Python 3.7+
- PyQt5
- python-snap7
- PLC Siemens S7-1200 con comunicación Ethernet habilitada

## Instalación

1. Instalar las dependencias:
```bash
pip install -r requirements.txt
```

2. Configurar el PLC:
   - Habilitar comunicación Ethernet en TIA Portal
   - Configurar la IP del PLC (por defecto: 192.168.1.100)
   - Permitir acceso PUT/GET en la configuración de protección

## Uso

1. Ejecutar la aplicación:
```bash
python plc_gui.py
```

2. Configurar la conexión:
   - Ingresar la IP del PLC
   - Configurar Rack (normalmente 0) y Slot (normalmente 1)
   - Hacer clic en "Conectar"

3. Monitorear tags:
   - Los tags por defecto aparecerán automáticamente
   - Agregar nuevos tags usando el panel "Agregar Tag"
   - Los valores se actualizan cada segundo

## Tags por Defecto

La aplicación incluye estos tags de ejemplo:
- `Motor_Estado` (DB1.DBX0.0) - Boolean
- `Temperatura` (DB1.DBD2) - Real
- `Contador` (DB1.DBW6) - Integer
- `Alarma` (DB1.DBX8.0) - Boolean

## Configuración del PLC

En TIA Portal, asegúrate de:

1. **Crear Data Blocks**: Crear DB1 con las variables correspondientes
2. **Configurar Ethernet**: Asignar IP estática al PLC
3. **Habilitar comunicación**: En "Protection & Security" permitir PUT/GET
4. **Compilar y descargar**: Transferir el programa al PLC

## Estructura del Proyecto

```
GASIFICADO/
├── plc_connection.py    # Módulo de conexión PLC
├── plc_gui.py          # Interfaz gráfica principal
├── requirements.txt    # Dependencias
└── README.md          # Este archivo
```

## Solución de Problemas

### Error de conexión
- Verificar que el PLC esté encendido y conectado a la red
- Comprobar la IP del PLC en TIA Portal
- Verificar que no haya firewall bloqueando el puerto 102

### Error de lectura/escritura
- Verificar que los Data Blocks existan en el PLC
- Comprobar que las direcciones de memoria sean correctas
- Asegurar que PUT/GET esté habilitado

### Dependencias
Si hay problemas con snap7:
- En Windows: Descargar snap7.dll y colocar en System32
- En Linux: Instalar libsnap7-dev

## Tipos de Datos Soportados

- **Bool**: Valores booleanos (True/False)
- **Int**: Enteros de 16 bits (-32768 a 32767)
- **Real**: Números de punto flotante de 32 bits

## Contribuir

Para contribuir al proyecto:
1. Fork el repositorio
2. Crear una rama para tu feature
3. Hacer commit de los cambios
4. Crear un Pull Request
