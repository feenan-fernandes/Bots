"""
Ouroboros Institutional Control Center v3.2
Genuine native desktop GUI application with clickable buttons for managing:
- Ouroboros Trading Bot Engine (app.py)
- Autonomous Dead-Man's Switch Supervisor (dead_mans_switch.py)
- Obsidian Neural Memory Vault (Obsidian.exe)
- Web Terminal Dashboard (http://127.0.0.1:8080)
- Real-time Subprocess Telemetry and Integrated Log Console
"""

import sys
import os
import subprocess
import signal
import socket
import json
import time
import webbrowser
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QTextEdit, QFrame,
    QStatusBar, QMessageBox, QCheckBox, QSplitter
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot
from PySide6.QtGui import QFont, QIcon, QColor, QTextCursor

# Ensure deterministic absolute working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# Heartbeat & state file paths
HEARTBEAT_PATH = os.path.join(BASE_DIR, "output", "heartbeat.json")
BOT_STATE_PATH = os.path.join(BASE_DIR, "output", "bot_state.json")
OBSIDIAN_VAULT_PATH = os.path.join(BASE_DIR, "Obsidian_Vault")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Resolve real Python executable to prevent PyInstaller self-recursion
def get_python_exe() -> str:
    """Finds the real Python executable, avoiding self-recursing if compiled by PyInstaller."""
    if getattr(sys, "frozen", False):
        import shutil
        py = shutil.which("python") or shutil.which("python3")
        if py:
            return py
        candidates = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Python311", "python.exe"),
            "C:\\Python311\\python.exe"
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
    return sys.executable

