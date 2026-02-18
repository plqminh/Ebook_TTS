from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QCheckBox, QComboBox, QGroupBox, QMessageBox)
from PyQt6.QtCore import Qt
import qdarktheme

class SettingsWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("⚙️ Settings")
        header.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(header)
        
        # 1. Appearance
        grp_app = QGroupBox("Appearance")
        app_layout = QHBoxLayout()
        
        app_layout.addWidget(QLabel("Theme:"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Auto", "Dark", "Light"])
        self.combo_theme.currentTextChanged.connect(self.change_theme)
        app_layout.addWidget(self.combo_theme)
        app_layout.addStretch()
        
        grp_app.setLayout(app_layout)
        layout.addWidget(grp_app)
        
        # 2. System / TTS
        grp_sys = QGroupBox("System & TTS")
        sys_layout = QVBoxLayout()
        
        self.btn_refresh = QPushButton("🔄 Refresh Voices")
        sys_layout.addWidget(self.btn_refresh)
        
        self.chk_cuda = QCheckBox("Enable CUDA (Requires Setup)")
        # Logic to check if cuda available via torch?
        sys_layout.addWidget(self.chk_cuda)
        
        grp_sys.setLayout(sys_layout)
        layout.addWidget(grp_sys)
        
        layout.addStretch()

    def change_theme(self, text):
        qdarktheme.setup_theme(text.lower())
