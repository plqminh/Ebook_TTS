from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLineEdit, QPushButton, QLabel, QCheckBox, QComboBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QFileDialog, QProgressBar, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal

class BatchWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 1. Header
        header = QLabel("⚡ Batch MP3 Converter")
        header.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(header)
        
        # 2. Configuration Form
        form_layout = QFormLayout()
        
        # Engine Selection
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["Edge TTS", "Google TTS", "VieNeu-TTS"])
        self.combo_engine.currentTextChanged.connect(self.on_engine_changed)
        
        engine_row = QHBoxLayout()
        engine_row.addWidget(self.combo_engine)
        form_layout.addRow("TTS Engine:", engine_row)

        # Model (Visible only for VieNeu)
        self.edit_model = QLineEdit()
        self.btn_browse_model = QPushButton("Browse")
        self.btn_browse_model.clicked.connect(self.browse_model)
        
        self.model_container = QWidget()
        model_layout = QHBoxLayout(self.model_container)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.edit_model)
        model_layout.addWidget(self.btn_browse_model)
        
        self.lbl_model = QLabel("Model (.pt/.onnx/config):")
        form_layout.addRow(self.lbl_model, self.model_container)
        
        # Ref Audio (Visible only for VieNeu, maybe cloning later?)
        self.combo_ref = QComboBox()
        self.combo_ref.currentIndexChanged.connect(self.on_ref_changed)
        
        self.btn_refresh_ref = QPushButton("🔄")
        self.btn_refresh_ref.setFixedWidth(30)
        
        self.ref_container = QWidget()
        ref_layout = QHBoxLayout(self.ref_container)
        ref_layout.setContentsMargins(0, 0, 0, 0)
        ref_layout.addWidget(self.combo_ref, 1)
        ref_layout.addWidget(self.btn_refresh_ref)
        
        self.lbl_ref = QLabel("Ref Audio (Voice):")
        form_layout.addRow(self.lbl_ref, self.ref_container)

        # Voice Selection (For Edge/Google)
        self.combo_voice = QComboBox()
        self.lbl_voice = QLabel("Voice:")
        form_layout.addRow(self.lbl_voice, self.combo_voice)

        # Merge Option
        self.chk_merge = QCheckBox("Merge all chapters into ONE MP3")
        form_layout.addRow("", self.chk_merge)
        
        main_layout.addLayout(form_layout)
        
        # 3. Chapter List Table
        main_layout.addWidget(QLabel("Chapters to Convert:"))
        
        self.table_chapters = QTableWidget()
        self.table_chapters.setColumnCount(2)
        self.table_chapters.setHorizontalHeaderLabels(["Select", "Chapter Title"])
        self.table_chapters.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_chapters.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        main_layout.addWidget(self.table_chapters)
        
        # Selection Buttons
        sel_btn_layout = QHBoxLayout()
        self.btn_sel_all = QPushButton("Select All")
        self.btn_sel_none = QPushButton("Select None")
        
        self.btn_sel_all.clicked.connect(self.select_all)
        self.btn_sel_none.clicked.connect(self.select_none)
        
        sel_btn_layout.addWidget(self.btn_sel_all)
        sel_btn_layout.addWidget(self.btn_sel_none)
        sel_btn_layout.addStretch()
        main_layout.addLayout(sel_btn_layout)
        
        # 4. Action Area
        action_layout = QHBoxLayout()
        
        self.btn_start = QPushButton("Start Batch Conversion")
        self.btn_start.setStyleSheet("background-color: #28a745; color: white; padding: 10px; font-weight: bold;")
        self.btn_start.setFixedHeight(50)
        
        self.btn_setup = QPushButton("Auto-Setup Resources")
        self.btn_setup.setStyleSheet("background-color: #1f6aa5; padding: 10px;")
        self.btn_setup.setFixedHeight(50)
        
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setStyleSheet("background-color: #d9534f; color: white; padding: 10px; font-weight: bold;")
        self.btn_stop.setFixedHeight(50)
        self.btn_stop.setEnabled(False) # Default disabled
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_stop)
        action_layout.addWidget(self.btn_setup)
        
        main_layout.addLayout(action_layout)
        
        # 5. Progress
        self.progress_bar = QProgressBar()
        self.lbl_status = QLabel("Ready")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.lbl_status)
        
        # 6. Log/Content Area
        from PyQt6.QtWidgets import QTextEdit
        self.log_area = QTextEdit()
        self.log_area.setPlaceholderText("Processing logs will appear here...")
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #21252b; color: #abb2bf; font-family: Consolas;")
        main_layout.addWidget(self.log_area)

        # Trigger initial state
        self.on_engine_changed(self.combo_engine.currentText())

    def browse_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Model", "", "Model/Config (*.pt *.onnx *.json *.yaml *.gguf)")
        if path: self.edit_model.setText(path)

    def on_ref_changed(self, index):
        if self.combo_ref.currentText() == "Browse...":
            path, _ = QFileDialog.getOpenFileName(self, "Select Reference Audio", "", "Audio (*.wav *.mp3)")
            if path:
                # Add to combo and select
                self.combo_ref.insertItem(0, path, path) # Display path as name
                self.combo_ref.setCurrentIndex(0)
            else:
                 # Revert to valid
                 if self.combo_ref.count() > 1: self.combo_ref.setCurrentIndex(0)

    def select_all(self):
        for row in range(self.table_chapters.rowCount()):
            item = self.table_chapters.item(row, 0)
            item.setCheckState(Qt.CheckState.Checked)

    def select_none(self):
        for row in range(self.table_chapters.rowCount()):
            item = self.table_chapters.item(row, 0)
            item.setCheckState(Qt.CheckState.Unchecked)

    def populate_chapters(self, chapters):
        self.table_chapters.setRowCount(len(chapters))
        for i, title in enumerate(chapters):
            # Checkbox Item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            
            self.table_chapters.setItem(i, 0, chk_item)
            self.table_chapters.setItem(i, 1, QTableWidgetItem(title))

    def on_engine_changed(self, engine_name):
        is_vieneu = "VieNeu" in engine_name
        
        # Toggle Visibility
        self.lbl_model.setVisible(is_vieneu)
        self.model_container.setVisible(is_vieneu)
        self.lbl_ref.setVisible(is_vieneu)
        self.ref_container.setVisible(is_vieneu)
        
        # Voice combo is always visible
        self.lbl_voice.setVisible(True)
        self.combo_voice.setVisible(True)
        
        # Populate Voices
        self.populate_voices()

    def populate_voices(self):
        self.combo_voice.clear()
        engine_map = {
            "Edge TTS": "edge",
            "Google TTS": "google",
            "VieNeu-TTS": "vieneu"
        }
        current_engine = self.combo_engine.currentText()
        engine_key = engine_map.get(current_engine, "edge")
        
        # Import here to avoid circular logic during layout init if possible
        # Or simpler:
        try:
            from app.services.tts_service import TTSService
            voices = TTSService.get_voices(engine_key)
            for v in voices:
                self.combo_voice.addItem(v["name"], v["id"])
        except ImportError:
            self.combo_voice.addItem("Error loading voices")

