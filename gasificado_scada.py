"""
SCADA de Gasificado para 3 Cámaras de Arándanos
- Control simultáneo de 3 cámaras de gasificado
- Monitoreo en tiempo real de PPM, SET points y alertas
- Interfaz estilo SCADA con indicadores visuales
- Pulsos automáticos para START/STOP
"""
import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QDialog, QFormLayout, QComboBox, QMessageBox, QLineEdit,
    QGroupBox, QGridLayout, QSpacerItem, QSizePolicy, QFrame, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPalette, QColor, QFont, QIntValidator

from plc_connection import PLCConnection

CONFIG_TAGS_FILE = "plc_tags_config.json"
SCADA_CONFIG_FILE = "gasificado_scada_config.json"
PULSE_MS = 200

# ================= Utilidades de acceso a Tags =================

def load_tags_config(config_path: str):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No se encontró el archivo de configuración de tags: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_tags_index_by_name(tags_cfg: dict):
    tags = tags_cfg.get('tags', [])
    return {t.get('name'): t for t in tags}

def read_tag_value(plc: PLCConnection, tag: dict):
    """Lee el valor del tag según su tipo."""
    if not tag:
        return None
    tag_type = (tag.get('tag_type') or '').upper()
    data_type = (tag.get('data_type') or '').lower()
    address = int(tag.get('address') or 0)
    bit = tag.get('bit')
    dbn = tag.get('db_number')

    if tag_type == 'DB':
        if data_type == 'bool':
            return plc.read_bool(int(dbn), address, int(bit))
        elif data_type == 'int':
            return plc.read_int(int(dbn), address)
        elif data_type == 'real':
            return plc.read_real(int(dbn), address)
        return None
    else:
        return plc.read_global_tag(tag_type, address, bit)

def write_tag_value(plc: PLCConnection, tag: dict, value):
    """Escribe valor en el tag según su tipo."""
    if not tag:
        return False
    tag_type = (tag.get('tag_type') or '').upper()
    data_type = (tag.get('data_type') or '').lower()
    address = int(tag.get('address') or 0)
    bit = tag.get('bit')
    dbn = tag.get('db_number')

    if tag_type == 'DB':
        if data_type == 'bool':
            return plc.write_bool(int(dbn), address, int(bit), bool(value))
        elif data_type == 'int':
            return plc.write_int(int(dbn), address, int(value))
        elif data_type == 'real':
            return plc.write_real(int(dbn), address, float(value))
        return False
    else:
        return plc.write_global_tag(tag_type, address, value, bit)

# ================= Monitor SCADA =================

class SCADAMonitorThread(QThread):
    chamber_data_updated = pyqtSignal(int, dict)  # chamber_id, data_dict
    connection_status = pyqtSignal(bool)

    def __init__(self, plc: PLCConnection, tags_by_name: dict, mapping: dict, interval_sec: float = 1.0):
        super().__init__()
        self.plc = plc
        self.tags_by_name = tags_by_name
        self.mapping = mapping or {}
        self.running = False
        self.interval = max(0.1, interval_sec)
        self._last_alert_states = {}

    def run(self):
        self.running = True
        while self.running:
            connected = self.plc.is_connected()
            self.connection_status.emit(bool(connected))

            if connected:
                for chamber_id in [1, 2, 3]:
                    data = self._read_chamber_data(chamber_id)
                    self.chamber_data_updated.emit(chamber_id, data)
            
            time.sleep(self.interval)

    def _read_chamber_data(self, chamber_id: int) -> dict:
        """Lee todos los datos de una cámara específica."""
        data = {
            'ppm': None,
            'set_value': None,
            'alerta': False,
            'alerta_changed': False
        }
        
        try:
            # Leer PPM
            ppm_tag = self.tags_by_name.get(f'PPM{chamber_id}')
            if ppm_tag:
                data['ppm'] = read_tag_value(self.plc, ppm_tag)
            
            # Leer SET
            set_tag = self.tags_by_name.get(f'SET{chamber_id}')
            if set_tag:
                data['set_value'] = read_tag_value(self.plc, set_tag)
            
            # Leer ALERTA
            alerta_tag = self.tags_by_name.get(f'ALERTA{chamber_id}')
            if alerta_tag:
                alerta_now = bool(read_tag_value(self.plc, alerta_tag))
                data['alerta'] = alerta_now
                
                # Detectar cambio de estado
                last_state = self._last_alert_states.get(chamber_id)
                if last_state is None or alerta_now != last_state:
                    data['alerta_changed'] = True
                    self._last_alert_states[chamber_id] = alerta_now
                    
        except Exception as e:
            print(f"Error leyendo datos cámara {chamber_id}: {e}")
        
        return data

    def stop(self):
        self.running = False

