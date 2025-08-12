"""
Interfaz de Gasificado para PLC Siemens S7-1200
- Ventana principal con START / STOP, lectura de PPM y estado de conexión
- Ventana de configuración para seleccionar qué tags del PLC usar (desde plc_tags_config.json)
- Ventana emergente cuando se activa ALERTA1 con opción de Continuar que escribe CONFIRM1=1
"""
import sys
import os
import json
import time
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QDialog, QFormLayout, QComboBox, QMessageBox, QLineEdit,
    QGroupBox, QGridLayout, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPalette, QColor, QFont, QIntValidator

from plc_connection import PLCConnection

CONFIG_TAGS_FILE = "plc_tags_config.json"  # Fuente de verdad de los tags
GASIFICADO_CONFIG_FILE = "gasificado_config.json"  # Preferencias de asignación de roles
PULSE_MS = 200  # Duración del pulso en milisegundos


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
    """Lee el valor del tag según su tipo.
    tag: {'tag_type','address','data_type','bit','db_number'}
    """
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


# ================= Monitor de PPM y Alerta =================

class GasificadoMonitorThread(QThread):
    ppm_updated = pyqtSignal(object)  # int o float
    alerta_changed = pyqtSignal(bool)
    connection_status = pyqtSignal(bool)
    set1_updated = pyqtSignal(object)

    def __init__(self, plc: PLCConnection, tags_by_name: dict, mapping: dict, interval_sec: float = 1.0):
        super().__init__()
        self.plc = plc
        self.tags_by_name = tags_by_name
        self.mapping = mapping or {}
        self.running = False
        self.interval = max(0.1, interval_sec)
        self._last_alert_state = None

    def run(self):
        self.running = True
        while self.running:
            connected = self.plc.is_connected()
            self.connection_status.emit(bool(connected))

            if connected:
                # Leer PPM si está configurado
                ppm_tag_name = self.mapping.get('ppm_tag')
                if ppm_tag_name:
                    tag = self.tags_by_name.get(ppm_tag_name)
                    try:
                        ppm_val = read_tag_value(self.plc, tag)
                    except Exception:
                        ppm_val = None
                    self.ppm_updated.emit(ppm_val)

                # Leer ALERTA1 si está configurado
                alerta_tag_name = self.mapping.get('alerta_tag')
                if alerta_tag_name:
                    tag = self.tags_by_name.get(alerta_tag_name)
                    try:
                        val = read_tag_value(self.plc, tag)
                        alerta_now = bool(val)
                    except Exception:
                        alerta_now = False
                    if self._last_alert_state is None or alerta_now != self._last_alert_state:
                        self.alerta_changed.emit(alerta_now)
                        self._last_alert_state = alerta_now

                # Leer SET1 si está configurado
                set1_tag_name = self.mapping.get('set1_tag')
                if set1_tag_name:
                    tag = self.tags_by_name.get(set1_tag_name)
                    try:
                        set1_val = read_tag_value(self.plc, tag)
                    except Exception:
                        set1_val = None
                    self.set1_updated.emit(set1_val)
            time.sleep(self.interval)

    def stop(self):
        self.running = False


# ================= Diálogo de Configuración =================

