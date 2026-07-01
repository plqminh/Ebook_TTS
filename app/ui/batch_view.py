from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLineEdit, QPushButton, QLabel, QCheckBox, QComboBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QFileDialog, QProgressBar, QMessageBox,
                             QSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal
from pathlib import Path

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
        self.combo_engine.addItems(["Edge TTS", "Google TTS", "OmniVoice"])
        self.combo_engine.currentTextChanged.connect(self.on_engine_changed)
        
        engine_row = QHBoxLayout()
        engine_row.addWidget(self.combo_engine)
        form_layout.addRow("TTS Engine:", engine_row)

        self.edit_model = QLineEdit() # Kept for compatibility, not added to layout
        self.edit_model.setText("OmniVoice (auto)")
        
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

        # Output Directory
        self.edit_output_dir = QLineEdit()
        self.edit_output_dir.setText(str(Path("batch_output").resolve()))
        self.edit_output_dir.setReadOnly(True)
        self.btn_browse_output = QPushButton("📁")
        self.btn_browse_output.setFixedWidth(30)
        self.btn_browse_output.clicked.connect(self._browse_output_dir)

        out_container = QWidget()
        out_layout = QHBoxLayout(out_container)
        out_layout.setContentsMargins(0, 0, 0, 0)
        out_layout.addWidget(self.edit_output_dir, 1)
        out_layout.addWidget(self.btn_browse_output)
        form_layout.addRow("Output Folder:", out_container)
        
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
        
        # Fast Range Selection
        self.spin_from = QSpinBox()
        self.spin_from.setMinimum(1)
        self.spin_to = QSpinBox()
        self.spin_to.setMinimum(1)
        self.btn_sel_range = QPushButton("Select Range")
        self.btn_sel_range.clicked.connect(self.select_range)
        
        sel_btn_layout.addWidget(self.btn_sel_all)
        sel_btn_layout.addWidget(self.btn_sel_none)
        
        sel_btn_layout.addSpacing(20)
        sel_btn_layout.addWidget(QLabel("From:"))
        sel_btn_layout.addWidget(self.spin_from)
        sel_btn_layout.addWidget(QLabel("To:"))
        sel_btn_layout.addWidget(self.spin_to)
        sel_btn_layout.addWidget(self.btn_sel_range)
        
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
        self.btn_setup.setVisible(False)  # Hidden as OmniVoice handles its own setup
        self.btn_setup.setFixedHeight(50)
        
        self.btn_pause = QPushButton("⏸ PAUSE")
        self.btn_pause.setStyleSheet("background-color: #f0ad4e; color: white; padding: 10px; font-weight: bold;")
        self.btn_pause.setFixedHeight(50)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause)

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setStyleSheet("background-color: #d9534f; color: white; padding: 10px; font-weight: bold;")
        self.btn_stop.setFixedHeight(50)
        self.btn_stop.setEnabled(False) # Default disabled
        
        action_layout.addWidget(self.btn_start)
        action_layout.addWidget(self.btn_pause)
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

    def select_range(self):
        start_idx = self.spin_from.value() - 1
        end_idx = self.spin_to.value() - 1
        
        for row in range(self.table_chapters.rowCount()):
            item = self.table_chapters.item(row, 0)
            if start_idx <= row <= end_idx:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

    def populate_chapters(self, chapters):
        total = len(chapters)
        self.table_chapters.setRowCount(total)
        
        if total > 0:
            self.spin_from.setMaximum(total)
            self.spin_to.setMaximum(total)
            self.spin_from.setValue(1)
            self.spin_to.setValue(total)
        else:
            self.spin_from.setMaximum(1)
            self.spin_to.setMaximum(1)
            
        for i, title in enumerate(chapters):
            # Checkbox Item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Checked)
            
            self.table_chapters.setItem(i, 0, chk_item)
            self.table_chapters.setItem(i, 1, QTableWidgetItem(title))

    def on_engine_changed(self, engine_name):
        is_omnivoice = "OmniVoice" in engine_name
        is_local = is_omnivoice
        
        # Toggle Visibility
        self.lbl_ref.setVisible(is_local)
        self.ref_container.setVisible(is_local)
        
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
            "OmniVoice": "omnivoice",
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

    def _browse_output_dir(self):
        """Open a directory picker for batch output."""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder",
                                                   self.edit_output_dir.text())
        if folder:
            self.edit_output_dir.setText(folder)

    def get_output_dir(self):
        """Return the user-selected output directory path."""
        return self.edit_output_dir.text()

    def _toggle_pause(self):
        """Toggle the pause button text between Pause and Resume."""
        if self.btn_pause.text() == "⏸ PAUSE":
            self.btn_pause.setText("▶ RESUME")
            self.btn_pause.setStyleSheet(
                "background-color: #5cb85c; color: white; padding: 10px; font-weight: bold;"
            )
        else:
            self.btn_pause.setText("⏸ PAUSE")
            self.btn_pause.setStyleSheet(
                "background-color: #f0ad4e; color: white; padding: 10px; font-weight: bold;"
            )
