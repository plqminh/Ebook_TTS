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
        
        controls_layout.addWidget(QLabel("Speed:"))
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(50, 200) # 0.5x to 2.0x
        self.slider_speed.setValue(100)
        self.slider_speed.setFixedWidth(100)
        controls_layout.addWidget(self.slider_speed)
        
        controls_layout.addStretch()
        
        self.layout.addLayout(controls_layout)

    def set_text(self, text):
        self.text_browser.setPlainText(text)

    def append_text(self, text):
        self.text_browser.append(text)

    def highlight_text(self, text):
        if not text: return
        
        cursor = self.text_browser.textCursor()
        # Reset highlighting (Select All -> Format -> Clear Background)
        # This is expensive for large text. Better to just clear previous selection if tracked.
        # Naive reset:
        cursor.select(cursor.SelectionType.Document)
        fmt = cursor.charFormat()
        fmt.setBackground(Qt.GlobalColor.transparent)
        cursor.setCharFormat(fmt)
        cursor.clearSelection()
        
        # Find new text
        # Move to start
        cursor.setPosition(0)
        self.text_browser.setTextCursor(cursor)
        
        found = self.text_browser.find(text)
        if found:
            # Apply Highlight
            fmt = self.text_browser.textCursor().charFormat()
            from PyQt6.QtGui import QColor
            fmt.setBackground(QColor("yellow"))
            fmt.setForeground(QColor("black"))
            self.text_browser.textCursor().setCharFormat(fmt)
            
            # Ensure visible
            self.text_browser.ensureCursorVisible()