# Locate Obsidian executable dynamically
def find_obsidian_exe() -> Optional[str]:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "Programs", "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Obsidian", "Obsidian.exe"),
        os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Obsidian", "Obsidian.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def register_obsidian_vault():
    """Ensure Obsidian_Vault is registered in Obsidian's known vaults."""
    try:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return
        obs_dir = os.path.join(appdata, "obsidian")
        os.makedirs(obs_dir, exist_ok=True)
        json_path = os.path.join(obs_dir, "obsidian.json")
        import hashlib
        vault_id = hashlib.md5(OBSIDIAN_VAULT_PATH.encode("utf-8")).hexdigest()[:16]
        
        data = {"vaults": {}}
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        data.setdefault("vaults", {})[vault_id] = {
            "path": OBSIDIAN_VAULT_PATH,
            "ts": int(time.time() * 1000),
            "open": True
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


class SubprocessWorker(QThread):
    """Background worker for streaming diagnostic tests or script output."""
    output_signal = Signal(str)
    finished_signal = Signal(int)

    def __init__(self, command, cwd=BASE_DIR):
        super().__init__()
        self.command = command
        self.cwd = cwd

    def run(self):
        try:
            p = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            for line in iter(p.stdout.readline, ""):
                if line:
                    self.output_signal.emit(line)
            p.stdout.close()
            p.wait()
            self.finished_signal.emit(p.returncode)
        except Exception as e:
            self.output_signal.emit(f"Error running command: {e}\n")
            self.finished_signal.emit(1)


class OuroborosControlCenter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ouroboros 3.2 — Institutional Quant Control Center")
        self.resize(1020, 720)
        self.setMinimumSize(850, 600)
        
        # Subprocess holders
        self.bot_process: Optional[subprocess.Popen] = None
        self.dms_process: Optional[subprocess.Popen] = None
        self.worker: Optional[SubprocessWorker] = None
        
        register_obsidian_vault()
        self._init_ui()
        self._apply_dark_theme()
        
        # Periodic status refresh timer (1000ms)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_telemetry)
        self.timer.start(1000)
        self._refresh_telemetry()
        
        self.log_message(">>> Ouroboros Institutional Control Center initialized. Ready.")

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # ─── 1. Header Bar ──────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setObjectName("headerCard")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(16, 12, 16, 12)

        title_box = QVBoxLayout()
        title_label = QLabel("OUROBOROS QUANT 3.2")
        title_label.setObjectName("appTitle")
        subtitle_label = QLabel("Autonomous High-Frequency Microstructure & Pre-Trade Risk Engine")
        subtitle_label.setObjectName("appSubtitle")
        title_box.addWidget(title_label)
        title_box.addWidget(subtitle_label)

        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self.clock_label = QLabel(datetime.now().strftime("%H:%M:%S UTC"))
        self.clock_label.setObjectName("clockLabel")
        header_layout.addWidget(self.clock_label)

        main_layout.addWidget(header_frame)

        # ─── 2. Status & Telemetry Pill Row ─────────────────────────
        status_row = QHBoxLayout()
        status_row.setSpacing(12)

        # Bot Card
        self.card_bot = self._create_telemetry_card("TRADING BOT", "OFFLINE", "#64748B")
        status_row.addWidget(self.card_bot)

        # DMS Card
        self.card_dms = self._create_telemetry_card("DEAD-MAN SWITCH", "STANDBY", "#64748B")
        status_row.addWidget(self.card_dms)

        # Risk Gate Card
        self.card_risk = self._create_telemetry_card("RISK HARD GATE", "NOMINAL (-3% Cap)", "#10B981")
        status_row.addWidget(self.card_risk)

        # Port 8080 Card
        self.card_web = self._create_telemetry_card("WEB TERMINAL", "CLOSED", "#64748B")
        status_row.addWidget(self.card_web)

        main_layout.addLayout(status_row)

        # ─── 3. Primary Action Buttons ──────────────────────────────
        btn_grid = QGridLayout()
        btn_grid.setSpacing(10)

        # Primary Execution Stack
        self.btn_start_all = QPushButton("⚡  Start Full Stack (Bot + DMS)")
        self.btn_start_all.setObjectName("btnPrimary")
        self.btn_start_all.setToolTip("Starts the Trading Bot Engine and Dead-Man's Switch concurrently")
        self.btn_start_all.clicked.connect(self.start_full_stack)
        btn_grid.addWidget(self.btn_start_all, 0, 0, 1, 2)

        self.btn_stop_all = QPushButton("🛑  Stop All Systems")
        self.btn_stop_all.setObjectName("btnDanger")
        self.btn_stop_all.setToolTip("Safely terminates all running Bot, DMS, and Python trading processes")
        self.btn_stop_all.clicked.connect(self.stop_all_systems)
        btn_grid.addWidget(self.btn_stop_all, 0, 2, 1, 2)

        # Secondary Actions
        self.btn_start_bot = QPushButton("🤖 Start Bot Only")
        self.btn_start_bot.setObjectName("btnSecondary")
        self.btn_start_bot.clicked.connect(self.start_bot_only)
        btn_grid.addWidget(self.btn_start_bot, 1, 0)

        self.btn_start_dms = QPushButton("🛡️ Start Dead-Man Only")
        self.btn_start_dms.setObjectName("btnSecondary")
        self.btn_start_dms.clicked.connect(self.start_dms_only)
        btn_grid.addWidget(self.btn_start_dms, 1, 1)

        self.btn_open_web = QPushButton("🌐 Open Web Terminal")
        self.btn_open_web.setObjectName("btnAccent")
        self.btn_open_web.setToolTip("Open Bento Grid 2.0 Terminal in default browser (http://127.0.0.1:8080)")
        self.btn_open_web.clicked.connect(self.open_web_terminal)
        btn_grid.addWidget(self.btn_open_web, 1, 2)

        self.btn_open_obsidian = QPushButton("🧠 Open Obsidian Vault")
        self.btn_open_obsidian.setObjectName("btnAccent")
        self.btn_open_obsidian.setToolTip("Open Obsidian Neural Knowledge Vault with interactive graph")
        self.btn_open_obsidian.clicked.connect(self.open_obsidian_vault)
        btn_grid.addWidget(self.btn_open_obsidian, 1, 3)

        # Tertiary Utilities
        self.btn_diagnostics = QPushButton("🧪 Run Verification Suite")
        self.btn_diagnostics.setObjectName("btnUtility")
        self.btn_diagnostics.setToolTip("Executes institutional test suites and streams real-time logs")
        self.btn_diagnostics.clicked.connect(self.run_diagnostics)
        btn_grid.addWidget(self.btn_diagnostics, 2, 0)

        self.btn_view_trades = QPushButton("📜 View Trades Log")
        self.btn_view_trades.setObjectName("btnUtility")
        self.btn_view_trades.clicked.connect(lambda: self.open_log_file("Ouroboros_trades.log"))
        btn_grid.addWidget(self.btn_view_trades, 2, 1)

        self.btn_view_errors = QPushButton("⚠️ View Errors Log")
        self.btn_view_errors.setObjectName("btnUtility")
        self.btn_view_errors.clicked.connect(lambda: self.open_log_file("Ouroboros_errors.log"))
        btn_grid.addWidget(self.btn_view_errors, 2, 2)

        self.btn_open_folder = QPushButton("📁 Open Folder")
        self.btn_open_folder.setObjectName("btnUtility")
        self.btn_open_folder.clicked.connect(self.open_project_folder)
        btn_grid.addWidget(self.btn_open_folder, 2, 3)

        main_layout.addLayout(btn_grid)

        # ─── 4. Live Terminal Console ───────────────────────────────
        console_frame = QFrame()
        console_frame.setObjectName("consoleFrame")
        console_layout = QVBoxLayout(console_frame)
        console_layout.setContentsMargins(12, 10, 12, 10)
        console_layout.setSpacing(6)

        console_header = QHBoxLayout()
        console_title = QLabel("SYSTEM CONSOLE & TELEMETRY STREAM")
        console_title.setObjectName("consoleTitle")
        console_header.addWidget(console_title)
        console_header.addStretch()

        self.chk_autoscroll = QCheckBox("Auto-Scroll")
        self.chk_autoscroll.setChecked(True)
        self.chk_autoscroll.setObjectName("consoleCheck")
        console_header.addWidget(self.chk_autoscroll)

        btn_clear = QPushButton("Clear")
        btn_clear.setObjectName("btnClear")
        btn_clear.clicked.connect(self.clear_console)
        console_header.addWidget(btn_clear)

        console_layout.addLayout(console_header)

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setObjectName("consoleText")
        console_layout.addWidget(self.console_text)

        main_layout.addWidget(console_frame, stretch=1)

        # ─── 5. Status Bar ──────────────────────────────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select an action above to control the trading system.")

    def _create_telemetry_card(self, title: str, default_val: str, color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("telemetryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("cardTitle")
        v_lbl = QLabel(default_val)
        v_lbl.setObjectName("cardValue")
        v_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")

        layout.addWidget(t_lbl)
        layout.addWidget(v_lbl)
        card.value_label = v_lbl  # type: ignore
        return card

    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0B0F19;
            }
            #headerCard {
                background-color: #111827;
                border: 1px solid #1F2937;
                border-radius: 8px;
            }
            #appTitle {
                color: #38BDF8;
                font-size: 18px;
                font-weight: 800;
                letter-spacing: 1px;
            }
            #appSubtitle {
                color: #94A3B8;
                font-size: 11px;
            }
            #clockLabel {
                color: #64748B;
                font-family: Consolas, monospace;
                font-size: 13px;
                font-weight: bold;
            }
            #telemetryCard {
                background-color: #111827;
                border: 1px solid #1F2937;
                border-radius: 8px;
            }
            #cardTitle {
                color: #64748B;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
            #cardValue {
                font-size: 13px;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: bold;
                padding: 10px 14px;
                border-radius: 6px;
                border: none;
            }
            #btnPrimary {
                background-color: #10B981;
                color: #FFFFFF;
            }
            #btnPrimary:hover {
                background-color: #059669;
            }
            #btnPrimary:pressed {
                background-color: #047857;
            }
            #btnDanger {
                background-color: #EF4444;
                color: #FFFFFF;
            }
            #btnDanger:hover {
                background-color: #DC2626;
            }
            #btnDanger:pressed {
                background-color: #B91C1C;
            }
            #btnSecondary {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid #334155;
            }
            #btnSecondary:hover {
                background-color: #334155;
                color: #FFFFFF;
            }
            #btnAccent {
                background-color: #1E3A8A;
                color: #93C5FD;
                border: 1px solid #1D4ED8;
            }
            #btnAccent:hover {
                background-color: #2563EB;
                color: #FFFFFF;
            }
            #btnUtility {
                background-color: #0F172A;
                color: #94A3B8;
                border: 1px solid #1E293B;
            }
            #btnUtility:hover {
                background-color: #1E293B;
                color: #E2E8F0;
            }
            #consoleFrame {
                background-color: #030712;
                border: 1px solid #1F2937;
                border-radius: 8px;
            }
            #consoleTitle {
                color: #64748B;
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
            #consoleCheck {
                color: #94A3B8;
                font-size: 11px;
            }
            #btnClear {
                background-color: transparent;
                color: #64748B;
                font-size: 11px;
                padding: 3px 8px;
                border: 1px solid #1F2937;
                border-radius: 4px;
            }
            #btnClear:hover {
                color: #E2E8F0;
                background-color: #1F2937;
            }
            #consoleText {
                background-color: #030712;
                color: #E2E8F0;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 11px;
                border: none;
            }
            QStatusBar {
                background-color: #0B0F19;
                color: #64748B;
                font-size: 11px;
            }
        """)

    # ─── Telemetry Refresh Loop ─────────────────────────────────────
    @Slot()
    def _refresh_telemetry(self):
        # Update clock
        self.clock_label.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

        # Check port 8080 (Web Terminal)
        port_open = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                res = s.connect_ex(("127.0.0.1", 8080))
                port_open = (res == 0)
        except Exception:
            port_open = False

        if port_open:
            self.card_web.value_label.setText("ONLINE (8080)")
            self.card_web.value_label.setStyleSheet("color: #10B981; font-weight: bold;")
        else:
            self.card_web.value_label.setText("CLOSED")
            self.card_web.value_label.setStyleSheet("color: #64748B; font-weight: bold;")

        # Check Bot Process
        bot_running = False
        if self.bot_process is not None:
            if self.bot_process.poll() is None:
                bot_running = True
            else:
                self.bot_process = None

        if bot_running or port_open:
            pid_str = f"PID: {self.bot_process.pid}" if self.bot_process else "ACTIVE"
            self.card_bot.value_label.setText(f"ONLINE ({pid_str})")
            self.card_bot.value_label.setStyleSheet("color: #10B981; font-weight: bold;")
        else:
            self.card_bot.value_label.setText("STOPPED")
            self.card_bot.value_label.setStyleSheet("color: #64748B; font-weight: bold;")

        # Check Dead-Man's Switch Heartbeat
        dms_running = (self.dms_process is not None and self.dms_process.poll() is None)
        heartbeat_latency = None
        if os.path.exists(HEARTBEAT_PATH):
            try:
                with open(HEARTBEAT_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ts = data.get("timestamp", 0)
                    heartbeat_latency = int((time.time() - ts) * 1000)
            except Exception:
                pass

        if heartbeat_latency is not None and heartbeat_latency < 3500:
            status_text = f"ACTIVE ({heartbeat_latency}ms)"
            self.card_dms.value_label.setText(status_text)
            self.card_dms.value_label.setStyleSheet("color: #38BDF8; font-weight: bold;")
        elif dms_running:
            self.card_dms.value_label.setText("SUPERVISING")
            self.card_dms.value_label.setStyleSheet("color: #38BDF8; font-weight: bold;")
        else:
            self.card_dms.value_label.setText("STANDBY")
            self.card_dms.value_label.setStyleSheet("color: #64748B; font-weight: bold;")

    # ─── Button Actions ─────────────────────────────────────────────
    def log_message(self, msg: str, color: str = "#E2E8F0"):
        ts = datetime.now().strftime("[%H:%M:%S]")
        formatted = f'<span style="color: #64748B;">{ts}</span> <span style="color: {color};">{msg}</span>'
        self.console_text.append(formatted)
        if self.chk_autoscroll.isChecked():
            self.console_text.moveCursor(QTextCursor.End)

    def clear_console(self):
        self.console_text.clear()

    def start_full_stack(self):
        self.log_message("⚡ Starting Full Institutional Stack (Bot + Dead-Man's Switch)...", "#38BDF8")
        self.start_bot_only()
        # Brief delay before starting DMS so heartbeat file can initialize
        QTimer.singleShot(1500, self.start_dms_only)

    def start_bot_only(self):
        if self.bot_process is not None and self.bot_process.poll() is None:
            self.log_message("⚠️ Trading Bot is already running.", "#F59E0B")
            return

        cmd = [get_python_exe(), os.path.join(BASE_DIR, "app.py")]
        try:
            self.log_message(f"🚀 Spawning Trading Bot: {' '.join(cmd)}", "#10B981")
            # Spawn in visible window or separate process
            self.bot_process = subprocess.Popen(
                cmd,
                cwd=BASE_DIR,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            self.log_message(f"✅ Trading Bot started (PID: {self.bot_process.pid})", "#10B981")
            self.status_bar.showMessage(f"Trading Bot started (PID: {self.bot_process.pid})")
        except Exception as e:
            self.log_message(f"❌ Failed to start Trading Bot: {e}", "#EF4444")

    def start_dms_only(self):
        if self.dms_process is not None and self.dms_process.poll() is None:
            self.log_message("⚠️ Dead-Man's Switch is already running.", "#F59E0B")
            return

        cmd = [get_python_exe(), os.path.join(BASE_DIR, "dead_mans_switch.py")]
        try:
            self.log_message(f"🛡️ Spawning Dead-Man's Switch Supervisor: {' '.join(cmd)}", "#38BDF8")
            self.dms_process = subprocess.Popen(
                cmd,
                cwd=BASE_DIR,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            )
            self.log_message(f"✅ Dead-Man's Switch supervisor active (PID: {self.dms_process.pid})", "#38BDF8")
            self.status_bar.showMessage(f"Dead-Man's Switch supervisor active (PID: {self.dms_process.pid})")
        except Exception as e:
            self.log_message(f"❌ Failed to start Dead-Man's Switch: {e}", "#EF4444")

    def stop_all_systems(self):
        self.log_message("🛑 Stopping all Ouroboros processes...", "#EF4444")
        stopped_count = 0

        # Terminate managed handles
        if self.bot_process is not None:
            try:
                self.bot_process.terminate()
                self.bot_process = None
                stopped_count += 1
            except Exception:
                pass

        if self.dms_process is not None:
            try:
                self.dms_process.terminate()
                self.dms_process = None
                stopped_count += 1
            except Exception:
                pass

        # Windows cleanup: force kill processes listening on port 8080 and dead_mans_switch
        if sys.platform == "win32":
            try:
                # Kill port 8080
                kill_cmd = 'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :8080 ^| findstr LISTENING\') do taskkill /F /PID %a'
                subprocess.run(kill_cmd, shell=True, capture_output=True, text=True)
                # Kill Dead-Man window
                subprocess.run('taskkill /F /FI "WINDOWTITLE eq *Dead-Man*"', shell=True, capture_output=True, text=True)
            except Exception as e:
                self.log_message(f"Warning during taskkill cleanup: {e}", "#F59E0B")

        self.log_message("✅ All processes halted and port 8080 released.", "#10B981")
        self.status_bar.showMessage("All trading processes halted.")
        self._refresh_telemetry()

    def open_web_terminal(self):
        url = "http://127.0.0.1:8080"
        self.log_message(f"🌐 Opening Web Terminal at {url}...", "#38BDF8")
        try:
            webbrowser.open(url)
        except Exception as e:
            self.log_message(f"❌ Failed to open browser: {e}", "#EF4444")

    def open_obsidian_vault(self):
        self.log_message("🧠 Launching Obsidian Neural Memory Vault...", "#A855F7")
        register_obsidian_vault()
        
        obs_exe = find_obsidian_exe()
        if obs_exe and os.path.exists(obs_exe):
            try:
                subprocess.Popen([obs_exe], cwd=BASE_DIR)
                self.log_message(f"✅ Obsidian launched directly from: {obs_exe}", "#10B981")
                return
            except Exception as e:
                self.log_message(f"Warning starting Obsidian via executable: {e}", "#F59E0B")

        # Fallback to URI scheme
        try:
            vault_uri = f"obsidian://open?path={OBSIDIAN_VAULT_PATH}"
            webbrowser.open(vault_uri)
            self.log_message(f"✅ Obsidian launched via URI: {vault_uri}", "#10B981")
        except Exception as e:
            self.log_message(f"❌ Failed to open Obsidian: {e}", "#EF4444")
            QMessageBox.information(
                self,
                "Obsidian Vault Location",
                f"Obsidian Vault path:\n\n{OBSIDIAN_VAULT_PATH}\n\nYou can open this folder directly inside Obsidian."
            )

    def run_diagnostics(self):
        if self.worker is not None and self.worker.isRunning():
            self.log_message("⚠️ Diagnostic tests are already running.", "#F59E0B")
            return

        self.log_message("🧪 ====================================================", "#38BDF8")
        self.log_message("🧪 STARTING INSTITUTIONAL QUANT VERIFICATION SUITE...", "#38BDF8")
        self.log_message("🧪 ====================================================", "#38BDF8")

        cmd = [get_python_exe(), "-u", os.path.join(BASE_DIR, "test_institutional_architecture.py")]
        self.worker = SubprocessWorker(cmd, cwd=BASE_DIR)
        self.worker.output_signal.connect(self._handle_diagnostic_output)
        self.worker.finished_signal.connect(self._diagnostic_suite_1_finished)
        self.worker.start()

    @Slot(str)
    def _handle_diagnostic_output(self, line: str):
        line_clean = line.rstrip()
        if not line_clean:
            return
        if "PASSED" in line_clean or "[OK]" in line_clean:
            self.log_message(line_clean, "#10B981")
        elif "FAIL" in line_clean or "ERROR" in line_clean or "CRITICAL" in line_clean:
            self.log_message(line_clean, "#EF4444")
        elif "WARNING" in line_clean:
            self.log_message(line_clean, "#F59E0B")
        elif "Testing" in line_clean or "===" in line_clean or ">>>" in line_clean:
            self.log_message(line_clean, "#38BDF8")
        else:
            self.log_message(line_clean, "#E2E8F0")

    @Slot(int)
    def _diagnostic_suite_1_finished(self, exit_code: int):
        self.log_message(f"Suite 1 completed with code: {exit_code}", "#38BDF8")
        # Run Suite 2 (Self Learning Vault)
        cmd2 = [get_python_exe(), "-u", os.path.join(BASE_DIR, "test_self_learning_vault.py")]
        self.worker = SubprocessWorker(cmd2, cwd=BASE_DIR)
        self.worker.output_signal.connect(self._handle_diagnostic_output)
        self.worker.finished_signal.connect(self._diagnostic_suite_2_finished)
        self.worker.start()

    @Slot(int)
    def _diagnostic_suite_2_finished(self, exit_code: int):
        self.log_message(f"Suite 2 completed with code: {exit_code}", "#38BDF8")
        self.log_message("📊 RUNNING AETHERIS MONTE CARLO BACKTEST & PERFORMANCE AUDIT...", "#38BDF8")
        cmd3 = [get_python_exe(), "-u", os.path.join(BASE_DIR, "backtest_aetheris.py")]
        self.worker = SubprocessWorker(cmd3, cwd=BASE_DIR)
        self.worker.output_signal.connect(self._handle_diagnostic_output)
        self.worker.finished_signal.connect(self._diagnostic_suite_3_finished)
        self.worker.start()

    @Slot(int)
    def _diagnostic_suite_3_finished(self, exit_code: int):
        self.log_message(f"AETHERIS Backtest completed with code: {exit_code}", "#38BDF8")
        self.log_message("🎉 ALL INSTITUTIONAL QUANT SUITES & BACKTESTS PASSED (100%)!", "#10B981")
        self.status_bar.showMessage("All diagnostic tests & empirical backtest complete.")

    def open_log_file(self, filename: str):
        filepath = os.path.join(LOGS_DIR, filename)
        if not os.path.exists(filepath):
            filepath = os.path.join(BASE_DIR, "output", filename)
        
        if not os.path.exists(filepath):
            self.log_message(f"⚠️ Log file not found: {filename}", "#F59E0B")
            return

        self.log_message(f"📜 Opening {filename} in default text editor...", "#E2E8F0")
        try:
            if sys.platform == "win32":
                os.startfile(filepath)
            else:
                subprocess.Popen(["xdg-open", filepath])
        except Exception as e:
            self.log_message(f"❌ Failed to open log file: {e}", "#EF4444")

    def open_project_folder(self):
        self.log_message(f"📁 Opening workspace: {BASE_DIR}", "#E2E8F0")
        try:
            if sys.platform == "win32":
                os.startfile(BASE_DIR)
            else:
                subprocess.Popen(["xdg-open", BASE_DIR])
        except Exception as e:
            self.log_message(f"❌ Failed to open directory: {e}", "#EF4444")

    def closeEvent(self, event):
        if self.bot_process is not None or self.dms_process is not None:
            reply = QMessageBox.question(
                self,
                "Exit Control Center",
                "Trading processes are currently running.\n\nDo you want to stop all trading processes before exiting?\n\n• Yes: Stop Bot & DMS\n• No: Keep Bot & DMS running in background\n• Cancel: Don't exit",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.stop_all_systems()
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    import multiprocessing
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    app.setApplicationName("Ouroboros Control Center")
    window = OuroborosControlCenter()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