# ================= Widget de Cámara Individual =================

class ChamberWidget(QGroupBox):
    def __init__(self, chamber_id: int, plc: PLCConnection, tags_by_name: dict):
        super().__init__(f"CÁMARA {chamber_id}")
        self.chamber_id = chamber_id
        self.plc = plc
        self.tags_by_name = tags_by_name
        self.alert_dialog_open = False
        
        self.setMinimumSize(480, 420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"""
            QGroupBox {{
                font-weight: 600;
                font-size: 18px;
                color: #2c3e50;
                background: #ffffff;
                border: none;
                margin: 12px;
                padding-top: 30px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 24px;
                padding: 12px 20px;
                color: #ffffff;
                background: #32cd32;
                font-size: 16px;
                font-weight: 600;
            }}
        """)
        
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        
        # Estado visual optimizado para HMI
        self.status_frame = QFrame()
        self.status_frame.setFixedHeight(48)
        self.status_frame.setStyleSheet("""
            background: #ecf0f1;
            border: none;
        """)
        self.lbl_status = QLabel("DETENIDO")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #7f8c8d; font-weight: 600; font-size: 16px;")
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.addWidget(self.lbl_status)
        
        # PPM Display optimizado para HMI industrial
        ppm_layout = QVBoxLayout()
        ppm_layout.setSpacing(8)
        ppm_title = QLabel("PPM")
        ppm_title.setStyleSheet("color: #7f8c8d; font-weight: 600; font-size: 14px; text-transform: uppercase;")
        ppm_title.setAlignment(Qt.AlignCenter)
        self.lbl_ppm = QLabel("—")
        self.lbl_ppm.setFont(QFont("Segoe UI", 42, QFont.Bold))
        self.lbl_ppm.setStyleSheet("""
            color: #2c3e50; 
            background: #e8f8f5;
            padding: 24px; 
            border: none;
            min-height: 100px;
        """)
        self.lbl_ppm.setAlignment(Qt.AlignCenter)
        ppm_layout.addWidget(ppm_title)
        ppm_layout.addWidget(self.lbl_ppm)
        
        # SET Control optimizado para HMI industrial
        set_layout = QVBoxLayout()
        set_layout.setSpacing(8)
        set_title = QLabel("SETPOINT")
        set_title.setStyleSheet("color: #7f8c8d; font-weight: 600; font-size: 14px; text-transform: uppercase;")
        set_title.setAlignment(Qt.AlignCenter)
        
        set_display_layout = QVBoxLayout()
        set_display_layout.setSpacing(12)
        self.lbl_set = QLabel("—")
        self.lbl_set.setFont(QFont("Segoe UI", 28, QFont.Bold))
        self.lbl_set.setStyleSheet("""
            color: #2c3e50; 
            background: #f8f9fa;
            padding: 20px; 
            border: none;
            min-height: 70px;
        """)
        self.lbl_set.setAlignment(Qt.AlignCenter)
        
        set_input_layout = QHBoxLayout()
        set_input_layout.setSpacing(12)
        self.edit_set = QLineEdit()
        self.edit_set.setPlaceholderText("Valor")
        self.edit_set.setValidator(QIntValidator())
        self.edit_set.setFixedHeight(48)
        self.edit_set.setStyleSheet("""
            QLineEdit {
                padding: 12px 16px;
                border: none;
                background: white;
                color: #2c3e50;
                font-size: 16px;
                font-weight: 500;
            }
            QLineEdit:focus {
                background: #f8f9fa;
            }
        """)
        
        self.btn_apply_set = QPushButton("APLICAR")
        self.btn_apply_set.setFixedHeight(48)
        self.btn_apply_set.setFixedWidth(100)
        self.btn_apply_set.setStyleSheet("""
            QPushButton {
                background: #32cd32;
                color: white;
                font-weight: 600;
                font-size: 14px;
                border: none;
                text-transform: uppercase;
            }
            QPushButton:hover { 
                background: #28a745;
            }
            QPushButton:pressed { 
                background: #1e7e34;
            }
        """)
        self.btn_apply_set.clicked.connect(self.on_apply_set)
        
        set_input_layout.addWidget(self.edit_set, 2)
        set_input_layout.addWidget(self.btn_apply_set, 1)
        
        set_display_layout.addWidget(self.lbl_set)
        set_display_layout.addLayout(set_input_layout)
        
        set_layout.addWidget(set_title)
        set_layout.addLayout(set_display_layout)
        
        # Botones START/STOP optimizados para HMI industrial
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        self.btn_start = QPushButton("INICIAR")
        self.btn_stop = QPushButton("DETENER")
        
        # Botón INICIAR - Verde estándar industrial
        self.btn_start.setFixedHeight(56)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: #28a745;
                color: white;
                font-family: 'Segoe UI';
                font-weight: 600;
                font-size: 16px;
                border: none;
                text-transform: uppercase;
            }
            QPushButton:hover { 
                background: #34ce57;
            }
            QPushButton:pressed { 
                background: #1e7e34;
            }
        """)
        
        # Botón DETENER - Rojo estándar industrial
        self.btn_stop.setFixedHeight(56)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: #dc3545;
                color: white;
                font-family: 'Segoe UI';
                font-weight: 600;
                font-size: 16px;
                border: none;
                text-transform: uppercase;
            }
            QPushButton:hover { 
                background: #e4606d;
            }
            QPushButton:pressed { 
                background: #bd2130;
            }
        """)
        
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        
        # Indicador de alerta optimizado para HMI
        self.lbl_alerta = QLabel("ALERTA")
        self.lbl_alerta.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.lbl_alerta.setStyleSheet("""
            color: #95a5a6;
            background: #ecf0f1;
            padding: 8px 16px;
            border: none;
            text-transform: uppercase;
            font-weight: 600;
        """)
        self.lbl_alerta.setAlignment(Qt.AlignCenter)
        self.lbl_alerta.setFixedHeight(40)
        
        # Layout principal optimizado para HMI industrial
        main_grid = QGridLayout()
        main_grid.setSpacing(16)
        main_grid.setContentsMargins(24, 16, 24, 24)
        
        # Fila 1: Estado
        main_grid.addWidget(self.status_frame, 0, 0, 1, 2)
        
        # Fila 2: PPM y SET lado a lado con proporciones óptimas
        main_grid.addLayout(ppm_layout, 1, 0)
        main_grid.addLayout(set_layout, 1, 1)
        
        # Fila 3: Botones con espaciado funcional
        main_grid.addLayout(btn_layout, 2, 0, 1, 2)
        
        # Fila 4: Alerta centrada
        alerta_layout = QHBoxLayout()
        alerta_layout.addStretch()
        alerta_layout.addWidget(self.lbl_alerta)
        alerta_layout.addStretch()
        main_grid.addLayout(alerta_layout, 3, 0, 1, 2)
        
        # Configurar proporciones de columnas para balance óptimo
        main_grid.setColumnStretch(0, 1)
        main_grid.setColumnStretch(1, 1)
        
        layout.addLayout(main_grid)
        layout.addStretch()
        
        self.setLayout(layout)

    def update_data(self, data: dict):
        """Actualiza la UI con nuevos datos."""
        # PPM
        ppm = data.get('ppm')
        if ppm is None:
            self.lbl_ppm.setText("—")
        else:
            self.lbl_ppm.setText(str(ppm))
            # Color coding para PPM - tema claro para arándanos
            if ppm > 1000:
                self.lbl_ppm.setStyleSheet("""
                    color: #B71C1C; 
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 #FFEBEE, stop:1 #FFCDD2);
                    padding: 8px; border-radius: 8px;
                    border: 2px solid #F44336; min-width: 80px;
                """)
            elif ppm > 500:
                self.lbl_ppm.setStyleSheet("""
                    color: #E65100; 
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 #FFF8E1, stop:1 #FFECB3);
                    padding: 8px; border-radius: 8px;
                    border: 2px solid #FFC107; min-width: 80px;
                """)
            else:
                self.lbl_ppm.setStyleSheet("""
                    color: #2E7D32; 
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                        stop:0 #E8F5E8, stop:1 #C8E6C9);
                    padding: 8px; border-radius: 8px;
                    border: 2px solid #4CAF50; min-width: 80px;
                """)
        
        # SET
        set_val = data.get('set_value')
        if set_val is None:
            self.lbl_set.setText("—")
        else:
            self.lbl_set.setText(str(set_val))
        
        # Alerta
        alerta = data.get('alerta', False)
        if alerta:
            self.lbl_alerta.setStyleSheet("""
                color: #D32F2F;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #FFEBEE, stop:1 #FFCDD2);
                border-radius: 20px;
                padding: 5px;
                border: 2px solid #F44336;
            """)
            self.status_frame.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #FFCDD2, stop:1 #EF5350);
                border-radius: 8px;
                border: 2px solid #F44336;
            """)
            self.lbl_status.setText("🚨 ALERTA ACTIVA")
            self.lbl_status.setStyleSheet("color: #B71C1C; font-weight: bold; font-size: 16px;")
            
            # Mostrar diálogo si cambió a activo
            if data.get('alerta_changed') and not self.alert_dialog_open:
                self._show_alert_dialog()
        else:
            self.lbl_alerta.setStyleSheet("""
                color: #B0BEC5;
                background: #F5F5F5;
                border-radius: 20px;
                padding: 5px;
            """)
            self.status_frame.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #C8E6C9, stop:1 #4CAF50);
                border-radius: 8px;
                border: 2px solid #388E3C;
            """)
            self.lbl_status.setText("✅ OPERANDO")
            self.lbl_status.setStyleSheet("color: #1B5E20; font-weight: bold; font-size: 16px;")

    def _get_tag(self, suffix: str):
        """Obtiene el tag para esta cámara con el sufijo dado."""
        tag_name = f"{suffix}{self.chamber_id}"
        return self.tags_by_name.get(tag_name)

    def _pulse_tag(self, tag: dict):
        """Envía un pulso al tag."""
        if not tag:
            return False
        dt = (tag.get('data_type') or '').lower()
        active = True if dt == 'bool' else 1
        reset = False if dt == 'bool' else 0
        ok = write_tag_value(self.plc, tag, active)
        if ok:
            QTimer.singleShot(PULSE_MS, lambda: write_tag_value(self.plc, tag, reset))
        return ok

    def on_start(self):
        if not self.plc.is_connected():
            QMessageBox.warning(self, "No conectado", "Conéctate al PLC antes de iniciar.")
            return
        tag = self._get_tag('START')
        if not tag:
            QMessageBox.warning(self, "Sin START", f"Tag START{self.chamber_id} no encontrado.")
            return
        ok = self._pulse_tag(tag)
        if not ok:
            QMessageBox.critical(self, "Error", f"No se pudo enviar START a cámara {self.chamber_id}.")

    def on_stop(self):
        if not self.plc.is_connected():
            QMessageBox.warning(self, "No conectado", "Conéctate al PLC antes de detener.")
            return
        tag = self._get_tag('STOP')
        if not tag:
            QMessageBox.warning(self, "Sin STOP", f"Tag STOP{self.chamber_id} no encontrado.")
            return
        ok = self._pulse_tag(tag)
        if not ok:
            QMessageBox.critical(self, "Error", f"No se pudo enviar STOP a cámara {self.chamber_id}.")

    def on_apply_set(self):
        if not self.plc.is_connected():
            QMessageBox.warning(self, "No conectado", "Conéctate al PLC antes de escribir SET.")
            return
        tag = self._get_tag('SET')
        if not tag:
            QMessageBox.warning(self, "SET no configurado", f"Tag SET{self.chamber_id} no encontrado.")
            return
        txt = self.edit_set.text().strip()
        if not txt:
            QMessageBox.warning(self, "Valor vacío", "Introduce un valor entero para SET.")
            return
        try:
            val = int(txt)
        except ValueError:
            QMessageBox.warning(self, "Formato inválido", "El valor debe ser numérico.")
            return
        ok = write_tag_value(self.plc, tag, val)
        if ok:
            self.edit_set.clear()
        else:
            QMessageBox.critical(self, "Error", f"No se pudo escribir SET{self.chamber_id}.")

    def _show_alert_dialog(self):
        self.alert_dialog_open = True
        try:
            m = QMessageBox(self)
            m.setWindowTitle(f"ALERTA CÁMARA {self.chamber_id}")
            m.setIcon(QMessageBox.Warning)
            m.setText(f"Se ha activado ALERTA{self.chamber_id}. ¿Deseas continuar?")
            btn_continue = m.addButton("Continuar", QMessageBox.AcceptRole)
            m.addButton("Cancelar", QMessageBox.RejectRole)
            m.setDefaultButton(btn_continue)
            m.exec_()

            if m.clickedButton() == btn_continue:
                confirm_tag = self._get_tag('CONFIRM')
                if confirm_tag:
                    ok = write_tag_value(self.plc, confirm_tag, 1)
                    if not ok:
                        QMessageBox.critical(self, "Error", f"No se pudo escribir CONFIRM{self.chamber_id}=1.")
        finally:
            QTimer.singleShot(500, lambda: setattr(self, 'alert_dialog_open', False))

