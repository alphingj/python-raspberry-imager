#!/usr/bin/env python3
import sys
import os
import json
import subprocess
import shutil
import zipfile
import lzma
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QProgressBar, QFileDialog,
    QGroupBox, QCheckBox, QLineEdit, QMessageBox, QListWidget,
    QListWidgetItem, QSplitter, QTextEdit
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap


CACHE_DIR = os.path.expanduser('~/.cache/rpi-imager')
CACHE_FILE = os.path.join(CACHE_DIR, 'os-list.json')
OS_API_URL = 'https://downloads.raspberrypi.org/os_list.json'


class FlashWorker(QThread):
    progress = pyqtSignal(int, int, float)
    finished = pyqtSignal(bool, str)
    log = pyqtSignal(str)

    def __init__(self, image_path, device_path, config=None):
        super().__init__()
        self.image_path = image_path
        self.device_path = device_path
        self.config = config or {}

    def run(self):
        try:
            self.log.emit(f"Starting flash to {self.device_path}...")
            if self.image_path.endswith('.xz'):
                self.log.emit("Decompressing XZ file...")
                decompressed = self._decompress_xz()
                self._write_image(decompressed)
            elif self.image_path.endswith('.zip'):
                self.log.emit("Decompressing ZIP file...")
                decompressed = self._decompress_zip()
                self._write_image(decompressed)
            else:
                self._write_image(self.image_path)
            self.finished.emit(True, "Flash complete!")
        except Exception as e:
            self.finished.emit(False, f"Flash failed: {e}")

    def _decompress_xz(self):
        import lzma
        dec_path = self.image_path[:-3] if self.image_path.endswith('.img.xz') else self.image_path + '.decompressed'
        with lzma.open(self.image_path, 'rb') as f_in:
            with open(dec_path, 'wb') as f_out:
                while chunk := f_in.read(8192 * 1024):
                    f_out.write(chunk)
        return dec_path

    def _decompress_zip(self):
        with zipfile.ZipFile(self.image_path, 'r') as z:
            names = z.namelist()
            if not names:
                raise ValueError("Empty ZIP file")
            img_name = next((n for n in names if n.endswith('.img')), names[0])
            z.extract(img_name, CACHE_DIR)
            return os.path.join(CACHE_DIR, img_name)

    def _write_image(self, path):
        total = os.path.getsize(path)
        written = 0
        with open(path, 'rb') as img, open(self.device_path, 'wb') as dev:
            while True:
                chunk = img.read(1024 * 1024)
                if not chunk:
                    break
                dev.write(chunk)
                written += len(chunk)
                pct = int(written / total * 100)
                speed = written / max((written / 1024 / 1024) * 100, 0.1)
                self.progress.emit(written, total, speed)
                self.msleep(10)


