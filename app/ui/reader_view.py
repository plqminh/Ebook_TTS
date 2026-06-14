from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, 
                             QPushButton, QLabel, QComboBox, QSlider, QFileDialog, QListWidget)
from PyQt6.QtCore import Qt, pyqtSignal

class ReaderWidget(QWidget):
    def __init__(self):
        super().__init__()
        
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
        
        # 3. Controls (Playback + Settings)
        controls_layout = QHBoxLayout()
        
        # Playback
        self.btn_play = QPushButton("▶ Play")
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_stop = QPushButton("⏹ Stop")
        
        controls_layout.addWidget(self.btn_play)
        controls_layout.addWidget(self.btn_pause)
        controls_layout.addWidget(self.btn_stop)
        
        # Separator
        controls_layout.addSpacing(20)
        
        # Voice Settings
        controls_layout.addWidget(QLabel("Voice:"))
        self.combo_voice = QComboBox()
        controls_layout.addWidget(self.combo_voice)
        
        controls_layout.addWidget(QLabel("Expression:"))
        self.slider_expression = QSlider(Qt.Orientation.Horizontal)
        self.slider_expression.setRange(1, 20)  # 0.1 to 2.0 (value / 10)
        self.slider_expression.setValue(10)       # Default: 1.0
        self.slider_expression.setFixedWidth(100)
        self.lbl_expression = QLabel("1.0")
        self.slider_expression.valueChanged.connect(
            lambda v: self.lbl_expression.setText(f"{v / 10:.1f}")
        )
        controls_layout.addWidget(self.slider_expression)
        controls_layout.addWidget(self.lbl_expression)
        
        controls_layout.addStretch()
        
        self.layout.addLayout(controls_layout)

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