# ================= Ventana Principal SCADA =================

class SCADAWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🫐 SCADA Gasificado - Control de Arándanos")
        self.resize(1800, 1000)
        self.setMinimumSize(1600, 900)
        self.setStyleSheet("""
            QMainWindow {
                background: #f8f9fa;
                color: #2c3e50;
            }
        """)
        
        self.plc = PLCConnection()
        self.tags_cfg = None
        self.tags_by_name = {}
        self.mapping = {}
        self.monitor_thread = None
        self.chamber_widgets = {}
        
        self._load_config()
        self._build_ui()
        self._auto_connect_and_start()

    def _load_config(self):
        # Cargar tags disponibles
        try:
            self.tags_cfg = load_tags_config(CONFIG_TAGS_FILE)
            self.tags_by_name = get_tags_index_by_name(self.tags_cfg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar {CONFIG_TAGS_FILE}: {e}")
            self.tags_cfg = {'plc_connection': {'ip_address': '192.168.0.6', 'rack': 0, 'slot': 1}, 'tags': []}
            self.tags_by_name = {}

        # Configuración básica
        self.mapping = {
            'plc_connection': self.tags_cfg.get('plc_connection', {'ip_address': '192.168.0.6', 'rack': 0, 'slot': 1})
        }

    def _build_ui(self):
        central = QWidget()
        main_layout = QVBoxLayout()
        
        # Header con estado de conexión
        header_layout = QHBoxLayout()
        
        title = QLabel("SISTEMA SCADA - GASIFICADO DE ARÁNDANOS")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet("""
            color: white; 
            padding: 16px 24px;
            background: #32cd32;
            border: none;
            text-transform: uppercase;
            font-weight: 600;
        """)
        title.setAlignment(Qt.AlignCenter)
        title.setMinimumHeight(64)
        
        conn_frame = QFrame()
        conn_frame.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                stop:0 #FFFFFF, stop:1 #F5F5F5);
            border-radius: 10px;
            border: 2px solid #B0BEC5;
            padding: 10px;
            margin: 10px;
        """)
        conn_frame.setMinimumHeight(60)
        conn_layout = QHBoxLayout(conn_frame)
        
        self.lbl_status = QLabel("🔴 Estado: Desconectado")
        self.lbl_status.setStyleSheet("color: #D32F2F; font-size: 16px; font-weight: bold;")
        self.lbl_status.setMinimumWidth(200)
        
        self.btn_connect = QPushButton("🔌 Conectar PLC")
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #42A5F5, stop:1 #2196F3);
                color: white;
                font-weight: bold;
                font-size: 15px;
                padding: 12px 25px;
                border-radius: 10px;
                border: 2px solid #1976D2;
                min-width: 150px;
                min-height: 40px;
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #64B5F6, stop:1 #42A5F5);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #2196F3, stop:1 #1565C0);
            }
        """)
        self.btn_connect.clicked.connect(self.on_toggle_connect)
        
        conn_layout.addWidget(self.lbl_status)
        conn_layout.addWidget(self.btn_connect)
        
        header_layout.addWidget(title, 2)
        header_layout.addWidget(conn_frame, 1)
        
        # Panel de cámaras con scroll
        chambers_scroll = QScrollArea()
        chambers_scroll.setWidgetResizable(True)
        chambers_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chambers_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        chambers_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)
        
        chambers_container = QWidget()
        chambers_layout = QHBoxLayout(chambers_container)
        chambers_layout.setSpacing(16)
        chambers_layout.setContentsMargins(16, 16, 16, 16)
        
        # Agregar stretch al inicio para centrar
        chambers_layout.addStretch()
        
        for chamber_id in [1, 2, 3]:
            chamber_widget = ChamberWidget(chamber_id, self.plc, self.tags_by_name)
            self.chamber_widgets[chamber_id] = chamber_widget
            chambers_layout.addWidget(chamber_widget)
        
        # Agregar stretch al final para centrar
        chambers_layout.addStretch()
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(chambers_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
        """)
        
        # Layout principal
        main_layout.addLayout(header_layout)
        main_layout.addWidget(scroll_area, 1)  # Expandible
        
        # Footer compacto
        footer_layout = QHBoxLayout()
        footer_info = QLabel("💡 SCADA Gasificado v2.0 | 🫐 Arándanos")
        footer_info.setStyleSheet("""
{{ ... }}
            font-size: 10px;
            padding: 5px;
            background: rgba(255, 255, 255, 0.5);
            border-radius: 3px;
        """)
        footer_info.setAlignment(Qt.AlignCenter)
        footer_layout.addWidget(footer_info)
        
        main_layout.addLayout(footer_layout)
        
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def _auto_connect_and_start(self):
        conn = self.mapping.get('plc_connection') or {}
        ip = conn.get('ip_address', '192.168.0.6')
        rack = int(conn.get('rack', 0))
        slot = int(conn.get('slot', 1))
        
        if ip:
            self._connect_plc(ip, rack, slot)

    def _connect_plc(self, ip: str, rack: int, slot: int):
        ok = self.plc.connect(ip, rack, slot)
        self._update_status(ok)
        self.btn_connect.setText("Desconectar" if ok else "Conectar")
        if ok:
            self._start_monitor()

    def _disconnect_plc(self):
        try:
            self._stop_monitor()
            self.plc.disconnect()
        finally:
            self._update_status(False)
            self.btn_connect.setText("Conectar")

    def _update_status(self, connected: bool):
        if connected:
            self.lbl_status.setText("🟢 Estado: Conectado")
            self.lbl_status.setStyleSheet("color: #2E7D32; font-size: 16px; font-weight: bold;")
            self.btn_connect.setText("🔌 Desconectar PLC")
        else:
            self.lbl_status.setText("🔴 Estado: Desconectado")
            self.lbl_status.setStyleSheet("color: #D32F2F; font-size: 16px; font-weight: bold;")
            self.btn_connect.setText("🔌 Conectar PLC")

    def _start_monitor(self):
        self._stop_monitor()
        self.monitor_thread = SCADAMonitorThread(self.plc, self.tags_by_name, self.mapping, interval_sec=1.0)
        self.monitor_thread.chamber_data_updated.connect(self.on_chamber_data_updated)
        self.monitor_thread.connection_status.connect(self._update_status)
        self.monitor_thread.start()

    def _stop_monitor(self):
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait(1500)
            self.monitor_thread = None

    def on_toggle_connect(self):
        if self.plc.is_connected():
            self._disconnect_plc()
        else:
            conn = self.mapping.get('plc_connection') or {}
            ip = conn.get('ip_address', '192.168.0.6')
            rack = int(conn.get('rack', 0))
            slot = int(conn.get('slot', 1))
            self._connect_plc(ip, rack, slot)

    def on_chamber_data_updated(self, chamber_id: int, data: dict):
        """Actualiza los datos de una cámara específica."""
        if chamber_id in self.chamber_widgets:
            self.chamber_widgets[chamber_id].update_data(data)

    def closeEvent(self, event):
        try:
            self._stop_monitor()
            if self.plc.is_connected():
                self.plc.disconnect()
        finally:
            super().closeEvent(event)

def apply_light_theme(app: QApplication):
    app.setStyle('Fusion')
    palette = QPalette()
    # Tema claro para arándanos
    palette.setColor(QPalette.Window, QColor(248, 250, 254))  # Azul muy claro
    palette.setColor(QPalette.WindowText, QColor(46, 59, 78))  # Azul oscuro
    palette.setColor(QPalette.Base, QColor(255, 255, 255))  # Blanco
    palette.setColor(QPalette.AlternateBase, QColor(227, 242, 253))  # Azul claro alternativo
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(46, 59, 78))
    palette.setColor(QPalette.Text, QColor(46, 59, 78))
    palette.setColor(QPalette.Button, QColor(245, 245, 245))
    palette.setColor(QPalette.ButtonText, QColor(46, 59, 78))
    palette.setColor(QPalette.BrightText, QColor(244, 67, 54))  # Rojo para alertas
    palette.setColor(QPalette.Link, QColor(33, 150, 243))  # Azul para enlaces
    palette.setColor(QPalette.Highlight, QColor(100, 181, 246))  # Azul claro para selección
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

def main():
    app = QApplication(sys.argv)
    apply_light_theme(app)
    
    w = SCADAWindow()
    w.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
