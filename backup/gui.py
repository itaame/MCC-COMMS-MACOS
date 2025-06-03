#!/usr/bin/env python3
import sys, time, threading, json, os
import requests
import sounddevice as sd
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QComboBox, QPushButton, QGroupBox, QFrame, QSizePolicy, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QIcon
from soundwave import SoundwaveWidget  # Custom widget for mic audio visualization
from config_dialog import read_config

# === LOAD LOOPS BASED ON ROLE ===
config = read_config()
if config is None:
    print("No config file found. Please run config dialog first.")
    sys.exit(1)
role = config.get("role", "FLIGHT")
loop_file = os.path.join("LOOPS", f"loops_{role.upper()}.txt")
try:
    with open(loop_file, "r") as f:
        LOOPS = json.load(f)
except Exception as e:
    print(f"Error loading {loop_file}: {e}")
    LOOPS = []

BOTS = [
    {"name": "BOT1", "port": 6001},
    {"name": "BOT2", "port": 6002},
    {"name": "BOT3", "port": 6003},
]
POLL_INTERVAL = 1.0

class LoopButtonWidget(QFrame):
    clicked = pyqtSignal(str)
    off_clicked = pyqtSignal(str)
    volume_changed = pyqtSignal(str, float)  # loop_name, volume (0.0-1.0)

    def __init__(self, loop_cfg, parent=None):
        super().__init__(parent)
        self.loop_cfg = loop_cfg
        self.loop_name = loop_cfg["name"]
        BUTTON_SIZE = 170
        ICON_ROW_HEIGHT = 28
        BORDER = 4
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(2)
        self.setFixedSize(BUTTON_SIZE, BUTTON_SIZE)
        self.setStyleSheet("background-color: #cccccc; border-radius: 20px;")
        self.icon_label = QLabel(self)
        icons = []
        if loop_cfg.get("can_listen"): icons.append("🎧")
        if loop_cfg.get("can_talk"): icons.append("🎤")
        self.icon_label.setText(" ".join(icons))
        self.icon_label.setFixedHeight(ICON_ROW_HEIGHT)
        self.icon_label.setGeometry(8, 8, 50, ICON_ROW_HEIGHT)
        self.count_label = QLabel("👥0", self)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.count_label.setFixedHeight(ICON_ROW_HEIGHT)
        self.count_label.setGeometry(BUTTON_SIZE - 54, 8, 50, ICON_ROW_HEIGHT)
        self.name_label = QLabel(self.loop_name, self)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.name_label.setFixedWidth(BUTTON_SIZE - 2*BORDER)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # --- OFF BUTTON ---
        self.off_btn = QPushButton("OFF", self)
        self.off_btn.setStyleSheet("background-color: #b41b1b; color: white; font-weight: bold; border-radius: 7px;")
        self.off_btn.setFixedSize(44, 26)
        self.off_btn.move(BUTTON_SIZE-56, BUTTON_SIZE-32)
        self.off_btn.clicked.connect(lambda: self.off_clicked.emit(self.loop_name))

        # --- VOLUME BUTTON ---
        self.vol_btn = QPushButton("🔊", self)
        self.vol_btn.setStyleSheet("background-color: #aaa; font-size: 18px; border-radius: 7px;")
        self.vol_btn.setFixedSize(36, 26)
        self.vol_btn.move(12, BUTTON_SIZE-32)
        self.vol_btn.clicked.connect(self.toggle_volume_slider)

        # --- VOLUME SLIDER (hidden by default) ---
        self.slider = QSlider(Qt.Orientation.Vertical, self)
        self.slider.setRange(20, 100)
        self.slider.setValue(100)
        self.slider.setFixedHeight(75)
        self.slider.setFixedWidth(30)
        self.slider.hide()
        self.slider.move(16, BUTTON_SIZE-110)
        self.slider.valueChanged.connect(self._slider_changed)
        self.slider.setStyleSheet("background-color: #b3d8fd;")
        self.slider_visible = False

    def set_bg(self, color):
        self.setStyleSheet(f"background-color: {color}; border-radius: 20px;")
    def set_count(self, n):
        self.count_label.setText(f"👥{n}")
    def mousePressEvent(self, e):
        if self.isEnabled():
            pos = e.position() if hasattr(e, "position") else e.pos()
            # Only handle click if not on the off or volume button
            if not self.off_btn.geometry().contains(int(pos.x()), int(pos.y())) \
               and not self.vol_btn.geometry().contains(int(pos.x()), int(pos.y())) \
               and not self.slider.geometry().contains(int(pos.x()), int(pos.y())):
                self.clicked.emit(self.loop_name)
    def resizeEvent(self, event):
        BUTTON_SIZE = self.width()
        ICON_ROW_HEIGHT = 28
        BORDER = 4
        label_width = BUTTON_SIZE - 2*BORDER
        self.name_label.setFixedWidth(label_width)
        self.name_label.adjustSize()
        label_height = self.name_label.sizeHint().height()
        top = (BUTTON_SIZE - label_height) // 2
        self.name_label.setGeometry(BORDER, top, label_width, label_height)
        self.icon_label.setGeometry(8, 8, 50, ICON_ROW_HEIGHT)
        self.count_label.setGeometry(BUTTON_SIZE - 54, 8, 50, ICON_ROW_HEIGHT)
        self.off_btn.move(BUTTON_SIZE-56, BUTTON_SIZE-32)
        self.vol_btn.move(12, BUTTON_SIZE-32)
        self.slider.move(16, BUTTON_SIZE-110)
        super().resizeEvent(event)

    def toggle_volume_slider(self):
        if not self.slider_visible:
            self.slider.show()
            self.slider_visible = True
        else:
            self.slider.hide()
            self.slider_visible = False

    def _slider_changed(self, value):
        self.volume_changed.emit(self.loop_name, value / 100.0)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MCC Voice Loops Controller")
        self.resize(900, 480)
        self.delay_enabled = False
        self.delay_seconds = 3
        self.loop_states = {loop["name"]: (0, None) for loop in LOOPS}
        self.user_counts = {loop["name"]: 0 for loop in LOOPS}
        self.buttons     = {}
        self.loop_configs = {loop["name"]: loop for loop in LOOPS}
        self.bot_pool = {b["name"]: {"port": b["port"], "assigned": None, "last_used": 0} for b in BOTS}

        layout = QVBoxLayout(self)

        # --- Audio device selection ---
        devs = sd.query_devices()
        ins  = [(i, d['name']) for i, d in enumerate(devs) if d['max_input_channels']>0]
        outs = [(i, d['name']) for i, d in enumerate(devs) if d['max_output_channels']>0]
        device_group = QGroupBox("Audio Devices")
        device_layout = QHBoxLayout()
        device_layout.setContentsMargins(8, 4, 8, 4)
        device_layout.setSpacing(10)
        self.in_combo  = QComboBox()
        self.out_combo = QComboBox()
        for i,n in ins:  self.in_combo.addItem(f"{i}: {n}", i)
        for i,n in outs: self.out_combo.addItem(f"{i}: {n}", i)
        self.in_combo.currentIndexChanged.connect(self.on_in_changed)
        self.out_combo.currentIndexChanged.connect(self.on_out_changed)
        self.in_combo.setMaximumHeight(28)
        self.out_combo.setMaximumHeight(28)
        device_layout.addWidget(QLabel("Input:"))
        device_layout.addWidget(self.in_combo)
        device_layout.addSpacing(20)
        device_layout.addWidget(QLabel("Output:"))
        device_layout.addWidget(self.out_combo)
        device_layout.addStretch()
        self.soundwave_widget = SoundwaveWidget()
        device_layout.addWidget(self.soundwave_widget, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.delay_btn = QPushButton("DELAY")
        self.delay_btn.setCheckable(True)
        self.delay_btn.setFixedSize(65, 45)
        self._update_delay_btn_style()
        self.delay_btn.clicked.connect(self.toggle_delay)
        device_layout.addWidget(self.delay_btn, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        device_group.setLayout(device_layout)
        device_group.setMaximumHeight(70)
        layout.addWidget(device_group)

        # --- Mic audio monitor ---
        self._audio_level = 0
        self._audio_monitor_running = True
        self._audio_thread = None
        self._audio_input_idx = self.in_combo.currentData() or 0
        self._start_audio_monitor()

        # --- Loop buttons grid ---
        grid = QGridLayout()
        row = col = 0
        for loop in LOOPS:
            btn = LoopButtonWidget(loop)
            btn.clicked.connect(self.on_loop_clicked)
            btn.off_clicked.connect(self.on_loop_off_clicked)
            btn.volume_changed.connect(self.on_volume_changed)
            btn.setEnabled(loop["can_listen"])
            self.buttons[loop["name"]] = btn
            grid.addWidget(btn, row, col)
            col = (col + 1) % 4
            if col == 0:
                row += 1
        layout.addLayout(grid)

        # --- Logo / bottom bar ---
        logo_label = QLabel()
        pixmap = QPixmap("logo.png")
        if not pixmap.isNull():
            logo_size = 70
            scaled = pixmap.scaledToHeight(logo_size, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        logo_label.setMaximumHeight(logo_size)
        logo_label.setMaximumWidth(logo_size*4)
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(logo_label, stretch=0, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(bottom_layout)
        self.setLayout(layout)
        self._start_poll()

    def _update_delay_btn_style(self):
        if self.delay_enabled:
            self.delay_btn.setStyleSheet("background-color: #43d843; color: white; font-weight: bold;")
        else:
            self.delay_btn.setStyleSheet("background-color: #c22c2c; color: white; font-weight: bold;")

    def toggle_delay(self):
        self.delay_enabled = not self.delay_enabled
        self._update_delay_btn_style()
        try:
            for bot in self.bot_pool.values():
                if self.delay_enabled:
                    requests.post(f"http://127.0.0.1:{bot['port']}/delay_on", json={"seconds": self.delay_seconds})
                else:
                    requests.post(f"http://127.0.0.1:{bot['port']}/delay_off")
        except:
            pass

    def _start_audio_monitor(self):
        if hasattr(self, '_audio_monitor_running'):
            self._audio_monitor_running = False
            time.sleep(0.07)
        self._audio_monitor_running = True
        self._audio_input_idx = self.in_combo.currentData() or 0
        def audio_thread_func():
            while self._audio_monitor_running:
                idx = self.in_combo.currentData() or 0
                try:
                    with sd.InputStream(device=idx, channels=1, samplerate=16000, blocksize=512) as stream:
                        while self._audio_monitor_running:
                            data, _ = stream.read(512)
                            level = np.abs(data).mean()
                            self._audio_level = float(level)
                            time.sleep(0.025)
                except Exception:
                    self._audio_level = 0
                    time.sleep(0.5)
        self._audio_thread = threading.Thread(target=audio_thread_func, daemon=True)
        self._audio_thread.start()
        self._audio_timer = QTimer(self)
        self._audio_timer.timeout.connect(self._update_soundwave)
        self._audio_timer.start(50)

    def _update_soundwave(self):
        amp = min(self._audio_level * 35.0, 1.0)
        freq = 1.5 + amp * 4.5
        self.soundwave_widget.set_wave_params(amp, freq)

    def on_in_changed(self, _):
        self._start_audio_monitor()
        idx = self.in_combo.currentData()
        for bot in self.bot_pool.values():
            try:
                requests.post(f"http://127.0.0.1:{bot['port']}/device_in", json={"device": idx})
            except:
                pass

    def on_out_changed(self, _):
        idx = self.out_combo.currentData()
        for bot in self.bot_pool.values():
            try:
                requests.post(f"http://127.0.0.1:{bot['port']}/device_out", json={"device": idx})
            except:
                pass

    def closeEvent(self, event):
        self._audio_monitor_running = False
        event.accept()

    def _set_button_state(self, loop_name):
        state, _ = self.loop_states[loop_name]
        btn = self.buttons[loop_name]
        if state == 0:
            color = "#cccccc"
        elif state == 1:
            color = "#87cefa"
        else:
            color = "#90ee90"
        btn.set_bg(color)
        btn.set_count(self.user_counts.get(loop_name, 0))

    def _start_poll(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll_status)
        self.timer.start(int(POLL_INTERVAL*1000))

    def _poll_status(self):
        for bot_name, bot in self.bot_pool.items():
            try:
                r = requests.get(f"http://127.0.0.1:{bot['port']}/status", timeout=0.5)
                info = r.json()
                if "user_counts" in info:
                    for loop in LOOPS:
                        name = loop["name"]
                        self.user_counts[name] = info["user_counts"].get(name, 0)
            except:
                pass
        for loop in LOOPS:
            self._set_button_state(loop["name"])

    def _find_idle_bot(self):
        idle_bots = [(name, data) for name, data in self.bot_pool.items() if data["assigned"] is None]
        if not idle_bots:
            return None
        idle_bots.sort(key=lambda x: x[1]["last_used"])
        return idle_bots[0][0]

    def _update_bot_assignment(self, loop_name, new_state):
        loop_cfg = self.loop_configs[loop_name]
        old_state, old_bot = self.loop_states[loop_name]
        assigned_bot = old_bot
        post = requests.post

        if loop_cfg["can_listen"] and not loop_cfg["can_talk"]:
            if new_state > 1:
                new_state = 0

        if new_state == 0:
            if old_bot:
                port = self.bot_pool[old_bot]["port"]
                if self.delay_enabled and old_state == 2:
                    post(f"http://127.0.0.1:{port}/leave_after_delay")
                else:
                    post(f"http://127.0.0.1:{port}/leave")
                    post(f"http://127.0.0.1:{port}/mute")
                self.bot_pool[old_bot]["assigned"] = None
                self.bot_pool[old_bot]["last_used"] = time.time()
            self.loop_states[loop_name] = (0, None)
            return

        if not assigned_bot:
            assigned_bot = self._find_idle_bot()
            if not assigned_bot:
                return
            self.bot_pool[assigned_bot]["assigned"] = loop_name
        port = self.bot_pool[assigned_bot]["port"]

        if new_state == 2:
            for other_loop in LOOPS:
                other_name = other_loop["name"]
                if other_name == loop_name:
                    continue
                ostate, obot = self.loop_states[other_name]
                if ostate == 2 and obot:
                    oport = self.bot_pool[obot]["port"]
                    if self.delay_enabled:
                        post(f"http://127.0.0.1:{oport}/mute_after_delay")
                    else:
                        post(f"http://127.0.0.1:{oport}/mute")
                    self.loop_states[other_name] = (1, obot)
                    self.bot_pool[obot]["last_used"] = time.time()
                    self._set_button_state(other_name)
            post(f"http://127.0.0.1:{port}/join", json={"loop": loop_name})
            if self.delay_enabled:
                threading.Timer(self.delay_seconds, lambda: post(f"http://127.0.0.1:{port}/talk")).start()
            else:
                post(f"http://127.0.0.1:{port}/talk")
        elif new_state == 1:
            if old_state == 2 and self.delay_enabled:
                post(f"http://127.0.0.1:{port}/mute_after_delay")
            else:
                post(f"http://127.0.0.1:{port}/join", json={"loop": loop_name})
                post(f"http://127.0.0.1:{port}/mute")

        self.bot_pool[assigned_bot]["assigned"] = loop_name
        self.bot_pool[assigned_bot]["last_used"] = time.time()
        self.loop_states[loop_name] = (new_state, assigned_bot)

    def on_loop_clicked(self, loop_name):
        cfg = self.loop_configs[loop_name]
        old_state, _ = self.loop_states[loop_name]
        if not cfg["can_listen"]:
            return
        if old_state == 0:
            new_state = 1
        elif old_state == 1:
            new_state = 2 if cfg["can_talk"] else 1
        elif old_state == 2:
            new_state = 1
        else:
            new_state = 1
        self._update_bot_assignment(loop_name, new_state)
        self._set_button_state(loop_name)

    def on_loop_off_clicked(self, loop_name):
        self._update_bot_assignment(loop_name, 0)
        self._set_button_state(loop_name)

    def on_volume_changed(self, loop_name, volume):
        # Find the assigned bot for this loop
        bot_name = self.loop_states[loop_name][1]
        if bot_name:
            port = self.bot_pool[bot_name]['port']
            try:
                requests.post(f'http://127.0.0.1:{port}/set_volume', json={'volume': volume}, timeout=0.5)
            except Exception as e:
                print(f"Could not set volume for {loop_name}: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("logo2.png"))
    w   = MainWindow()
    w.show()
    sys.exit(app.exec())
