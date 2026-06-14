from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QCheckBox, QComboBox, QGroupBox, QSpinBox,
                             QDoubleSpinBox, QFormLayout, QSlider, QLineEdit,
                             QFileDialog, QListWidget, QMessageBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal
import qdarktheme

class SettingsWidget(QWidget):
    # Signals to notify app when settings change
    settings_changed = pyqtSignal()
    voice_cloned = pyqtSignal(str, str, str)   # (name, audio_path, ref_text)
    voice_removed = pyqtSignal(str)            # (name)
    transcribe_requested = pyqtSignal(str, str)  # (audio_path, model_size)

    def __init__(self):
        super().__init__()

        # Scroll area so the page doesn't clip on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(20, 20, 20, 20)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Header
        header = QLabel("⚙️ Settings")
        header.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(header)
        
        # ── 1. Appearance ──────────────────────────────────────────────
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
        
        # ── 2. Reading Settings ────────────────────────────────────────
        grp_read = QGroupBox("Reading")
        read_layout = QFormLayout()

        # Font Size
        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(8, 36)
        self.spin_font_size.setValue(14)
        self.spin_font_size.setSuffix(" pt")
        read_layout.addRow("Reader Font Size:", self.spin_font_size)

        # Auto-scroll to highlighted sentence
        self.chk_auto_scroll = QCheckBox("Auto-scroll to current sentence")
        self.chk_auto_scroll.setChecked(True)
        read_layout.addRow("", self.chk_auto_scroll)

        # Max retries for reader TTS generation
        self.spin_read_retries = QSpinBox()
        self.spin_read_retries.setRange(1, 10)
        self.spin_read_retries.setValue(3)
        read_layout.addRow("Max Retries (per sentence):", self.spin_read_retries)

        grp_read.setLayout(read_layout)
        layout.addWidget(grp_read)

        # ── 3. Batch Processing Settings ───────────────────────────────
        grp_batch = QGroupBox("Batch Processing")
        batch_layout = QFormLayout()

        # Silence gap between chunks (seconds)
        self.spin_silence_gap = QDoubleSpinBox()
        self.spin_silence_gap.setRange(0.0, 3.0)
        self.spin_silence_gap.setValue(0.3)
        self.spin_silence_gap.setSingleStep(0.1)
        self.spin_silence_gap.setSuffix(" s")
        batch_layout.addRow("Silence Between Chunks:", self.spin_silence_gap)

        # Max retries for batch cloud TTS
        self.spin_batch_retries = QSpinBox()
        self.spin_batch_retries.setRange(1, 10)
        self.spin_batch_retries.setValue(3)
        batch_layout.addRow("Max Retries (cloud TTS):", self.spin_batch_retries)

        # Concurrent chunks
        self.spin_concurrent_chunks = QSpinBox()
        self.spin_concurrent_chunks.setRange(1, 10)
        self.spin_concurrent_chunks.setValue(3)
        batch_layout.addRow("Concurrent Chunks:", self.spin_concurrent_chunks)

        # Output format
        self.combo_output_fmt = QComboBox()
        self.combo_output_fmt.addItems(["MP3 (.mp3)", "WAV (.wav)"])
        batch_layout.addRow("Output Format:", self.combo_output_fmt)

        grp_batch.setLayout(batch_layout)
        layout.addWidget(grp_batch)

        # ── 4. Voice Cloning ──────────────────────────────────────────
        grp_clone = QGroupBox("Voice Cloning (OmniVoice)")
        clone_layout = QVBoxLayout()

        form = QFormLayout()

        self.edit_clone_name = QLineEdit()
        self.edit_clone_name.setPlaceholderText("e.g. My Custom Voice")
        form.addRow("Voice Name:", self.edit_clone_name)

        file_row = QHBoxLayout()
        self.edit_clone_file = QLineEdit()
        self.edit_clone_file.setReadOnly(True)
        self.edit_clone_file.setPlaceholderText("Select a .wav or .mp3 file…")
        self.btn_browse_clone = QPushButton("Browse…")
        self.btn_browse_clone.setFixedWidth(90)
        self.btn_browse_clone.clicked.connect(self._browse_clone_audio)
        file_row.addWidget(self.edit_clone_file)
        file_row.addWidget(self.btn_browse_clone)
        form.addRow("Audio File:", file_row)

        ref_row = QHBoxLayout()
        self.edit_clone_ref_text = QLineEdit()
        self.edit_clone_ref_text.setPlaceholderText("(required) transcript — or use Auto-Transcribe →")
        ref_row.addWidget(self.edit_clone_ref_text)

        self.combo_whisper_model = QComboBox()
        self.combo_whisper_model.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.combo_whisper_model.setCurrentIndex(1)  # default: base
        self.combo_whisper_model.setFixedWidth(100)
        self.combo_whisper_model.setToolTip(
            "Whisper model size\n"
            "tiny (~39 MB) — fastest, least accurate\n"
            "base (~74 MB) — good balance\n"
            "small (~244 MB) — better accuracy\n"
            "medium (~769 MB) — high accuracy\n"
            "large-v3 (~1.5 GB) — best accuracy"
        )
        ref_row.addWidget(self.combo_whisper_model)

        self.btn_transcribe = QPushButton("🎤 Auto-Transcribe")
        self.btn_transcribe.setFixedWidth(140)
        self.btn_transcribe.clicked.connect(self._on_transcribe)
        self.btn_transcribe.setToolTip("Use Whisper to auto-transcribe the selected audio file")
        ref_row.addWidget(self.btn_transcribe)

        form.addRow("Reference Text:", ref_row)

        clone_layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.btn_add_voice = QPushButton("➕ Add Voice")
        self.btn_add_voice.clicked.connect(self._on_add_voice)
        btn_row.addWidget(self.btn_add_voice)
        btn_row.addStretch()
        clone_layout.addLayout(btn_row)

        # Status label (shown during encoding)
        self.lbl_clone_status = QLabel("")
        self.lbl_clone_status.setStyleSheet("color: #888; font-style: italic;")
        clone_layout.addWidget(self.lbl_clone_status)

        # Existing cloned voices list
        clone_layout.addWidget(QLabel("Cloned Voices:"))
        self.list_cloned = QListWidget()
        self.list_cloned.setMaximumHeight(120)
        clone_layout.addWidget(self.list_cloned)

        rm_row = QHBoxLayout()
        self.btn_remove_voice = QPushButton("🗑 Remove Selected")
        self.btn_remove_voice.clicked.connect(self._on_remove_voice)
        rm_row.addWidget(self.btn_remove_voice)
        rm_row.addStretch()
        clone_layout.addLayout(rm_row)

        grp_clone.setLayout(clone_layout)
        layout.addWidget(grp_clone)

        # ── 4b. OmniVoice Voice Design ────────────────────────────────
        grp_omni = QGroupBox("Voice Design (OmniVoice)")
        omni_layout = QVBoxLayout()

        omni_form = QFormLayout()
        self.edit_voice_design = QLineEdit()
        self.edit_voice_design.setPlaceholderText(
            "e.g. A young female speaker with a warm tone and slight British accent"
        )
        omni_form.addRow("Voice Description:", self.edit_voice_design)
        omni_layout.addLayout(omni_form)

        omni_note = QLabel(
            "💡 Used when OmniVoice engine + \"Voice Design\" voice is selected.\n"
            "Describe gender, age, pitch, accent, speaking style, etc."
        )
        omni_note.setStyleSheet("color: #888; font-style: italic; font-size: 11px;")
        omni_note.setWordWrap(True)
        omni_layout.addWidget(omni_note)

        grp_omni.setLayout(omni_layout)
        layout.addWidget(grp_omni)

        # ── 5. System ─────────────────────────────────────────────────
        grp_sys = QGroupBox("System")
        sys_layout = QVBoxLayout()
        
        self.btn_refresh = QPushButton("🔄 Refresh Voices")
        sys_layout.addWidget(self.btn_refresh)
        
        grp_sys.setLayout(sys_layout)
        layout.addWidget(grp_sys)
        
        layout.addStretch()

    # ── Voice Cloning Helpers ──────────────────────────────────────────

    def _browse_clone_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Reference Audio", "",
            "Audio Files (*.wav *.mp3)"
        )
        if path:
            self.edit_clone_file.setText(path)

    def _on_add_voice(self):
        name = self.edit_clone_name.text().strip()
        audio = self.edit_clone_file.text().strip()
        ref_text = self.edit_clone_ref_text.text().strip()

        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the voice.")
            return
        if not audio:
            QMessageBox.warning(self, "Missing Audio", "Please select an audio file.")
            return
        if not ref_text:
            QMessageBox.warning(self, "Missing Text",
                                "Please enter the transcript of the audio clip.\n"
                                "This is required for preset-quality voice encoding.")
            return

        self.voice_cloned.emit(name, audio, ref_text)

        # Clear inputs
        self.edit_clone_name.clear()
        self.edit_clone_file.clear()
        self.edit_clone_ref_text.clear()

    def _on_remove_voice(self):
        item = self.list_cloned.currentItem()
        if not item:
            QMessageBox.warning(self, "No Selection", "Please select a voice to remove.")
            return
        name = item.text()
        reply = QMessageBox.question(
            self, "Confirm Remove",
            f"Remove cloned voice \"{name}\"?\nThis deletes the encoded preset and reference files.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.voice_removed.emit(name)

    def refresh_cloned_list(self, names: list):
        """Repopulate the cloned-voice list widget."""
        self.list_cloned.clear()
        for n in names:
            self.list_cloned.addItem(n)

    def set_clone_status(self, msg: str):
        """Update the encoding status label."""
        self.lbl_clone_status.setText(msg)

    def set_clone_enabled(self, enabled: bool):
        """Enable/disable clone controls during encoding."""
        self.btn_add_voice.setEnabled(enabled)
        self.btn_browse_clone.setEnabled(enabled)
        self.edit_clone_name.setEnabled(enabled)
        self.edit_clone_ref_text.setEnabled(enabled)
        self.btn_transcribe.setEnabled(enabled)
        self.combo_whisper_model.setEnabled(enabled)

    def set_ref_text(self, text: str):
        """Set the reference text field (used after Whisper transcription)."""
        self.edit_clone_ref_text.setText(text)

    def set_transcribe_enabled(self, enabled: bool):
        """Enable/disable transcribe controls independently."""
        self.btn_transcribe.setEnabled(enabled)
        self.combo_whisper_model.setEnabled(enabled)

    def _on_transcribe(self):
        """Handle Auto-Transcribe button click."""
        audio = self.edit_clone_file.text().strip()
        if not audio:
            QMessageBox.warning(self, "No Audio",
                                "Please select an audio file first.")
            return
        model_size = self.combo_whisper_model.currentText()
        self.transcribe_requested.emit(audio, model_size)

    # ── Theme ──────────────────────────────────────────────────────────

    def change_theme(self, text):
        qdarktheme.setup_theme(text.lower())

    # ── Getters ────────────────────────────────────────────────────────
    def get_font_size(self):
        return self.spin_font_size.value()

    def get_auto_scroll(self):
        return self.chk_auto_scroll.isChecked()

    def get_read_max_retries(self):
        return self.spin_read_retries.value()

    def get_silence_gap(self):
        return self.spin_silence_gap.value()

    def get_batch_max_retries(self):
        return self.spin_batch_retries.value()
        
    def get_concurrent_chunks(self):
        return self.spin_concurrent_chunks.value()

    def get_output_extension(self):
        return ".mp3" if "MP3" in self.combo_output_fmt.currentText() else ".wav"

    def get_voice_design_description(self):
        return self.edit_voice_design.text().strip()
