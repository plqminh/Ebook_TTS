from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, 
                             QPushButton, QLabel, QComboBox, QSlider, QFileDialog,
                             QListWidget, QProgressBar)
from PyQt6.QtCore import Qt, pyqtSignal


class ReaderWidget(QWidget):
    # Signal emitted when a file is dropped onto the widget
    file_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        
        # Main Layout (Split: TOC | Content)
        main_h_layout = QHBoxLayout(self)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        
        # --- TOC Sidebar ---
        self.toc_list = QListWidget()
        self.toc_list.setFixedWidth(200)
        # self.toc_list.setVisible(False) # Optional: Toggle
        self.toc_list.setStyleSheet("border-right: 1px solid #444;")
        main_h_layout.addWidget(self.toc_list)
        
        # --- Content Area ---
        content_widget = QWidget()
        self.layout = QVBoxLayout(content_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        main_h_layout.addWidget(content_widget)
        
        # 1. Header (Book Title + Nav)
        header_layout = QHBoxLayout()
        self.btn_load = QPushButton("📂 Load Book")
        self.lbl_title = QLabel("No Book Loaded")
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_next = QPushButton("Next ▶")
        
        header_layout.addWidget(self.btn_load)
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_prev)
        header_layout.addWidget(self.btn_next)
        
        self.layout.addLayout(header_layout)
        
        # 2. Text Area (High Performance)
        self.text_browser = QTextBrowser()
        self.text_browser.setFontPointSize(14)
        self.text_browser.setOpenExternalLinks(False)
        self.layout.addWidget(self.text_browser)
        
        # 2b. Reading Progress Bar (thin, under text)
        self.progress_reading = QProgressBar()
        self.progress_reading.setFixedHeight(4)
        self.progress_reading.setTextVisible(False)
        self.progress_reading.setStyleSheet(
            "QProgressBar { background-color: #333; border: none; }"
            "QProgressBar::chunk { background-color: #61afef; }"
        )
        self.progress_reading.setValue(0)
        self.layout.addWidget(self.progress_reading)
        
        # 3. Playback Controls (Row 1)
        controls_layout = QHBoxLayout()
        
        self.btn_play = QPushButton("▶ Play")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_skip_prev = QPushButton("⏪")
        self.btn_skip_prev.setFixedWidth(36)
        self.btn_skip_prev.setToolTip("Previous sentence")
        self.btn_skip_next = QPushButton("⏩")
        self.btn_skip_next.setFixedWidth(36)
        self.btn_skip_next.setToolTip("Next sentence")
        
        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_pause)
        controls_layout.addWidget(self.btn_stop)
        controls_layout.addWidget(self.btn_skip_prev)
        controls_layout.addWidget(self.btn_skip_next)
        
        # Separator
        controls_layout.addSpacing(20)
        
        # Voice Selection
        controls_layout.addWidget(QLabel("Voice:"))
        self.combo_voice = QComboBox()
        controls_layout.addWidget(self.combo_voice)
        
        controls_layout.addStretch()
        self.layout.addLayout(controls_layout)

        # 4. TTS Tuning Controls (Row 2)
        tuning_layout = QHBoxLayout()

        # Speed (Edge/Google: rate parameter)
        tuning_layout.addWidget(QLabel("Speed:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(-50, 100)
        self.slider_speed.setValue(0)
        self.slider_speed.setFixedWidth(100)
        self.slider_speed.setToolTip("TTS speaking rate (-50% to +100%)")
        self.lbl_speed = QLabel("+0%")
        self.lbl_speed.setFixedWidth(40)
        self.slider_speed.valueChanged.connect(
            lambda v: self.lbl_speed.setText(f"{'+' if v >= 0 else ''}{v}%")
        )
        tuning_layout.addWidget(self.slider_speed)
        tuning_layout.addWidget(self.lbl_speed)

        tuning_layout.addSpacing(12)

        # Pitch (Edge: pitch parameter)
        tuning_layout.addWidget(QLabel("Pitch:"))
        self.slider_pitch = QSlider(Qt.Orientation.Horizontal)
        self.slider_pitch.setRange(-50, 50)
        self.slider_pitch.setValue(0)
        self.slider_pitch.setFixedWidth(100)
        self.slider_pitch.setToolTip("TTS pitch offset (-50Hz to +50Hz)")
        self.lbl_pitch = QLabel("+0Hz")
        self.lbl_pitch.setFixedWidth(45)
        self.slider_pitch.valueChanged.connect(
            lambda v: self.lbl_pitch.setText(f"{'+' if v >= 0 else ''}{v}Hz")
        )
        tuning_layout.addWidget(self.slider_pitch)
        tuning_layout.addWidget(self.lbl_pitch)

        tuning_layout.addSpacing(12)

        # Expression / Temperature (OmniVoice)
        tuning_layout.addWidget(QLabel("Expression:"))
        self.slider_expression = QSlider(Qt.Orientation.Horizontal)
        self.slider_expression.setRange(1, 20)  # 0.1 to 2.0 (value / 10)
        self.slider_expression.setValue(10)       # Default: 1.0
        self.slider_expression.setFixedWidth(100)
        self.slider_expression.setToolTip("OmniVoice expression/temperature (0.1–2.0)")
        self.lbl_expression = QLabel("1.0")
        self.lbl_expression.setFixedWidth(30)
        self.slider_expression.valueChanged.connect(
            lambda v: self.lbl_expression.setText(f"{v / 10:.1f}")
        )
        tuning_layout.addWidget(self.slider_expression)
        tuning_layout.addWidget(self.lbl_expression)

        tuning_layout.addStretch()
        self.layout.addLayout(tuning_layout)

    # ── Text Display ───────────────────────────────────────────────────

    def set_text(self, text):
        self._plain_text = text
        self.text_browser.setHtml(self._build_html(text))

    def append_text(self, text):
        self.text_browser.append(text)

    def _build_html(self, text, highlight_sentence=None):
        """Build HTML with optional sentence highlighting."""
        import html
        escaped = html.escape(text)
        if highlight_sentence:
            escaped_sentence = html.escape(highlight_sentence)
            escaped = escaped.replace(
                escaped_sentence,
                f'<span style="background-color: yellow; color: black;">{escaped_sentence}</span>',
                1  # only first match
            )
        # Preserve whitespace/newlines with pre-wrap
        return f'<div style="font-size: 14pt; font-family: sans-serif; white-space: pre-wrap; line-height: 1.5;">{escaped}</div>'

    def highlight_text(self, text):
        if not text or not hasattr(self, '_plain_text'): return
        self.text_browser.setHtml(self._build_html(self._plain_text, text))
        
        # Scroll to the highlighted text
        found = self.text_browser.find(text)
        if found:
            self.text_browser.ensureCursorVisible()

    def update_reading_progress(self, current_sentence, total_sentences):
        """Update the thin reading progress bar."""
        if total_sentences > 0:
            pct = int((current_sentence / total_sentences) * 100)
            self.progress_reading.setValue(pct)
        else:
            self.progress_reading.setValue(0)

    # ── Drag & Drop ────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile().lower()
                if path.endswith(('.epub', '.pdf', '.docx', '.txt')):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.epub', '.pdf', '.docx', '.txt')):
                self.file_dropped.emit(path)
                return
