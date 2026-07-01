"""
MainWindow — Central controller for the Ebook TTS application.
Extracted from the monolithic qt_app.py for maintainability.
"""
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QListWidget, QStackedWidget, QFileDialog, QMessageBox,
                             QStatusBar)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence
from pathlib import Path

from app.logger import logger
from app.workers import QtBatchWorker, EncodeThread, TranscribeThread


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ebook TTS Player (PyQt6)")
        self.resize(1100, 700)
        self.setAcceptDrops(True)

        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main Layout (Horizontal)
        self.main_layout = QHBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setStyleSheet("""
            QListWidget {
                background-color: #21252b;
                border: none;
                font-size: 14px;
                padding-top: 20px;
            }
            QListWidget::item {
                height: 50px;
                padding-left: 15px;
                color: #abb2bf;
            }
            QListWidget::item:selected {
                background-color: #2c313a;
                border-left: 4px solid #61afef;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #2c313a;
            }
        """)
        self.sidebar.addItems(["📖 Reader", "⚡ Batch MP3", "⚙️ Settings"])
        self.sidebar.currentRowChanged.connect(self.switch_view)

        self.main_layout.addWidget(self.sidebar)

        # --- Content Area (Stacked) ---
        self.content_stack = QStackedWidget()
        self.main_layout.addWidget(self.content_stack)

        # View 1: Reader
        from app.ui.reader_view import ReaderWidget
        self.reader_view = ReaderWidget()
        self.content_stack.addWidget(self.reader_view)

        # View 2: Batch
        from app.ui.batch_view import BatchWidget
        self.batch_view = BatchWidget()
        self.content_stack.addWidget(self.batch_view)

        # View 3: Settings
        from app.ui.settings_view import SettingsWidget
        self.settings_view = SettingsWidget()
        self.content_stack.addWidget(self.settings_view)

        # Select first item
        self.sidebar.setCurrentRow(0)

        # --- Status Bar ---
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._lbl_chapter_pos = None  # Lazy init

        # --- Logic & Services ---
        from app.services.tts_service import TTSService
        from app.services.playback_manager import PlaybackManager

        self.book_loader = None
        self.tts_service = TTSService()
        self.playback_manager = PlaybackManager(self.tts_service)

        # ── Connect Signals ───────────────────────────────────────

        # Reader controls
        self.reader_view.btn_load.clicked.connect(self.load_book)
        self.reader_view.combo_voice.currentIndexChanged.connect(self.change_voice)
        self.reader_view.slider_expression.valueChanged.connect(self._on_expression_changed)
        self.reader_view.slider_speed.valueChanged.connect(self._on_speed_changed)
        self.reader_view.slider_pitch.valueChanged.connect(self._on_pitch_changed)
        self.reader_view.file_dropped.connect(self._load_book_from_path)

        # Settings controls
        self.settings_view.btn_refresh.clicked.connect(self.populate_voices)
        self.settings_view.spin_font_size.valueChanged.connect(self.on_font_size_changed)
        self.settings_view.spin_read_retries.valueChanged.connect(
            lambda v: setattr(self.playback_manager, 'MAX_RETRIES', v)
        )
        self.settings_view.cache_clear_requested.connect(self._on_clear_cache)

        # Voice Cloning
        self.settings_view.voice_cloned.connect(self._on_voice_cloned)
        self.settings_view.voice_removed.connect(self._on_voice_removed)
        self.settings_view.transcribe_requested.connect(self._on_transcribe_requested)

        # Playback
        self.reader_view.btn_play.clicked.connect(self.playback_manager.play)
        self.reader_view.btn_pause.clicked.connect(self.playback_manager.pause)
        self.reader_view.btn_stop.clicked.connect(self.playback_manager.stop)
        self.reader_view.btn_skip_prev.clicked.connect(self.playback_manager.skip_prev)
        self.reader_view.btn_skip_next.clicked.connect(self.playback_manager.skip_next)
        self.playback_manager.sig_sentence_changed.connect(self._on_sentence_changed)
        self.playback_manager.sig_status.connect(self._update_status)

        # Nav
        self.reader_view.btn_prev.clicked.connect(self.prev_chapter)
        self.reader_view.btn_next.clicked.connect(self.next_chapter)
        self.reader_view.toc_list.currentRowChanged.connect(self.on_toc_chapter_selected)
        self.playback_manager.sig_playback_finished.connect(self.auto_play_next_chapter)

        self.current_chapter_index = 0
        self.chapter_titles = []

        # Batch
        self.setup_batch_connections()
        self.batch_view.edit_model.setText("OmniVoice SDK (auto)")

        # Populate
        self.populate_ref_voices()
        self.populate_voices()
        self._refresh_cloned_list()

        # Keyboard Shortcuts
        self._setup_shortcuts()

        # Clean up orphaned temp files on startup
        from app.services.playback_manager import PlaybackManager as PM
        orphaned = PM.cleanup_temp_audio()
        if orphaned:
            logger.info(f"Startup: cleaned {orphaned} orphaned temp audio files.")

        logger.info("MainWindow initialized.")

    # ── Keyboard Shortcuts ─────────────────────────────────────────────

    def _setup_shortcuts(self):
        """Bind keyboard shortcuts for common actions."""
        # Play / Pause toggle
        QShortcut(QKeySequence(Qt.Key.Key_Space), self).activated.connect(
            self._toggle_play_pause
        )
        # Stop
        QShortcut(QKeySequence(Qt.Key.Key_S), self).activated.connect(
            self.playback_manager.stop
        )
        # Previous / Next chapter
        QShortcut(QKeySequence(Qt.Key.Key_Left), self).activated.connect(
            self.prev_chapter
        )
        QShortcut(QKeySequence(Qt.Key.Key_Right), self).activated.connect(
            self.next_chapter
        )
        # Skip sentence (Ctrl+Arrow)
        QShortcut(QKeySequence("Ctrl+Left"), self).activated.connect(
            self.playback_manager.skip_prev
        )
        QShortcut(QKeySequence("Ctrl+Right"), self).activated.connect(
            self.playback_manager.skip_next
        )
        # Open file
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(
            self.load_book
        )
        # Font size
        QShortcut(QKeySequence(Qt.Key.Key_Plus), self).activated.connect(
            lambda: self.settings_view.spin_font_size.setValue(
                self.settings_view.spin_font_size.value() + 1
            )
        )
        QShortcut(QKeySequence(Qt.Key.Key_Minus), self).activated.connect(
            lambda: self.settings_view.spin_font_size.setValue(
                self.settings_view.spin_font_size.value() - 1
            )
        )

    def _toggle_play_pause(self):
        if self.playback_manager.is_playing:
            self.playback_manager.pause()
        else:
            self.playback_manager.play()

    # ── Status Bar ─────────────────────────────────────────────────────

    def _update_status(self, msg):
        self.status_bar.showMessage(msg, 5000)

    def _update_chapter_status(self):
        """Update the persistent chapter position in the status bar."""
        if self.chapter_titles:
            total = len(self.chapter_titles)
            current = self.current_chapter_index + 1
            pct = int((current / total) * 100)
            self.status_bar.showMessage(
                f"Chapter {current} of {total} ({pct}%)", 0
            )

    # ── Drag & Drop on MainWindow ──────────────────────────────────────

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
                self._load_book_from_path(path)
                return

    # ── Voice / Tuning ─────────────────────────────────────────────────

    def populate_ref_voices(self):
        ref_dir = Path("assets/ref_voices")
        if not ref_dir.exists():
            ref_dir.mkdir(parents=True, exist_ok=True)

        self.batch_view.combo_ref.clear()

        files = list(ref_dir.glob("*.wav")) + list(ref_dir.glob("*.mp3"))
        for f in files:
            self.batch_view.combo_ref.addItem(f.name, str(f))

        self.batch_view.combo_ref.addItem("Browse...", None)

        if files:
            self.batch_view.combo_ref.setCurrentIndex(0)

    def populate_voices(self):
        voices = []
        voices.extend(self.tts_service.get_voices("edge"))
        voices.extend(self.tts_service.get_voices("google"))
        voices.extend(self.tts_service.get_voices("omnivoice"))

        self.reader_view.combo_voice.clear()
        for v in voices:
            self.reader_view.combo_voice.addItem(f"{v['name']} ({v['id']})", v['id'])

        index = self.reader_view.combo_voice.findData("vi-VN-HoaiMyNeural")
        if index < 0:
            index = self.reader_view.combo_voice.findData("vi")
        if index >= 0:
            self.reader_view.combo_voice.setCurrentIndex(index)

    def change_voice(self, index):
        voice_id = self.reader_view.combo_voice.itemData(index)
        if voice_id:
            self.playback_manager.set_voice(voice_id)

    def _on_expression_changed(self, value):
        self.playback_manager.temperature = value / 10.0

    def _on_speed_changed(self, value):
        rate_str = f"{'+' if value >= 0 else ''}{value}%"
        self.playback_manager.set_rate(rate_str)

    def _on_pitch_changed(self, value):
        pitch_str = f"{'+' if value >= 0 else ''}{value}Hz"
        self.playback_manager.set_pitch(pitch_str)

    # ── Reader / Chapter Navigation ────────────────────────────────────

    def prev_chapter(self):
        if self.current_chapter_index > 0:
            self.load_chapter(self.current_chapter_index - 1)

    def next_chapter(self):
        if self.current_chapter_index < len(self.chapter_titles) - 1:
            self.load_chapter(self.current_chapter_index + 1)

    def auto_play_next_chapter(self):
        if self.current_chapter_index < len(self.chapter_titles) - 1:
            self.load_chapter(self.current_chapter_index + 1)
            QTimer.singleShot(100, self.playback_manager.play)

    def on_toc_chapter_selected(self, index):
        if 0 <= index < len(self.chapter_titles):
            if index != self.current_chapter_index:
                self.load_chapter(index)

    def load_chapter(self, index):
        try:
            self.current_chapter_index = index

            # Sync UI
            self.reader_view.toc_list.blockSignals(True)
            self.reader_view.toc_list.setCurrentRow(index)
            self.reader_view.toc_list.blockSignals(False)

            title = self.chapter_titles[index] if index < len(self.chapter_titles) else "Unknown"
            self.reader_view.lbl_title.setText(title)

            content = self.book_loader.get_chapter_content(index)
            self.reader_view.set_text(content)
            self.playback_manager.reset(content)

            self._update_chapter_status()

            # Save progress
            self._save_current_progress()

        except Exception as e:
            logger.error(f"Error loading chapter {index}: {e}", exc_info=True)

    def _on_sentence_changed(self, index, text):
        """Handle sentence change — update highlight and progress bar."""
        self.reader_view.highlight_text(text)
        total = len(self.playback_manager.sentences)
        self.reader_view.update_reading_progress(index + 1, total)

    # ── Book Loading ───────────────────────────────────────────────────

    def load_book(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Ebook", "", "Ebooks (*.epub *.pdf *.docx *.txt)"
        )
        if file_path:
            self._load_book_from_path(file_path)

    def _load_book_from_path(self, file_path):
        """Load a book from a given file path (used by Open dialog and drag-drop)."""
        from app.services.book_loader import BookLoader
        from app.services.history_manager import HistoryManager

        try:
            if self.book_loader:
                self.book_loader.close()
            self.book_loader = BookLoader(file_path)

            self.setWindowTitle(f"Ebook TTS Player - {Path(file_path).name}")

            self.chapter_titles = [x['title'] for x in self.book_loader.get_toc()]

            # Populate UI
            self.reader_view.toc_list.clear()
            self.reader_view.toc_list.addItems(self.chapter_titles)

            # Resume from last position if available
            progress = HistoryManager.get_progress(file_path)
            start_chapter = progress["chapter_index"]
            start_sentence = progress["sentence_index"]

            if start_chapter >= len(self.chapter_titles):
                start_chapter = 0
                start_sentence = 0

            if self.chapter_titles:
                self.load_chapter(start_chapter)
                if start_sentence > 0:
                    self.playback_manager.set_position(start_sentence)

            # Update Batch View
            self.batch_view.populate_chapters(self.chapter_titles)

            self._current_file_path = file_path
            logger.info(f"Loaded book: {file_path} ({len(self.chapter_titles)} chapters)")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load book: {str(e)}")
            logger.error(f"Failed to load book: {e}", exc_info=True)

    def _save_current_progress(self):
        """Save current reading position to history."""
        if hasattr(self, '_current_file_path') and self._current_file_path:
            from app.services.history_manager import HistoryManager
            HistoryManager.save_progress(
                self._current_file_path,
                self.current_chapter_index,
                self.playback_manager.current_index,
            )

    # ── Voice Cloning ──────────────────────────────────────────────────

    def _on_voice_cloned(self, name, audio_path, ref_text):
        existing = self.tts_service.get_custom_voice_names()
        key = f"custom_{name}"
        if key in existing:
            QMessageBox.warning(self, "Exists",
                                f"A voice named \"{name}\" already exists.\n"
                                "Remove it first or choose a different name.")
            return

        self.settings_view.set_clone_enabled(False)
        self.settings_view.set_clone_status("⏳ Encoding voice (loading model)…")

        self._encode_thread = EncodeThread(
            self.tts_service, name, audio_path, ref_text
        )
        self._encode_thread.finished.connect(self._on_encode_done)
        self._encode_thread.error.connect(self._on_encode_error)
        self._encode_thread.start()

    def _on_encode_done(self, name):
        self.settings_view.set_clone_enabled(True)
        self.settings_view.set_clone_status("")
        QMessageBox.information(self, "Done", f"Voice \"{name}\" added as preset!")
        self.populate_voices()
        self.populate_ref_voices()
        self._refresh_cloned_list()

    def _on_encode_error(self, error_msg):
        self.settings_view.set_clone_enabled(True)
        self.settings_view.set_clone_status("")
        QMessageBox.critical(self, "Error", f"Failed to encode voice:\n{error_msg}")

    def _on_voice_removed(self, name):
        self.tts_service.remove_custom_voice(name)
        QMessageBox.information(self, "Removed", f"Voice \"{name}\" removed.")
        self.populate_voices()
        self.populate_ref_voices()
        self._refresh_cloned_list()

    def _refresh_cloned_list(self):
        names = self.tts_service.get_custom_voice_names()
        display = [n.replace("custom_", "", 1) for n in names]
        self.settings_view.refresh_cloned_list(display)

    # ── Whisper Transcription ──────────────────────────────────────────

    def _on_transcribe_requested(self, audio_path, model_size):
        self.settings_view.set_transcribe_enabled(False)
        self.settings_view.set_clone_status(
            f"⏳ Transcribing with Whisper ({model_size})… First run downloads the model."
        )

        self._transcribe_thread = TranscribeThread(
            self.tts_service, audio_path, model_size
        )
        self._transcribe_thread.finished.connect(self._on_transcribe_done)
        self._transcribe_thread.error.connect(self._on_transcribe_error)
        self._transcribe_thread.start()

    def _on_transcribe_done(self, text):
        self.settings_view.set_transcribe_enabled(True)
        self.settings_view.set_clone_status("")
        self.settings_view.set_ref_text(text)

    def _on_transcribe_error(self, error_msg):
        self.settings_view.set_transcribe_enabled(True)
        self.settings_view.set_clone_status("")
        QMessageBox.critical(self, "Transcription Error",
                             f"Whisper transcription failed:\n{error_msg}")

    # ── View Switching ─────────────────────────────────────────────────

    def switch_view(self, index):
        self.content_stack.setCurrentIndex(index)

    def on_font_size_changed(self, size):
        self.reader_view.text_browser.setStyleSheet(f"font-size: {size}pt;")
        if hasattr(self.reader_view, '_plain_text'):
            self.reader_view.set_text(self.reader_view._plain_text)

    # ── Batch Logic ────────────────────────────────────────────────────

    def setup_batch_connections(self):
        self.batch_view.btn_setup.clicked.connect(self.run_auto_setup)
        self.batch_view.btn_start.clicked.connect(self.start_batch_conversion)
        self.batch_view.btn_stop.clicked.connect(self.stop_batch_conversion)
        self.batch_view.btn_pause.clicked.connect(self._toggle_batch_pause)
        self.batch_view.btn_refresh_ref.clicked.connect(self.populate_ref_voices)

    def run_auto_setup(self):
        QMessageBox.information(self, "Auto Setup",
                                "OmniVoice models are downloaded automatically via "
                                "HuggingFace Hub on first use.\nNo manual setup is required.")

    def start_batch_conversion(self):
        # Validation
        indices = []
        for row in range(self.batch_view.table_chapters.rowCount()):
            if self.batch_view.table_chapters.item(row, 0).checkState() == Qt.CheckState.Checked:
                indices.append(row)

        if not indices:
            QMessageBox.warning(self, "Error", "No chapters selected.")
            return

        model_path = self.batch_view.edit_model.text()
        if not model_path:
            model_path = "OmniVoice (auto)"

        # Get Engine & Voice
        engine_map = {
            "Edge TTS": "edge",
            "Google TTS": "google",
            "OmniVoice": "omnivoice",
        }
        engine = engine_map.get(self.batch_view.combo_engine.currentText(), "edge")
        voice = self.batch_view.combo_voice.currentData()

        if not voice:
            QMessageBox.warning(self, "Error", "Please select a voice.")
            return

        ref_path = self.batch_view.combo_ref.currentData() if engine == "omnivoice" else None
        merge = self.batch_view.chk_merge.isChecked()
        output_dir = self.batch_view.get_output_dir()

        # Read batch settings
        silence_gap = self.settings_view.get_silence_gap()
        batch_retries = self.settings_view.get_batch_max_retries()
        concurrent_chunks = self.settings_view.get_concurrent_chunks()
        output_ext = self.settings_view.get_output_extension()
        temperature = self.reader_view.slider_expression.value() / 10.0
        voice_description = self.settings_view.get_voice_design_description()

        # Start Worker
        self.batch_view.btn_start.setEnabled(False)
        self.batch_view.btn_stop.setEnabled(True)
        self.batch_view.btn_pause.setEnabled(True)
        self.batch_view.btn_pause.setText("⏸ PAUSE")

        self.batch_worker = QtBatchWorker(
            "convert",
            indices=indices,
            model_path=model_path,
            ref_path=ref_path,
            merge=merge,
            book_loader=self.book_loader,
            engine=engine,
            voice=voice,
            silence_gap=silence_gap,
            batch_retries=batch_retries,
            concurrent_chunks=concurrent_chunks,
            output_ext=output_ext,
            temperature=temperature,
            voice_description=voice_description,
            output_dir=output_dir,
        )
        self.batch_worker.signals.progress_val.connect(self.batch_view.progress_bar.setValue)
        self.batch_worker.signals.status.connect(self.batch_view.lbl_status.setText)
        self.batch_worker.signals.progress.connect(self.batch_view.log_area.append)
        self.batch_worker.signals.finished.connect(self.on_batch_finished)
        self.batch_worker.start()
        logger.info(f"Batch conversion started: {len(indices)} chapters, engine={engine}")

    def stop_batch_conversion(self):
        if hasattr(self, 'batch_worker') and self.batch_worker.isRunning():
            self.batch_view.lbl_status.setText("Stopping...")
            self.batch_view.log_area.append(">>> User requested STOP.")
            self.batch_worker.requestInterruption()
            self.batch_view.btn_stop.setEnabled(False)
            self.batch_view.btn_pause.setEnabled(False)

    def _toggle_batch_pause(self):
        if not hasattr(self, 'batch_worker') or not self.batch_worker.isRunning():
            return

        if self.batch_worker._paused:
            self.batch_worker.resume()
            self.batch_view.lbl_status.setText("Resumed...")
            self.batch_view.log_area.append(">>> Resumed.")
        else:
            self.batch_worker.pause()
            self.batch_view.lbl_status.setText("Paused")
            self.batch_view.log_area.append(">>> Paused by user.")

    def on_batch_finished(self):
        self.batch_view.btn_start.setEnabled(True)
        self.batch_view.btn_stop.setEnabled(False)
        self.batch_view.btn_pause.setEnabled(False)
        self.batch_view.lbl_status.setText("Done/Stopped")
        QMessageBox.information(self, "Finished", "Batch Process Finished or Stopped.")
        logger.info("Batch conversion finished.")

    # ── Cache Cleanup ──────────────────────────────────────────────────

    def _on_clear_cache(self):
        from app.services.playback_manager import PlaybackManager as PM
        count = PM.cleanup_temp_audio()
        QMessageBox.information(self, "Cache Cleared",
                                f"Deleted {count} temporary audio files.")

    # ── Graceful Shutdown ──────────────────────────────────────────────

    def closeEvent(self, event):
        """Save progress, stop threads, clean up on app close."""
        logger.info("Application closing...")

        # Save reading progress
        self._save_current_progress()

        # Stop playback
        self.playback_manager.shutdown()

        # Stop batch worker if running
        if hasattr(self, 'batch_worker') and self.batch_worker.isRunning():
            self.batch_worker.requestInterruption()
            self.batch_worker.wait(3000)

        # Stop encode/transcribe threads
        for attr in ('_encode_thread', '_transcribe_thread'):
            thread = getattr(self, attr, None)
            if thread and thread.isRunning():
                thread.wait(3000)

        logger.info("Application closed cleanly.")
        event.accept()