class ConfigDialog(QDialog):
    def __init__(self, parent, tags_cfg: dict, current_mapping: dict):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Gasificado")
        self.setModal(True)
        self.resize(480, 320)

        self.tags_cfg = tags_cfg
        self.tags_by_name = get_tags_index_by_name(tags_cfg)
        self.mapping = dict(current_mapping or {})

        # UI
        main_layout = QVBoxLayout()

        # Conexión PLC
        plc_box = QGroupBox("Conexión PLC")
        plc_form = QFormLayout()
        self.ip_edit = QLineEdit(tags_cfg.get('plc_connection', {}).get('ip_address', '192.168.0.1'))
        self.rack_edit = QLineEdit(str(tags_cfg.get('plc_connection', {}).get('rack', 0)))
        self.slot_edit = QLineEdit(str(tags_cfg.get('plc_connection', {}).get('slot', 1)))
        plc_form.addRow("IP:", self.ip_edit)
        plc_form.addRow("Rack:", self.rack_edit)
        plc_form.addRow("Slot:", self.slot_edit)
        plc_box.setLayout(plc_form)

        # Selección de Tags
        tags_box = QGroupBox("Asignación de Tags")
        tags_form = QFormLayout()

        names = sorted(self.tags_by_name.keys())
        def make_combo(placeholder: str, allow_none=False):
            cb = QComboBox()
            if allow_none:
                cb.addItem("— Ninguno —", userData=None)
            else:
                cb.addItem("— Seleccionar —", userData=None)
            for n in names:
                cb.addItem(n, userData=n)
            cb.setEditable(False)
            cb.setCurrentIndex(0)
            cb.setPlaceholderText(placeholder)
            return cb

        self.cb_start = make_combo("Start Tag")
        self.cb_stop = make_combo("Stop Tag", allow_none=True)
        self.cb_ppm = make_combo("PPM Tag")
        self.cb_alerta = make_combo("Alerta Tag")
        self.cb_confirm = make_combo("Confirm Tag")
        self.cb_set1 = make_combo("SET1 Tag", allow_none=True)

        tags_form.addRow("START:", self.cb_start)
        tags_form.addRow("STOP:", self.cb_stop)
        tags_form.addRow("Concentración PPM:", self.cb_ppm)
        tags_form.addRow("ALERTA1:", self.cb_alerta)
        tags_form.addRow("CONFIRM1:", self.cb_confirm)
        tags_form.addRow("SET1:", self.cb_set1)
        tags_box.setLayout(tags_form)

        # Botones
        btns = QHBoxLayout()
        btn_save = QPushButton("Guardar")
        btn_cancel = QPushButton("Cancelar")
        btns.addStretch(1)
        btns.addWidget(btn_save)
        btns.addWidget(btn_cancel)

        main_layout.addWidget(plc_box)
        main_layout.addWidget(tags_box)
        main_layout.addLayout(btns)
        self.setLayout(main_layout)

        # Cargar selección actual
        self._apply_current_selection()

        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self.on_save)

    def _apply_current_selection(self):
        def set_combo(cb: QComboBox, value: str):
            if not value:
                cb.setCurrentIndex(0)
                return
            ix = cb.findData(value)
            cb.setCurrentIndex(ix if ix >= 0 else 0)

        set_combo(self.cb_start, self.mapping.get('start_tag'))
        set_combo(self.cb_stop, self.mapping.get('stop_tag'))
        set_combo(self.cb_ppm, self.mapping.get('ppm_tag'))
        set_combo(self.cb_alerta, self.mapping.get('alerta_tag'))
        set_combo(self.cb_confirm, self.mapping.get('confirm_tag'))
        set_combo(self.cb_set1, self.mapping.get('set1_tag'))

    def on_save(self):
        start = self.cb_start.currentData()
        alerta = self.cb_alerta.currentData()
        confirm = self.cb_confirm.currentData()
        # Validación mínima
        if not start or not alerta or not confirm:
            QMessageBox.warning(self, "Faltan datos", "Debes seleccionar al menos START, ALERTA1 y CONFIRM1.")
            return

        mapping = {
            'start_tag': start,
            'stop_tag': self.cb_stop.currentData(),
            'ppm_tag': self.cb_ppm.currentData(),
            'alerta_tag': alerta,
            'confirm_tag': confirm,
            'set1_tag': self.cb_set1.currentData(),
            'plc_connection': {
                'ip_address': self.ip_edit.text().strip() or '192.168.0.1',
                'rack': int(self.rack_edit.text() or 0),
                'slot': int(self.slot_edit.text() or 1),
            },
            'last_saved': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'version': '1.1'
        }

        # Guardar a archivo
        try:
            with open(GASIFICADO_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar configuración: {e}")
            return

        self.mapping = mapping
        self.accept()


# ================= Ventana Principal =================

class GasificadoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gasificado - S7-1200")
        self.resize(560, 340)

        self.plc = PLCConnection()
        self.tags_cfg = None
        self.tags_by_name = {}
        self.mapping = {}

        self.monitor_thread = None
        self.alert_dialog_open = False

        self._build_ui()
        self._load_configs()
        self._auto_connect_and_start()

    # ----- Construcción UI -----
    def _build_ui(self):
        central = QWidget()
        main_layout = QVBoxLayout()

        # Estado de conexión
        status_layout = QHBoxLayout()
        self.lbl_status = QLabel("Estado: Desconectado")
        self.lbl_status.setStyleSheet("color: #ff6666;")
        self.btn_connect = QPushButton("Conectar")
        self.btn_connect.clicked.connect(self.on_toggle_connect)
        status_layout.addWidget(self.lbl_status)
        status_layout.addStretch(1)
        status_layout.addWidget(self.btn_connect)

        # PPM
        ppm_box = QGroupBox("Concentración")
        ppm_layout = QHBoxLayout()
        self.lbl_ppm_title = QLabel("PPM:")
        self.lbl_ppm_title.setFixedWidth(60)
        self.lbl_ppm = QLabel("—")
        self.lbl_ppm.setFont(QFont("Segoe UI", 20, QFont.Bold))
        ppm_layout.addWidget(self.lbl_ppm_title)
        ppm_layout.addWidget(self.lbl_ppm)
        ppm_layout.addStretch(1)
        ppm_box.setLayout(ppm_layout)

        # SET1 (Setpoint)
        set_box = QGroupBox("SET1 (Setpoint)")
        set_layout = QHBoxLayout()
        self.lbl_set1_title = QLabel("Actual:")
        self.lbl_set1 = QLabel("—")
        self.lbl_set1.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.edit_set1 = QLineEdit()
        self.edit_set1.setPlaceholderText("Nuevo valor…")
        self.edit_set1.setValidator(QIntValidator())
        self.edit_set1.setFixedWidth(120)
        self.btn_apply_set1 = QPushButton("Aplicar")
        self.btn_apply_set1.clicked.connect(self.on_apply_set1)
        set_layout.addWidget(self.lbl_set1_title)
        set_layout.addWidget(self.lbl_set1)
        set_layout.addStretch(1)
        set_layout.addWidget(QLabel("Nuevo:"))
        set_layout.addWidget(self.edit_set1)
        set_layout.addWidget(self.btn_apply_set1)
        set_box.setLayout(set_layout)

        # Botones START/STOP
        btns_layout = QHBoxLayout()
        self.btn_start = QPushButton("START")
        self.btn_stop = QPushButton("STOP")
        self.btn_config = QPushButton("Configuración…")
        self.btn_start.setStyleSheet("font-weight:bold; background:#2e7d32; color:white; padding:8px;")
        self.btn_stop.setStyleSheet("font-weight:bold; background:#c62828; color:white; padding:8px;")

        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_config.clicked.connect(self.on_open_config)

        btns_layout.addWidget(self.btn_start)
        btns_layout.addWidget(self.btn_stop)
        btns_layout.addStretch(1)
        btns_layout.addWidget(self.btn_config)

        main_layout.addLayout(status_layout)
        main_layout.addWidget(ppm_box)
        main_layout.addWidget(set_box)
        main_layout.addLayout(btns_layout)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    # ----- Carga de configuración -----
    def _load_configs(self):
        # Cargar tags disponibles
        try:
            self.tags_cfg = load_tags_config(CONFIG_TAGS_FILE)
            self.tags_by_name = get_tags_index_by_name(self.tags_cfg)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo cargar {CONFIG_TAGS_FILE}: {e}")
            self.tags_cfg = {'plc_connection': {'ip_address': '192.168.0.1', 'rack': 0, 'slot': 1}, 'tags': []}
            self.tags_by_name = {}

        # Cargar asignaciones previas, si existen
        if os.path.exists(GASIFICADO_CONFIG_FILE):
            try:
                with open(GASIFICADO_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.mapping = json.load(f)
            except Exception:
                self.mapping = {}
        else:
            self.mapping = {}

        # Defaults intuitivos si no existen
        defaults = {
            'start_tag': 'START1' if 'START1' in self.tags_by_name else None,
            'stop_tag': None,
            'ppm_tag': None,  # El usuario debe seleccionar uno numérico
            'alerta_tag': 'ALERTA1' if 'ALERTA1' in self.tags_by_name else None,
            'confirm_tag': 'CONFIRM1' if 'CONFIRM1' in self.tags_by_name else None,
            'set1_tag': 'SET1' if 'SET1' in self.tags_by_name else None,
            'plc_connection': self.tags_cfg.get('plc_connection', {'ip_address': '192.168.0.1', 'rack': 0, 'slot': 1})
        }
        for k, v in defaults.items():
            self.mapping.setdefault(k, v)

    # ----- Conexión automática -----
    def _auto_connect_and_start(self):
        conn = self.mapping.get('plc_connection') or {}
        ip = conn.get('ip_address') or self.tags_cfg.get('plc_connection', {}).get('ip_address')
        rack = int(conn.get('rack', self.tags_cfg.get('plc_connection', {}).get('rack', 0)))
        slot = int(conn.get('slot', self.tags_cfg.get('plc_connection', {}).get('slot', 1)))

        if ip:
            self._connect_plc(ip, rack, slot)
        else:
            self._update_status(False)

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
            self.lbl_status.setText("Estado: Conectado")
            self.lbl_status.setStyleSheet("color: #66bb6a;")
        else:
            self.lbl_status.setText("Estado: Desconectado")
            self.lbl_status.setStyleSheet("color: #ff6666;")

    def _start_monitor(self):
        self._stop_monitor()
        self.monitor_thread = GasificadoMonitorThread(self.plc, self.tags_by_name, self.mapping, interval_sec=1.0)
        self.monitor_thread.ppm_updated.connect(self.on_ppm_updated)
        self.monitor_thread.alerta_changed.connect(self.on_alerta_changed)
        self.monitor_thread.connection_status.connect(self._update_status)
        self.monitor_thread.set1_updated.connect(self.on_set1_updated)
        self.monitor_thread.start()

    def _stop_monitor(self):
        if self.monitor_thread:
            self.monitor_thread.stop()
            self.monitor_thread.wait(1500)
            self.monitor_thread = None

    # ----- Slots UI -----
    def on_toggle_connect(self):
        if self.plc.is_connected():
            self._disconnect_plc()
        else:
            conn = self.mapping.get('plc_connection') or {}
            ip = conn.get('ip_address') or self.tags_cfg.get('plc_connection', {}).get('ip_address')
            rack = int(conn.get('rack', self.tags_cfg.get('plc_connection', {}).get('rack', 0)))
            slot = int(conn.get('slot', self.tags_cfg.get('plc_connection', {}).get('slot', 1)))
            self._connect_plc(ip, rack, slot)

    def on_ppm_updated(self, value):
        if value is None:
            self.lbl_ppm.setText("—")
        else:
            try:
                # Mostrar con formato simple
                if isinstance(value, float):
                    self.lbl_ppm.setText(f"{value:.2f}")
                else:
                    self.lbl_ppm.setText(str(value))
            except Exception:
                self.lbl_ppm.setText(str(value))

    def _get_tag(self, key: str):
        name = self.mapping.get(key)
        return self.tags_by_name.get(name) if name else None

    def _pulse_tag(self, tag: dict):
        """Escribe un pulso (1/True) y luego resetea (0/False) tras PULSE_MS."""
        dt = (tag.get('data_type') or '').lower()
        active = True if dt == 'bool' else 1
        reset = False if dt == 'bool' else 0
        ok = write_tag_value(self.plc, tag, active)
        if not ok:
            return False
        # Programar reset
        QTimer.singleShot(PULSE_MS, lambda: write_tag_value(self.plc, tag, reset))
        return True

    def on_start(self):
        if not self.plc.is_connected():
            QMessageBox.warning(self, "No conectado", "Conéctate al PLC antes de iniciar.")
            return
        tag = self._get_tag('start_tag')
        if not tag:
            QMessageBox.warning(self, "Sin START", "Selecciona el tag START en Configuración.")
            return
        ok = self._pulse_tag(tag)
        if not ok:
            QMessageBox.critical(self, "Error", "No se pudo escribir START.")

    def on_stop(self):
        if not self.plc.is_connected():
            QMessageBox.warning(self, "No conectado", "Conéctate al PLC antes de detener.")
            return
        stop_tag = self._get_tag('stop_tag')
        if stop_tag:
            ok = self._pulse_tag(stop_tag)
        else:
            # Si no hay STOP configurado, advertimos y no hacemos nada (recomendado para pulsos)
            QMessageBox.warning(self, "Sin STOP", "Selecciona el tag STOP en Configuración para enviar un pulso de STOP.")
            return
        if not ok:
            QMessageBox.critical(self, "Error", "No se pudo ejecutar STOP.")

    def on_set1_updated(self, value):
        try:
            if value is None:
                self.lbl_set1.setText("—")
            else:
                if isinstance(value, float):
                    self.lbl_set1.setText(f"{value:.2f}")
                else:
                    self.lbl_set1.setText(str(int(value)))
        except Exception:
            self.lbl_set1.setText(str(value))

    def on_apply_set1(self):
        if not self.plc.is_connected():
            QMessageBox.warning(self, "No conectado", "Conéctate al PLC antes de escribir SET1.")
            return
        tag = self._get_tag('set1_tag')
        if not tag:
            QMessageBox.warning(self, "SET1 no configurado", "Selecciona el tag SET1 en Configuración.")
            return
        txt = self.edit_set1.text().strip()
        if not txt:
            QMessageBox.warning(self, "Valor vacío", "Introduce un valor entero para SET1.")
            return
        dt = (tag.get('data_type') or '').lower()
        try:
            if dt == 'int':
                val = int(txt)
            elif dt == 'real':
                # Por si el tag se definiera como REAL
                val = float(txt)
            else:
                QMessageBox.warning(self, "Tipo no soportado", f"SET1 data_type '{dt}' no soportado para escritura.")
                return
        except ValueError:
            QMessageBox.warning(self, "Formato inválido", "El valor debe ser numérico.")
            return
        ok = write_tag_value(self.plc, tag, val)
        if ok:
            self.edit_set1.clear()
        else:
            QMessageBox.critical(self, "Error", "No se pudo escribir SET1.")

    def on_open_config(self):
        dlg = ConfigDialog(self, self.tags_cfg, self.mapping)
        if dlg.exec_() == QDialog.Accepted:
            # Actualizar mapping y conexión si cambió
            self.mapping = dlg.mapping
            # Releer tags_cfg por si se editó externamente
            try:
                self.tags_cfg = load_tags_config(CONFIG_TAGS_FILE)
                self.tags_by_name = get_tags_index_by_name(self.tags_cfg)
            except Exception:
                pass
            # Reiniciar monitor
            if self.plc.is_connected():
                self._start_monitor()

    def on_alerta_changed(self, active: bool):
        if active and not self.alert_dialog_open:
            self.alert_dialog_open = True
            try:
                # Mostrar diálogo modal con opción Continuar
                m = QMessageBox(self)
                m.setWindowTitle("ALERTA1 activa")
                m.setIcon(QMessageBox.Warning)
                m.setText("Se ha activado ALERTA1. ¿Deseas continuar?")
                btn_continue = m.addButton("Continuar", QMessageBox.AcceptRole)
                m.addButton("Cancelar", QMessageBox.RejectRole)
                m.setDefaultButton(btn_continue)
                m.exec_()

                if m.clickedButton() == btn_continue:
                    # Escribir CONFIRM1 = 1
                    confirm_tag = self._get_tag('confirm_tag')
                    if confirm_tag:
                        ok = write_tag_value(self.plc, confirm_tag, 1)
                        if not ok:
                            QMessageBox.critical(self, "Error", "No se pudo escribir CONFIRM1=1.")
            finally:
                # Pequeño retardo para evitar re-apertura inmediata
                QTimer.singleShot(500, lambda: setattr(self, 'alert_dialog_open', False))

    def closeEvent(self, event):
        try:
            self._stop_monitor()
            if self.plc.is_connected():
                self.plc.disconnect()
        finally:
            super().closeEvent(event)


def apply_dark_theme(app: QApplication):
    app.setStyle('Fusion')
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


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    w = GasificadoWindow()
    w.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