class RPiImager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Raspberry Pi Imager')
        self.resize(1000, 650)
        self.selected_image = None
        self.selected_os = None
        self.os_list = []
        self.device_type = 'Pi4'
        self.init_ui()
        self.load_os_list()
        self.detect_devices()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)

        # Left panel - OS list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)

        left_layout.addWidget(QLabel('<h2 style="margin: 0;">Operating Systems</h2>'))

        self.os_filter = QComboBox()
        self.os_filter.addItems(['All', 'Recommended', 'Raspberry Pi OS', 'Media', 'Emulation', 'Utilities'])
        self.os_filter.currentTextChanged.connect(self.filter_os_list)
        left_layout.addWidget(self.os_filter)

        self.os_list_widget = QListWidget()
        self.os_list_widget.itemClicked.connect(self.on_os_selected)
        left_layout.addWidget(self.os_list_widget)

        # Right panel - controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)

        # Device type
        type_group = QGroupBox('Device Type')
        type_layout = QVBoxLayout(type_group)
        self.device_type_combo = QComboBox()
        self.device_type_combo.addItems(['Raspberry Pi 5', 'Raspberry Pi 4/400', 'Raspberry Pi 3', 'Raspberry Pi 2', 'Raspberry Pi 1', 'Pi Zero/1', 'Compute Module'])
        self.device_type_combo.currentIndexChanged.connect(self.on_device_type_changed)
        type_layout.addWidget(self.device_type_combo)
        right_layout.addWidget(type_group)

        # Device selection
        dev_group = QGroupBox('Target Device')
        dev_layout = QVBoxLayout(dev_group)
        self.device_combo = QComboBox()
        self.device_combo.addItem('No device detected')
        dev_layout.addWidget(self.device_combo)
        refresh_btn = QPushButton('Refresh Devices')
        refresh_btn.clicked.connect(self.detect_devices)
        dev_layout.addWidget(refresh_btn)
        right_layout.addWidget(dev_group)

        # File selection
        file_group = QGroupBox('Image File')
        file_layout = QHBoxLayout(file_group)
        self.file_label = QLabel('No file selected')
        self.file_label.setStyleSheet('color: #888;')
        file_layout.addWidget(self.file_label)
        browse_btn = QPushButton('Browse...')
        browse_btn.clicked.connect(self.browse_image)
        file_layout.addWidget(browse_btn)
        right_layout.addWidget(file_group)

        # Configuration
        config_group = QGroupBox('Configuration')
        config_layout = QVBoxLayout(config_group)

        self.ssh_checkbox = QCheckBox('Enable SSH')
        config_layout.addWidget(self.ssh_checkbox)

        self.ssh_pass = QLineEdit()
        self.ssh_pass.setPlaceholderText('SSH Password (optional)')
        self.ssh_pass.setEchoMode(QLineEdit.Password)
        self.ssh_pass.setEnabled(False)
        self.ssh_checkbox.toggled.connect(self.ssh_pass.setEnabled)
        config_layout.addWidget(self.ssh_pass)

        self.wifi_checkbox = QCheckBox('Configure Wi-Fi')
        config_layout.addWidget(self.wifi_checkbox)

        self.wifi_ssid = QLineEdit()
        self.wifi_ssid.setPlaceholderText('Wi-Fi SSID')
        self.wifi_ssid.setEnabled(False)
        self.wifi_checkbox.toggled.connect(self.wifi_ssid.setEnabled)
        config_layout.addWidget(self.wifi_ssid)

        self.wifi_pass = QLineEdit()
        self.wifi_pass.setPlaceholderText('Wi-Fi Password')
        self.wifi_pass.setEchoMode(QLineEdit.Password)
        self.wifi_pass.setEnabled(False)
        self.wifi_checkbox.toggled.connect(self.wifi_pass.setEnabled)
        config_layout.addWidget(self.wifi_pass)

        right_layout.addWidget(config_group)

        # Flash button
        self.flash_btn = QPushButton('Flash to Device')
        self.flash_btn.setStyleSheet('background: #0a8; color: white; font-weight: bold; padding: 12px; font-size: 14px;')
        self.flash_btn.clicked.connect(self.flash_device)
        right_layout.addWidget(self.flash_btn)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)

        self.status_label = QLabel('')
        right_layout.addWidget(self.status_label)

        # Log output
        log_group = QGroupBox('Log')
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet('background: #111; color: #0f0; font-family: monospace;')
        log_layout.addWidget(self.log_text)
        right_layout.addWidget(log_group)

        right_layout.addStretch()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def log(self, msg):
        self.log_text.append(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def on_device_type_changed(self, idx):
        self.device_type = ['Pi5', 'Pi4', 'Pi3', 'Pi2', 'Pi1', 'Zero', 'CM'][idx]

    def load_os_list(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        try:
            cached = self.load_cached_os_list()
            if cached:
                self.os_list = cached
                self.filter_os_list(self.os_filter.currentText())
                return

            import requests
            resp = requests.get(OS_API_URL, timeout=30)
            if resp.ok:
                self.os_list = resp.json().get('os_list', [])
                with open(CACHE_FILE, 'w') as f:
                    json.dump(self.os_list, f)
                self.filter_os_list(self.os_filter.currentText())
        except Exception as e:
            QMessageBox.warning(self, 'Warning', f'Could not load OS list: {e}')
            self.populate_os_list([])

    def load_cached_os_list(self):
        if os.path.exists(CACHE_FILE):
            age = os.path.getmtime(CACHE_FILE)
            if os.path.getmtime(CACHE_FILE) > os.path.getmtime(CACHE_FILE) - 3600:
                with open(CACHE_FILE) as f:
                    return json.load(f)
        return None

    def filter_os_list(self, category):
        filtered = []
        for os_entry in self.os_list:
            if not isinstance(os_entry, dict):
                continue
            name = os_entry.get('os_name', '')
            desc = os_entry.get('description', '').lower()
            if category == 'All':
                filtered.append(os_entry)
            elif category == 'Recommended':
                if 'raspberry pi os' in name.lower() or 'raspberry pi os' in desc:
                    filtered.append(os_entry)
            elif category == 'Raspberry Pi OS':
                if 'raspberry pi os' in name.lower():
                    filtered.append(os_entry)
            elif category == 'Media':
                if any(x in desc for x in ['media', 'kodi', 'osmc', 'libreelec']):
                    filtered.append(os_entry)
            elif category == 'Emulation':
                if any(x in desc for x in ['emulat', 'retropie', 'lakka']):
                    filtered.append(os_entry)
            elif category == 'Utilities':
                if any(x in desc for x in ['utility', 'data', 'recovery']):
                    filtered.append(os_entry)

        self.populate_os_list(filtered)

    def populate_os_list(self, items):
        self.os_list_widget.clear()
        if not items:
            item = QListWidgetItem('No operating systems available\nSelect an image file to flash')
            self.os_list_widget.addItem(item)
            return

        for os_entry in items:
            name = os_entry.get('os_name', 'Unknown')
            desc = os_entry.get('description', '')
            version = os_entry.get('version', '')
            size_mb = os_entry.get('nominal_size', 0)
            display = f"{name}"
            if version:
                display += f" (v{version})"
            if desc:
                display += f"\n{desc[:60]}"
            if size_mb:
                display += f" · {size_mb}MB"

            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, os_entry)
            self.os_list_widget.addItem(item)

    def on_os_selected(self, item):
        os_entry = item.data(Qt.UserRole)
        if os_entry and isinstance(os_entry, dict):
            tarballs = os_entry.get('tarballs', [])
            if tarballs and isinstance(tarballs, list) and tarballs[0]:
                self.log(f"Selected: {os_entry.get('os_name')} - download manually: {tarballs[0]}")
            else:
                url = os_entry.get('os_info', '')
                if url:
                    self.log(f"Selected: {os_entry.get('os_name')} - check {url} for image links")

    def detect_devices(self):
        self.device_combo.clear()
        devices = self.find_usb_devices()
        if devices:
            for d in devices:
                self.device_combo.addItem(d)
        else:
            self.device_combo.addItem('No removable device detected')

    def find_usb_devices(self):
        devices = []
        try:
            result = subprocess.run(['lsblk', '-d', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT,MODEL,TRAN', '-J'],
                                  capture_output=True, text=True)
            data = json.loads(result.stdout)
            for dev in data.get('blockdevices', []):
                if dev.get('type') == 'disk' and dev.get('mountpoint') is None:
                    if dev.get('tran') in ('usb', None):
                        model = dev.get('model', 'Unknown')[:20]
                        size = dev.get('size', '?')
                        name = dev['name']
                        devices.append(f"/dev/{name} ({size}) - {model}")
        except Exception:
            pass
        return devices

    def browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select Image File', '',
            'Image Files (*.img *.img.xz *.zip *.iso);;All Files (*)'
        )
        if path:
            self.selected_image = path
            self.file_label.setText(os.path.basename(path))
            self.file_label.setStyleSheet('color: white;')

    def flash_device(self):
        if not self.selected_image:
            QMessageBox.warning(self, 'Error', 'Please select an image file first.')
            return
        if self.device_combo.currentIndex() <= 0:
            QMessageBox.warning(self, 'Error', 'Please select a target device.')
            return

        current_text = self.device_combo.currentText()
        device_path = current_text.split()[0]

        reply = QMessageBox.question(self, 'Confirm',
            f'Write {os.path.basename(self.selected_image)} to {device_path}?\n\nThis will erase all data on the device.',
            QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            config = {
                'ssh_enabled': self.ssh_checkbox.isChecked(),
                'ssh_password': self.ssh_pass.text(),
                'wifi_ssid': self.wifi_ssid.text() if self.wifi_checkbox.isChecked() else '',
                'wifi_password': self.wifi_pass.text() if self.wifi_checkbox.isChecked() else '',
            }
            self.start_flash(device_path, self.selected_image, config)

    def start_flash(self, device, image_path, config):
        self.flash_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.status_label.setText('Flashing...')
        self.log(f"Writing to {device}...")

        self.flash_thread = FlashWorker(image_path, device, config)
        self.flash_thread.progress.connect(self.update_progress)
        self.flash_thread.finished.connect(self.flash_finished)
        self.flash_thread.log.connect(self.log)
        self.flash_thread.start()

    def update_progress(self, written, total, speed):
        pct = int(written / total * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"{self.format_size(written)} / {self.format_size(total)} ({self.format_size(speed)}/s)")

    def flash_finished(self, success, message):
        self.flash_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(message)
        if success:
            QMessageBox.information(self, 'Success', message)
        else:
            QMessageBox.critical(self, 'Error', message)

    def format_size(self, bytes_val):
        if not bytes_val: return '0 B'
        k = 1024
        sizes = ['B', 'KB', 'MB', 'GB', 'TB']
        i = int(bytes_val / k ** (len(sizes) - 1))
        if i < 1:
            i = 0
            while bytes_val >= k and i < len(sizes) - 1:
                bytes_val /= k
                i += 1
        return f"{bytes_val:.1f} {sizes[i]}"


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = RPiImager()
    window.show()
    sys.exit(app.exec_())