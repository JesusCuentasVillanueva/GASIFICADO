"""
Interfaz gráfica PyQt5 para monitoreo y control del PLC S7-1200
"""
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import threading
import time
import json
import os
from plc_connection import PLCConnection

class PLCMonitorThread(QThread):
    """Thread para monitoreo continuo del PLC"""
    data_updated = pyqtSignal(dict)
    connection_status = pyqtSignal(bool)
    
    def __init__(self, plc_connection):
        super().__init__()
        self.plc = plc_connection
        self.running = False
        self.monitoring_tags = []
    
    def add_tag(self, tag_name, tag_type, address, data_type, bit=None, db_number=None):
        """Agregar tag para monitoreo
        
        Args:
            tag_name: nombre del tag
            tag_type: 'DB', 'I', 'Q', 'M', 'IW', 'QW', 'MW'
            address: dirección del tag
            data_type: 'bool', 'int', 'real'
            bit: bit específico (para tipos digitales)
            db_number: número de DB (solo para tipo 'DB')
        """
        tag = {
            'name': tag_name,
            'tag_type': tag_type,
            'address': address,
            'data_type': data_type,
            'bit': bit,
            'db_number': db_number
        }
        self.monitoring_tags.append(tag)
    
    def run(self):
        self.running = True
        while self.running:
            if self.plc.is_connected():
                data = {}
                for tag in self.monitoring_tags:
                    try:
                        if tag['tag_type'] == 'DB':
                            # Tags de Data Block (método original)
                            if tag['data_type'] == 'bool':
                                value = self.plc.read_bool(tag['db_number'], tag['address'], tag['bit'])
                            elif tag['data_type'] == 'int':
                                value = self.plc.read_int(tag['db_number'], tag['address'])
                            elif tag['data_type'] == 'real':
                                value = self.plc.read_real(tag['db_number'], tag['address'])
                            else:
                                value = None
                        else:
                            # Tags globales (I, Q, M, IW, QW, MW)
                            value = self.plc.read_global_tag(tag['tag_type'], tag['address'], tag['bit'])
                        
                        data[tag['name']] = value
                    except Exception as e:
                        data[tag['name']] = f"Error: {e}"
                
                self.data_updated.emit(data)
                self.connection_status.emit(True)
            else:
                self.connection_status.emit(False)
            
            time.sleep(1)  # Actualizar cada segundo
    
    def stop(self):
        self.running = False

class TagWidget(QWidget):
    """Widget para mostrar y controlar un tag individual"""
    value_changed = pyqtSignal(str, object)
    edit_requested = pyqtSignal(str)  # Señal para solicitar edición del tag
    
    def __init__(self, tag_name, data_type, read_only=False):
        super().__init__()
        self.tag_name = tag_name
        self.data_type = data_type
        self.read_only = read_only
        self.init_ui()
    
    def init_ui(self):
        layout = QHBoxLayout()
        
        # Etiqueta del tag
        self.label = QLabel(f"{self.tag_name}:")
        self.label.setFixedWidth(150)
        layout.addWidget(self.label)
        
        # Control según el tipo de dato
        if self.data_type == 'bool':
            self.control = QCheckBox()
            if not self.read_only:
                self.control.stateChanged.connect(self.on_bool_changed)
        elif self.data_type == 'int':
            self.control = QSpinBox()
            self.control.setRange(-32768, 32767)
            if not self.read_only:
                self.control.valueChanged.connect(self.on_int_changed)
        elif self.data_type == 'real':
            self.control = QDoubleSpinBox()
            self.control.setRange(-999999.99, 999999.99)
            self.control.setDecimals(2)
            if not self.read_only:
                self.control.valueChanged.connect(self.on_real_changed)
        
        if self.read_only:
            self.control.setEnabled(False)
        
        layout.addWidget(self.control)
        
        # Indicador de estado
        self.status_label = QLabel("●")
        self.status_label.setStyleSheet("color: gray; font-size: 16px;")
        layout.addWidget(self.status_label)
        
        # Botón de editar
        self.edit_btn = QPushButton("✎")
        self.edit_btn.setFixedSize(25, 25)
        self.edit_btn.setToolTip("Editar tag")
        self.edit_btn.clicked.connect(self.on_edit_clicked)
        layout.addWidget(self.edit_btn)
        
        self.setLayout(layout)
    
    def update_value(self, value):
        """Actualizar el valor mostrado"""
        if value is not None and not isinstance(value, str):
            if self.data_type == 'bool':
                self.control.setChecked(bool(value))
            elif self.data_type == 'int':
                self.control.setValue(int(value))
            elif self.data_type == 'real':
                self.control.setValue(float(value))
            
            self.status_label.setStyleSheet("color: green; font-size: 16px;")
        else:
            self.status_label.setStyleSheet("color: red; font-size: 16px;")
    
    def on_bool_changed(self, state):
        self.value_changed.emit(self.tag_name, bool(state))
    
    def on_int_changed(self, value):
        self.value_changed.emit(self.tag_name, int(value))
    
    def on_real_changed(self, value):
        self.value_changed.emit(self.tag_name, float(value))
    
    def on_edit_clicked(self):
        """Manejar clic en botón de editar"""
        self.edit_requested.emit(self.tag_name)

class PLCMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.plc = PLCConnection()
        self.monitor_thread = None
        self.tag_widgets = {}
        self.config_file = "plc_tags_config.json"
        self.init_ui()
        self.load_tags_from_config()  # Cargar tags guardados en lugar de setup_default_tags()
    
    def init_ui(self):
        self.setWindowTitle("Monitor PLC S7-1200")
        self.setGeometry(100, 100, 800, 600)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Panel de conexión
        connection_group = QGroupBox("Conexión PLC")
        connection_layout = QHBoxLayout()
        
        self.ip_input = QLineEdit("192.168.1.100")
        self.ip_input.setPlaceholderText("IP del PLC")
        connection_layout.addWidget(QLabel("IP:"))
        connection_layout.addWidget(self.ip_input)
        
        self.rack_input = QSpinBox()
        self.rack_input.setValue(0)
        connection_layout.addWidget(QLabel("Rack:"))
        connection_layout.addWidget(self.rack_input)
        
        self.slot_input = QSpinBox()
        self.slot_input.setValue(1)
        connection_layout.addWidget(QLabel("Slot:"))
        connection_layout.addWidget(self.slot_input)
        
        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(self.toggle_connection)
        connection_layout.addWidget(self.connect_btn)
        
        self.diagnose_btn = QPushButton("Diagnosticar PLC")
        self.diagnose_btn.clicked.connect(self.diagnose_plc)
        self.diagnose_btn.setEnabled(False)
        connection_layout.addWidget(self.diagnose_btn)
        
        self.status_label = QLabel("Desconectado")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        connection_layout.addWidget(self.status_label)
        
        connection_group.setLayout(connection_layout)
        main_layout.addWidget(connection_group)
        
        # Panel de tags
        tags_group = QGroupBox("Tags del PLC")
        self.tags_layout = QVBoxLayout()
        tags_group.setLayout(self.tags_layout)
        main_layout.addWidget(tags_group)
        
        # Panel de control de tags
        control_group = QGroupBox("Agregar Tag")
        control_layout = QVBoxLayout()
        
        # Primera fila: Nombre y Tipo de Tag
        row1_layout = QHBoxLayout()
        self.tag_name_input = QLineEdit()
        self.tag_name_input.setPlaceholderText("Nombre del tag")
        row1_layout.addWidget(QLabel("Nombre:"))
        row1_layout.addWidget(self.tag_name_input)
        
        self.tag_type_combo = QComboBox()
        self.tag_type_combo.addItems(["I (Entrada)", "Q (Salida)", "M (Marca)", "IW (Entrada Analógica)", "QW (Salida Analógica)", "MW (Palabra Memoria)", "DB (Data Block)"])
        self.tag_type_combo.currentTextChanged.connect(self.on_tag_type_changed)
        row1_layout.addWidget(QLabel("Tipo Tag:"))
        row1_layout.addWidget(self.tag_type_combo)
        control_layout.addLayout(row1_layout)
        
        # Segunda fila: Dirección y configuraciones específicas
        row2_layout = QHBoxLayout()
        self.address_input = QSpinBox()
        self.address_input.setRange(0, 8190)
        row2_layout.addWidget(QLabel("Dirección:"))
        row2_layout.addWidget(self.address_input)
        
        self.bit_input = QSpinBox()
        self.bit_input.setRange(0, 7)
        self.bit_label = QLabel("Bit:")
        row2_layout.addWidget(self.bit_label)
        row2_layout.addWidget(self.bit_input)
        
        # Para Data Blocks
        self.db_input = QSpinBox()
        self.db_input.setRange(1, 999)
        self.db_input.setValue(1)
        self.db_label = QLabel("DB:")
        row2_layout.addWidget(self.db_label)
        row2_layout.addWidget(self.db_input)
        
        self.data_type_combo = QComboBox()
        self.data_type_combo.addItems(["bool", "int", "real"])
        row2_layout.addWidget(QLabel("Tipo Dato:"))
        row2_layout.addWidget(self.data_type_combo)
        control_layout.addLayout(row2_layout)
        
        # Tercera fila: Etiqueta de ejemplo y botón
        row3_layout = QHBoxLayout()
        self.example_label = QLabel("Ejemplo: Q0.0 (Salida digital)")
        self.example_label.setStyleSheet("color: #888888; font-style: italic;")
        row3_layout.addWidget(self.example_label)
        
        self.add_tag_btn = QPushButton("Agregar Tag")
        self.add_tag_btn.clicked.connect(self.add_tag)
        row3_layout.addWidget(self.add_tag_btn)
        
        self.save_config_btn = QPushButton("Guardar Configuración")
        self.save_config_btn.clicked.connect(self.save_tags_to_config)
        self.save_config_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        row3_layout.addWidget(self.save_config_btn)
        
        control_layout.addLayout(row3_layout)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # Scroll area para tags
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        self.tags_layout = QVBoxLayout()
        scroll_widget.setLayout(self.tags_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)
        
        # Barra de estado
        self.statusBar().showMessage("Listo")
    
    def setup_default_tags(self):
        """Configurar tags por defecto con ejemplos de tags globales"""
        # TEMPORALMENTE DESHABILITADO - Usar el diagnóstico para encontrar direcciones válidas
        # y luego agregar tags manualmente
        
        # default_tags = [
        #     # Tags globales de ejemplo - direcciones básicas que suelen existir
        #     ("Contactor_Motor", "Q", 0, "bool", 0, None),
        #     ("Sensor_Presion", "I", 0, "bool", 0, None),
        #     ("Marca_Ciclo", "M", 0, "bool", 0, None),
        #     ("Marca_Estado", "M", 0, "bool", 1, None),
        # ]
        # 
        # for tag_name, tag_type, address, data_type, bit, db_number in default_tags:
        #     self.add_tag_to_ui(tag_name, tag_type, address, data_type, bit, db_number)
        
        # En su lugar, mostrar mensaje informativo
        info_label = QLabel("\n=== INSTRUCCIONES ==="
                           "\n1. Conéctate a tu PLC"
                           "\n2. Haz clic en 'Diagnosticar PLC' para ver direcciones disponibles"
                           "\n3. Agrega tags manualmente usando direcciones válidas"
                           "\n4. Evita usar direcciones que no existen en tu PLC\n")
        info_label.setStyleSheet("color: #888888; font-style: italic; padding: 10px;")
        info_label.setWordWrap(True)
        self.tags_layout.addWidget(info_label)
    
    def on_tag_type_changed(self, tag_type_text):
        """Manejar cambio en el tipo de tag"""
        tag_type = tag_type_text.split(" ")[0]  # Extraer solo el tipo (I, Q, M, etc.)
        
        # Mostrar/ocultar controles según el tipo de tag
        if tag_type in ["I", "Q", "M"]:
            # Tags digitales - mostrar bit, ocultar DB, tipo de dato fijo a bool
            self.bit_label.setVisible(True)
            self.bit_input.setVisible(True)
            self.db_label.setVisible(False)
            self.db_input.setVisible(False)
            self.data_type_combo.setCurrentText("bool")
            self.data_type_combo.setEnabled(False)
        elif tag_type in ["IW", "QW", "MW"]:
            # Tags analógicos - ocultar bit, ocultar DB, tipo de dato fijo a int
            self.bit_label.setVisible(False)
            self.bit_input.setVisible(False)
            self.db_label.setVisible(False)
            self.db_input.setVisible(False)
            self.data_type_combo.setCurrentText("int")
            self.data_type_combo.setEnabled(False)
        elif tag_type == "DB":
            # Data Blocks - mostrar bit y DB, habilitar tipo de dato
            self.bit_label.setVisible(True)
            self.bit_input.setVisible(True)
            self.db_label.setVisible(True)
            self.db_input.setVisible(True)
            self.data_type_combo.setEnabled(True)
        
        # Actualizar etiquetas de ejemplo
        examples = {
            "I": "Ejemplo: I0.1 (Entrada digital)",
            "Q": "Ejemplo: Q0.0 (Salida digital)",
            "M": "Ejemplo: M0.2 (Marca)",
            "IW": "Ejemplo: IW64 (Entrada analógica)",
            "QW": "Ejemplo: QW64 (Salida analógica)",
            "MW": "Ejemplo: MW10 (Palabra memoria)",
            "DB": "Ejemplo: DB1.DBX0.0 (Data Block)"
        }
        
        if hasattr(self, 'example_label'):
            self.example_label.setText(examples.get(tag_type, ""))
    
    def save_tags_to_config(self):
        """Guardar configuración de tags y conexión PLC en archivo JSON"""
        try:
            config = {
                'plc_connection': {
                    'ip_address': self.ip_input.text(),
                    'rack': self.rack_input.value(),
                    'slot': self.slot_input.value()
                },
                'tags': [],
                'version': '1.0',
                'last_saved': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            
            for tag_name, tag_info in self.tag_widgets.items():
                tag_config = {
                    'name': tag_name,
                    'tag_type': tag_info['tag_type'],
                    'address': tag_info['address'],
                    'data_type': tag_info['data_type'],
                    'bit': tag_info['bit'],
                    'db_number': tag_info['db_number']
                }
                config['tags'].append(tag_config)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.statusBar().showMessage(f"Configuración guardada: {len(config['tags'])} tags", 3000)
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo guardar la configuración: {e}")
    
    def load_tags_from_config(self):
        """Cargar configuración de tags y conexión PLC desde archivo JSON"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Cargar configuración de conexión PLC
                plc_config = config.get('plc_connection', {})
                if plc_config:
                    self.ip_input.setText(plc_config.get('ip_address', '192.168.0.6'))
                    self.rack_input.setValue(plc_config.get('rack', 0))
                    self.slot_input.setValue(plc_config.get('slot', 1))
                
                # Cargar tags guardados
                for tag_config in config.get('tags', []):
                    self.add_tag_to_ui(
                        tag_config['name'],
                        tag_config['tag_type'],
                        tag_config['address'],
                        tag_config['data_type'],
                        tag_config.get('bit'),
                        tag_config.get('db_number')
                    )
                
                tags_count = len(config.get('tags', []))
                ip_address = plc_config.get('ip_address', 'N/A')
                self.statusBar().showMessage(f"Configuración cargada: {tags_count} tags, PLC: {ip_address}", 3000)
            else:
                # Si no existe archivo, mostrar tags por defecto
                self.setup_default_tags()
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar la configuración: {e}")
            # En caso de error, mostrar tags por defecto
            self.setup_default_tags()
    
    def add_tag_to_ui(self, tag_name, tag_type, address, data_type, bit=None, db_number=None):
        """Agregar tag a la interfaz"""
        # Determinar si es de solo lectura
        read_only = tag_type in ['I', 'IW']  # Entradas son solo lectura
        
        tag_widget = TagWidget(tag_name, data_type, read_only=read_only)
        tag_widget.value_changed.connect(self.write_tag_value)
        tag_widget.edit_requested.connect(self.edit_tag)  # Conectar señal de edición
        self.tags_layout.addWidget(tag_widget)
        self.tag_widgets[tag_name] = {
            'widget': tag_widget,
            'tag_type': tag_type,
            'address': address,
            'data_type': data_type,
            'bit': bit,
            'db_number': db_number
        }
    
    def add_tag(self):
        """Agregar nuevo tag desde la interfaz"""
        tag_name = self.tag_name_input.text().strip()
        if not tag_name:
            QMessageBox.warning(self, "Error", "Ingrese un nombre para el tag")
            return
        
        if tag_name in self.tag_widgets:
            QMessageBox.warning(self, "Error", "El tag ya existe")
            return
        
        # Obtener tipo de tag
        tag_type_text = self.tag_type_combo.currentText()
        tag_type = tag_type_text.split(" ")[0]  # Extraer solo el tipo (I, Q, M, etc.)
        
        address = self.address_input.value()
        data_type = self.data_type_combo.currentText()
        
        # Configurar bit y db_number según el tipo
        bit = None
        db_number = None
        
        if tag_type in ["I", "Q", "M"] or (tag_type == "DB" and data_type == "bool"):
            bit = self.bit_input.value()
        
        if tag_type == "DB":
            db_number = self.db_input.value()
        
        self.add_tag_to_ui(tag_name, tag_type, address, data_type, bit, db_number)
        
        # Guardar configuración automáticamente
        self.save_tags_to_config()
        
        # Limpiar campos
        self.tag_name_input.clear()
        self.address_input.setValue(0)
    
    def edit_tag(self, tag_name):
        """Editar un tag existente"""
        if tag_name not in self.tag_widgets:
            return
        
        tag_info = self.tag_widgets[tag_name]
        
        # Crear diálogo de edición
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Editar Tag: {tag_name}")
        dialog.setGeometry(300, 300, 400, 300)
        
        layout = QVBoxLayout()
        
        # Nombre del tag
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Nombre:"))
        name_edit = QLineEdit(tag_name)
        name_layout.addWidget(name_edit)
        layout.addLayout(name_layout)
        
        # Tipo de tag
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Tipo Tag:"))
        type_combo = QComboBox()
        type_combo.addItems(["I (Entrada)", "Q (Salida)", "M (Marca)", "IW (Entrada Analógica)", "QW (Salida Analógica)", "MW (Palabra Memoria)", "DB (Data Block)"])
        
        # Seleccionar tipo actual
        current_type = tag_info['tag_type']
        type_map = {'I': 0, 'Q': 1, 'M': 2, 'IW': 3, 'QW': 4, 'MW': 5, 'DB': 6}
        if current_type in type_map:
            type_combo.setCurrentIndex(type_map[current_type])
        
        type_layout.addWidget(type_combo)
        layout.addLayout(type_layout)
        
        # Dirección
        addr_layout = QHBoxLayout()
        addr_layout.addWidget(QLabel("Dirección:"))
        addr_edit = QSpinBox()
        addr_edit.setRange(0, 8190)
        addr_edit.setValue(tag_info['address'])
        addr_layout.addWidget(addr_edit)
        layout.addLayout(addr_layout)
        
        # Bit (para tipos digitales)
        bit_layout = QHBoxLayout()
        bit_label = QLabel("Bit:")
        bit_edit = QSpinBox()
        bit_edit.setRange(0, 7)
        bit_edit.setValue(tag_info['bit'] if tag_info['bit'] is not None else 0)
        bit_layout.addWidget(bit_label)
        bit_layout.addWidget(bit_edit)
        layout.addLayout(bit_layout)
        
        # DB (para Data Blocks)
        db_layout = QHBoxLayout()
        db_label = QLabel("DB:")
        db_edit = QSpinBox()
        db_edit.setRange(1, 999)
        db_edit.setValue(tag_info['db_number'] if tag_info['db_number'] is not None else 1)
        db_layout.addWidget(db_label)
        db_layout.addWidget(db_edit)
        layout.addLayout(db_layout)
        
        # Tipo de dato
        data_type_layout = QHBoxLayout()
        data_type_layout.addWidget(QLabel("Tipo Dato:"))
        data_type_combo = QComboBox()
        data_type_combo.addItems(["bool", "int", "real"])
        data_type_combo.setCurrentText(tag_info['data_type'])
        data_type_layout.addWidget(data_type_combo)
        layout.addLayout(data_type_layout)
        
        # Función para actualizar controles según tipo
        def update_controls():
            tag_type = type_combo.currentText().split(" ")[0]
            if tag_type in ["I", "Q", "M"]:
                bit_label.setVisible(True)
                bit_edit.setVisible(True)
                db_label.setVisible(False)
                db_edit.setVisible(False)
                data_type_combo.setCurrentText("bool")
                data_type_combo.setEnabled(False)
            elif tag_type in ["IW", "QW", "MW"]:
                bit_label.setVisible(False)
                bit_edit.setVisible(False)
                db_label.setVisible(False)
                db_edit.setVisible(False)
                data_type_combo.setCurrentText("int")
                data_type_combo.setEnabled(False)
            elif tag_type == "DB":
                bit_label.setVisible(True)
                bit_edit.setVisible(True)
                db_label.setVisible(True)
                db_edit.setVisible(True)
                data_type_combo.setEnabled(True)
        
        type_combo.currentTextChanged.connect(update_controls)
        update_controls()  # Aplicar configuración inicial
        
        # Botones
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton("Guardar")
        cancel_btn = QPushButton("Cancelar")
        delete_btn = QPushButton("Eliminar")
        delete_btn.setStyleSheet("color: red;")
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(delete_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # Conectar botones
        def save_changes():
            new_name = name_edit.text().strip()
            if not new_name:
                QMessageBox.warning(dialog, "Error", "El nombre no puede estar vacío")
                return
            
            if new_name != tag_name and new_name in self.tag_widgets:
                QMessageBox.warning(dialog, "Error", "Ya existe un tag con ese nombre")
                return
            
            # Obtener nuevos valores
            new_tag_type = type_combo.currentText().split(" ")[0]
            new_address = addr_edit.value()
            new_data_type = data_type_combo.currentText()
            new_bit = bit_edit.value() if new_tag_type in ["I", "Q", "M"] or (new_tag_type == "DB" and new_data_type == "bool") else None
            new_db_number = db_edit.value() if new_tag_type == "DB" else None
            
            # Eliminar tag anterior
            self.remove_tag(tag_name)
            
            # Agregar tag con nuevos valores
            self.add_tag_to_ui(new_name, new_tag_type, new_address, new_data_type, new_bit, new_db_number)
            
            # Guardar configuración
            self.save_tags_to_config()
            
            dialog.accept()
        
        def delete_tag():
            reply = QMessageBox.question(dialog, "Confirmar", f"¿Estás seguro de eliminar el tag '{tag_name}'?",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.remove_tag(tag_name)
                self.save_tags_to_config()
                dialog.accept()
        
        save_btn.clicked.connect(save_changes)
        cancel_btn.clicked.connect(dialog.reject)
        delete_btn.clicked.connect(delete_tag)
        
        dialog.exec_()
    
    def remove_tag(self, tag_name):
        """Eliminar un tag de la interfaz"""
        if tag_name in self.tag_widgets:
            # Eliminar widget de la interfaz
            widget = self.tag_widgets[tag_name]['widget']
            self.tags_layout.removeWidget(widget)
            widget.deleteLater()
            
            # Eliminar de la lista
            del self.tag_widgets[tag_name]
    
    def toggle_connection(self):
        """Conectar/desconectar del PLC"""
        if not self.plc.is_connected():
            ip = self.ip_input.text()
            rack = self.rack_input.value()
            slot = self.slot_input.value()
            
            if self.plc.connect(ip, rack, slot):
                self.connect_btn.setText("Desconectar")
                self.status_label.setText("Conectado")
                self.status_label.setStyleSheet("color: green; font-weight: bold;")
                self.diagnose_btn.setEnabled(True)
                
                # Guardar configuración de conexión exitosa
                self.save_tags_to_config()
                
                self.start_monitoring()
            else:
                QMessageBox.critical(self, "Error", "No se pudo conectar al PLC")
        else:
            self.plc.disconnect()
            self.connect_btn.setText("Conectar")
            self.status_label.setText("Desconectado")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.diagnose_btn.setEnabled(False)
            self.stop_monitoring()
    
    def start_monitoring(self):
        """Iniciar monitoreo de tags"""
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait()
        
        self.monitor_thread = PLCMonitorThread(self.plc)
        
        # Agregar todos los tags al monitoreo
        for tag_name, tag_info in self.tag_widgets.items():
            self.monitor_thread.add_tag(
                tag_name, 
                tag_info['tag_type'], 
                tag_info['address'], 
                tag_info['data_type'], 
                tag_info['bit'],
                tag_info['db_number']
            )
        
        self.monitor_thread.data_updated.connect(self.update_tag_values)
        self.monitor_thread.connection_status.connect(self.update_connection_status)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Detener monitoreo de tags"""
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait()
            self.monitor_thread = None
    
    def update_tag_values(self, data):
        """Actualizar valores de los tags en la interfaz"""
        for tag_name, value in data.items():
            if tag_name in self.tag_widgets:
                self.tag_widgets[tag_name]['widget'].update_value(value)
    
    def update_connection_status(self, connected):
        """Actualizar estado de conexión"""
        if not connected and self.plc.connected:
            self.plc.connected = False
            self.connect_btn.setText("Conectar")
            self.status_label.setText("Desconectado")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.stop_monitoring()
    
    def write_tag_value(self, tag_name, value):
        """Escribir valor al PLC"""
        if not self.plc.is_connected():
            QMessageBox.warning(self, "Error", "No hay conexión con el PLC")
            return
        
        if tag_name not in self.tag_widgets:
            return
        
        tag_info = self.tag_widgets[tag_name]
        success = False
        
        try:
            if tag_info['tag_type'] == 'DB':
                # Tags de Data Block (método original)
                if tag_info['data_type'] == 'bool':
                    success = self.plc.write_bool(tag_info['db_number'], tag_info['address'], tag_info['bit'], value)
                elif tag_info['data_type'] == 'int':
                    success = self.plc.write_int(tag_info['db_number'], tag_info['address'], value)
                elif tag_info['data_type'] == 'real':
                    success = self.plc.write_real(tag_info['db_number'], tag_info['address'], value)
            else:
                # Tags globales (Q, M, QW, MW) - las entradas (I, IW) no se pueden escribir
                if tag_info['tag_type'] in ['I', 'IW']:
                    QMessageBox.warning(self, "Error", f"No se puede escribir en una entrada: {tag_name}")
                    return
                
                success = self.plc.write_global_tag(tag_info['tag_type'], tag_info['address'], value, tag_info['bit'])
            
            if success:
                self.statusBar().showMessage(f"Valor escrito: {tag_name} = {value}", 2000)
            else:
                QMessageBox.warning(self, "Error", f"No se pudo escribir el valor en {tag_name}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error escribiendo {tag_name}: {e}")
    
    def diagnose_plc(self):
        """Diagnosticar el PLC para encontrar direcciones disponibles"""
        if not self.plc.is_connected():
            QMessageBox.warning(self, "Error", "No hay conexión con el PLC")
            return
        
        # Crear ventana de diagnóstico
        dialog = QDialog(self)
        dialog.setWindowTitle("Diagnóstico del PLC")
        dialog.setGeometry(200, 200, 600, 400)
        
        layout = QVBoxLayout()
        
        # Área de texto para mostrar resultados
        text_area = QTextEdit()
        text_area.setReadOnly(True)
        layout.addWidget(text_area)
        
        # Botones
        button_layout = QHBoxLayout()
        test_btn = QPushButton("Probar Direcciones")
        close_btn = QPushButton("Cerrar")
        button_layout.addWidget(test_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        def run_diagnosis():
            text_area.clear()
            text_area.append("=== DIAGNÓSTICO DEL PLC S7-1200 ===")
            text_area.append("")
            
            # Obtener estado del PLC
            status = self.plc.get_plc_status()
            if status:
                text_area.append("Estado del PLC:")
                if 'error' in status:
                    text_area.append(f"  Error: {status['error']}")
                else:
                    text_area.append(f"  Conexión: {status['connection']}")
                text_area.append("")
            
            # Probar direcciones disponibles
            text_area.append("Probando direcciones disponibles...")
            text_area.append("")
            
            test_results = self.plc.safe_read_test()
            
            for tag_type, addresses in test_results.items():
                if addresses:
                    text_area.append(f"{tag_type} - Direcciones disponibles: {addresses}")
                    for addr in addresses:
                        if tag_type in ['I', 'Q', 'M']:
                            text_area.append(f"  {tag_type}{addr}.0, {tag_type}{addr}.1, ..., {tag_type}{addr}.7")
                        else:
                            text_area.append(f"  {tag_type}{addr}")
                else:
                    text_area.append(f"{tag_type} - No se encontraron direcciones disponibles")
                text_area.append("")
            
            # Recomendaciones
            text_area.append("=== RECOMENDACIONES ===")
            text_area.append("")
            text_area.append("1. Usa solo las direcciones que aparecen como 'disponibles'")
            text_area.append("2. Para Data Blocks (DB), verifica en TIA Portal qué DBs existen")
            text_area.append("3. Las direcciones I son entradas (solo lectura)")
            text_area.append("4. Las direcciones Q son salidas (lectura/escritura)")
            text_area.append("5. Las direcciones M son marcas internas (lectura/escritura)")
            text_area.append("")
            text_area.append("Diagnóstico completado.")
        
        test_btn.clicked.connect(run_diagnosis)
        close_btn.clicked.connect(dialog.close)
        
        # Ejecutar diagnóstico automáticamente
        run_diagnosis()
        
        dialog.exec_()
    
    def closeEvent(self, event):
        """Manejar cierre de la aplicación"""
        self.stop_monitoring()
        if self.plc.is_connected():
            self.plc.disconnect()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Estilo moderno
    
    # Configurar tema oscuro
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(53, 53, 53))
    palette.setColor(QPalette.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    palette.setColor(QPalette.ToolTipBase, QColor(0, 0, 0))
    palette.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
    palette.setColor(QPalette.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.Button, QColor(53, 53, 53))
    palette.setColor(QPalette.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)
    
    window = PLCMainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
