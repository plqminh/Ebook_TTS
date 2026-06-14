import sys
import os
import traceback

# Suppress Qt Multimedia FFmpeg device enumeration spam on Windows
os.environ["QT_LOGGING_RULES"] = "qt.multimedia.*.debug=false;qt.multimedia.*.warning=false"

# CRITICAL: Pre-load PyTorch DLLs BEFORE PyQt6 imports.
# PyQt6 modifies Windows DLL search paths, which blocks torch's c10.dll from loading later.
_torch_lib = os.path.join(sys.prefix, "Lib", "site-packages", "torch", "lib")
if os.path.isdir(_torch_lib):
    os.add_dll_directory(_torch_lib)
    os.environ["PATH"] = _torch_lib + os.pathsep + os.environ.get("PATH", "")
try:
    import torch  # Force c10.dll to load NOW, before PyQt6
except Exception:
    pass  # torch might not be installed yet (first-time setup)

def main():
    try:
        from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                     QHBoxLayout, QListWidget, QStackedWidget, QLabel, QFrame)
        from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
        from PyQt6.QtGui import QIcon, QAction
        import qdarktheme

        class MainWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Ebook TTS Player (PyQt6)")
                self.resize(1100, 700)
                
                # Theme is applied after QApplication is created (see below)
                
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
                
                # --- Logic & Services ---
                from app.services.book_loader import BookLoader
                from app.services.parser import FileParser
                from app.services.tts_service import TTSService
                from app.services.playback_manager import PlaybackManager # New
                from PyQt6.QtWidgets import QFileDialog, QMessageBox
                
                self.book_loader = None
                self.tts_service = TTSService()
                self.playback_manager = PlaybackManager(self.tts_service)
                
                # Connect Signals
                self.reader_view.btn_load.clicked.connect(self.load_book)
                self.reader_view.combo_voice.currentIndexChanged.connect(self.change_voice)
                self.reader_view.slider_expression.valueChanged.connect(self._on_expression_changed)
                self.settings_view.btn_refresh.clicked.connect(self.populate_voices)
                
                # Settings Signals
                self.settings_view.spin_font_size.valueChanged.connect(self.on_font_size_changed)
                self.settings_view.spin_read_retries.valueChanged.connect(
                    lambda v: setattr(self.playback_manager, 'MAX_RETRIES', v)
                )

                # Voice Cloning Signals
                self.settings_view.voice_cloned.connect(self._on_voice_cloned)
                self.settings_view.voice_removed.connect(self._on_voice_removed)
                self.settings_view.transcribe_requested.connect(self._on_transcribe_requested)
                
                # Playback Signals
                self.reader_view.btn_play.clicked.connect(self.playback_manager.play)
                self.reader_view.btn_pause.clicked.connect(self.playback_manager.pause)
                self.reader_view.btn_stop.clicked.connect(self.playback_manager.stop)
                self.playback_manager.sig_sentence_changed.connect(lambda i, t: self.reader_view.highlight_text(t))
                
                # Nav Signals
                self.reader_view.btn_prev.clicked.connect(self.prev_chapter)
                self.reader_view.btn_next.clicked.connect(self.next_chapter)
                self.reader_view.toc_list.currentRowChanged.connect(self.on_toc_chapter_selected)
                self.playback_manager.sig_playback_finished.connect(self.auto_play_next_chapter)
                
                self.current_chapter_index = 0
                self.chapter_titles = []
                
                # Setup Batch
                self.setup_batch_connections()
                
                # VieNeu SDK handles model paths internally
                self.batch_view.edit_model.setText("vieneu SDK (auto)")

                self.populate_ref_voices()
                self.populate_voices()
                self._refresh_cloned_list()

            def populate_ref_voices(self):
                from pathlib import Path
                ref_dir = Path("assets/ref_voices")
                if not ref_dir.exists(): ref_dir.mkdir(parents=True, exist_ok=True)
                
                self.batch_view.combo_ref.clear()
                
                # Scan
                files = list(ref_dir.glob("*.wav")) + list(ref_dir.glob("*.mp3"))
                for f in files:
                    self.batch_view.combo_ref.addItem(f.name, str(f))
                    
                # Add Browse at the end
                self.batch_view.combo_ref.addItem("Browse...", None)
                
                # Default to first file if exists
                if files: self.batch_view.combo_ref.setCurrentIndex(0)

            # ... (Reader Logic) ...
            def prev_chapter(self):
                if self.current_chapter_index > 0:
                    self.load_chapter(self.current_chapter_index - 1)
            
            def next_chapter(self):
                if self.current_chapter_index < len(self.chapter_titles) - 1:
                    self.load_chapter(self.current_chapter_index + 1)
            
            def auto_play_next_chapter(self):
                if self.current_chapter_index < len(self.chapter_titles) - 1:
                    self.load_chapter(self.current_chapter_index + 1)
                    # Use a small delay to ensure UI updates and previous audio is released
                    from PyQt6.QtCore import QTimer
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
                except Exception as e:
                    print(f"Error loading chapter {index}: {e}")

            def populate_voices(self):
                # Aggregate all voices (vieneu includes custom voices automatically)
                voices = []
                voices.extend(self.tts_service.get_voices("edge"))
                voices.extend(self.tts_service.get_voices("google"))
                voices.extend(self.tts_service.get_voices("vieneu"))
                voices.extend(self.tts_service.get_voices("omnivoice"))

                self.reader_view.combo_voice.clear()
                for v in voices:
                    self.reader_view.combo_voice.addItem(f"{v['name']} ({v['id']})", v['id'])

                # Set default if available (e.g. Google VN)
                index = self.reader_view.combo_voice.findData("vi")
                if index >= 0: self.reader_view.combo_voice.setCurrentIndex(index)

            # ── Voice Cloning Handlers ─────────────────────────────────────

            class _EncodeThread(QThread):
                """Background thread for encoding reference audio."""
                finished = pyqtSignal(str)    # name
                error = pyqtSignal(str)        # error message

                def __init__(self, tts_service, name, audio_path, ref_text):
                    super().__init__()
                    self.tts_service = tts_service
                    self.name = name
                    self.audio_path = audio_path
                    self.ref_text = ref_text

                def run(self):
                    try:
                        self.tts_service.encode_and_save_voice(
                            self.name, self.audio_path, self.ref_text
                        )
                        self.finished.emit(self.name)
                    except Exception as e:
                        self.error.emit(str(e))

            def _on_voice_cloned(self, name, audio_path, ref_text):
                from PyQt6.QtWidgets import QMessageBox

                # Check for duplicates
                existing = self.tts_service.get_custom_voice_names()
                key = f"custom_{name}"
                if key in existing:
                    QMessageBox.warning(self, "Exists",
                                        f"A voice named \"{name}\" already exists.\n"
                                        "Remove it first or choose a different name.")
                    return

                # Disable controls and show status
                self.settings_view.set_clone_enabled(False)
                self.settings_view.set_clone_status("⏳ Encoding voice (loading VieNeu model)…")

                # Run encoding in background thread
                self._encode_thread = self._EncodeThread(
                    self.tts_service, name, audio_path, ref_text
                )
                self._encode_thread.finished.connect(self._on_encode_done)
                self._encode_thread.error.connect(self._on_encode_error)
                self._encode_thread.start()

            def _on_encode_done(self, name):
                from PyQt6.QtWidgets import QMessageBox
                self.settings_view.set_clone_enabled(True)
                self.settings_view.set_clone_status("")
                QMessageBox.information(self, "Done", f"Voice \"{name}\" added as preset!")
                self.populate_voices()
                self.populate_ref_voices()
                self._refresh_cloned_list()

            def _on_encode_error(self, error_msg):
                from PyQt6.QtWidgets import QMessageBox
                self.settings_view.set_clone_enabled(True)
                self.settings_view.set_clone_status("")
                QMessageBox.critical(self, "Error", f"Failed to encode voice:\n{error_msg}")

            def _on_voice_removed(self, name):
                from PyQt6.QtWidgets import QMessageBox
                self.tts_service.remove_custom_voice(name)
                QMessageBox.information(self, "Removed", f"Voice \"{name}\" removed.")
                self.populate_voices()
                self.populate_ref_voices()
                self._refresh_cloned_list()

            def _refresh_cloned_list(self):
                names = self.tts_service.get_custom_voice_names()
                # Strip "custom_" prefix for display
                display = [n.replace("custom_", "", 1) for n in names]
                self.settings_view.refresh_cloned_list(display)

            # ── Whisper Transcription Handlers ────────────────────────────────

            class _TranscribeThread(QThread):
                """Background thread for Whisper audio transcription."""
                finished = pyqtSignal(str)   # transcribed text
                error = pyqtSignal(str)       # error message

                def __init__(self, tts_service, audio_path, model_size):
                    super().__init__()
                    self.tts_service = tts_service
                    self.audio_path = audio_path
                    self.model_size = model_size

                def run(self):
                    try:
                        text = self.tts_service.transcribe_audio(
                            self.audio_path, self.model_size
                        )
                        self.finished.emit(text)
                    except Exception as e:
                        self.error.emit(str(e))

            def _on_transcribe_requested(self, audio_path, model_size):
                self.settings_view.set_transcribe_enabled(False)
                self.settings_view.set_clone_status(
                    f"⏳ Transcribing with Whisper ({model_size})… First run downloads the model."
                )

                self._transcribe_thread = self._TranscribeThread(
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
                from PyQt6.QtWidgets import QMessageBox
                self.settings_view.set_transcribe_enabled(True)
                self.settings_view.set_clone_status("")
                QMessageBox.critical(self, "Transcription Error",
                                     f"Whisper transcription failed:\n{error_msg}")

            def change_voice(self, index):
                voice_id = self.reader_view.combo_voice.itemData(index)
                if voice_id:
                    self.playback_manager.set_voice(voice_id)

            def _on_expression_changed(self, value):
                self.playback_manager.temperature = value / 10.0

            def load_book(self):
                from PyQt6.QtWidgets import QFileDialog, QMessageBox
                from app.services.book_loader import BookLoader
                
                file_path, _ = QFileDialog.getOpenFileName(self, "Open Ebook", "", "Ebooks (*.epub *.pdf *.docx *.txt)")
                
                if file_path:
                    try:
                        # Re-init loader with new path
                        if self.book_loader: self.book_loader.close()
                        self.book_loader = BookLoader(file_path)
                        
                        self.setWindowTitle(f"Ebook TTS Player - {file_path}")
                        
                        self.chapter_titles = [x['title'] for x in self.book_loader.get_toc()]
                        
                        # Populate UI List
                        self.reader_view.toc_list.clear()
                        self.reader_view.toc_list.addItems(self.chapter_titles)
                        
                        if self.chapter_titles:
                             self.load_chapter(0)
                        else:
                             pass

                        # 2. Update Batch View
                        self.batch_view.populate_chapters(self.chapter_titles)
                        
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to load book: {str(e)}")

            def switch_view(self, index):
                self.content_stack.setCurrentIndex(index)
                
            # --- Batch Logic ---
            def setup_batch_connections(self):
                self.batch_view.btn_setup.clicked.connect(self.run_auto_setup)
                self.batch_view.btn_start.clicked.connect(self.start_batch_conversion)
                self.batch_view.btn_stop.clicked.connect(self.stop_batch_conversion) # Connect STOP
                self.batch_view.btn_refresh_ref.clicked.connect(self.populate_ref_voices) # Refresh

            def run_auto_setup(self):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Auto Setup", 
                                           "OmniVoice models are downloaded automatically via HuggingFace Hub on first use.\nNo manual setup is required.")

            def start_batch_conversion(self):
                # Validation
                indices = []
                for row in range(self.batch_view.table_chapters.rowCount()):
                     if self.batch_view.table_chapters.item(row, 0).checkState() == Qt.CheckState.Checked:
                         indices.append(row)
                         
                if not indices:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "Error", "No chapters selected.")
                    return

                model_path = self.batch_view.edit_model.text()
                # For OmniVoice, model path is handled by HuggingFace Hub
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
                
                # Check Voice
                if not voice:
                     QMessageBox.warning(self, "Error", "Please select a voice.")
                     return

                # Get Ref from Combo (Only if OmniVoice + custom voice)
                ref_path = self.batch_view.combo_ref.currentData() if engine == "omnivoice" else None

                merge = self.batch_view.chk_merge.isChecked()

                # Read batch settings
                silence_gap = self.settings_view.get_silence_gap()
                batch_retries = self.settings_view.get_batch_max_retries()
                concurrent_chunks = self.settings_view.get_concurrent_chunks()
                output_ext = self.settings_view.get_output_extension()
                
                # Start Worker
                self.batch_view.btn_start.setEnabled(False)
                self.batch_view.btn_stop.setEnabled(True)
                
                # Get current expression/temperature from reader view
                temperature = self.reader_view.slider_expression.value() / 10.0

                # Get voice design description for OmniVoice
                voice_description = self.settings_view.get_voice_design_description()
                
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
                )
                self.batch_worker.signals.progress_val.connect(self.batch_view.progress_bar.setValue)
                self.batch_worker.signals.status.connect(self.batch_view.lbl_status.setText)
                self.batch_worker.signals.progress.connect(self.batch_view.log_area.append) # Log Text
                self.batch_worker.signals.finished.connect(self.on_batch_finished)
                self.batch_worker.start()

            def stop_batch_conversion(self):
                if hasattr(self, 'batch_worker') and self.batch_worker.isRunning():
                     self.batch_view.lbl_status.setText("Stopping...")
                     self.batch_view.log_area.append(">>> User requested STOP.")
                     self.batch_worker.requestInterruption()
                     self.batch_view.btn_stop.setEnabled(False)

            def update_batch_status(self, msg):
                self.batch_view.lbl_status.setText(msg)
                


            def on_font_size_changed(self, size):
                self.reader_view.text_browser.setStyleSheet(f"font-size: {size}pt;")
                # Re-render current text if loaded
                if hasattr(self.reader_view, '_plain_text'):
                    self.reader_view.set_text(self.reader_view._plain_text)

            def on_batch_finished(self):
                self.batch_view.btn_start.setEnabled(True)
                self.batch_view.btn_stop.setEnabled(False)
                self.batch_view.lbl_status.setText("Done/Stopped")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Finished", "Batch Process Finished or Stopped.")

        # --- Worker Thread ---
        from PyQt6.QtCore import QThread, pyqtSignal, QObject

        class WorkerSignals(QObject):
            finished = pyqtSignal()
            error = pyqtSignal(str)
            progress = pyqtSignal(str) # For text logging
            progress_val = pyqtSignal(int)
            status = pyqtSignal(str)

        class QtBatchWorker(QThread):
            def __init__(self, task_type, **kwargs):
                super().__init__()
                self.task_type = task_type
                self.kwargs = kwargs
                self.signals = WorkerSignals()
                
            def run(self):
                try:
                    if self.task_type == "convert":
                        from app.services.batch_service import BatchService
                        from app.services.parser import FileParser
                        from pathlib import Path
                        
                        indices = self.kwargs['indices']
                        model_path = self.kwargs['model_path']
                        ref_path = self.kwargs['ref_path']
                        merge = self.kwargs['merge']
                        loader = self.kwargs['book_loader']
                        engine = self.kwargs.get('engine', 'omnivoice')
                        voice = self.kwargs.get('voice', None)
                        silence_gap = self.kwargs.get('silence_gap', 0.3)
                        batch_retries = self.kwargs.get('batch_retries', 3)
                        concurrent_chunks = self.kwargs.get('concurrent_chunks', 3)
                        output_ext = self.kwargs.get('output_ext', '.mp3')
                        temperature = self.kwargs.get('temperature', 1.0)
                        voice_description = self.kwargs.get('voice_description', None)
                        
                        total = len(indices)
                        outputs = []
                        out_dir = Path("batch_output")
                        out_dir.mkdir(exist_ok=True)
                        
                        def log_cb(msg):
                            self.signals.progress.emit(msg)
                            
                        # Stop check callback
                        def stop_cb():
                            return self.isInterruptionRequested()
                        
                        for i, idx in enumerate(indices):
                            # Check stop between chapters
                            if self.isInterruptionRequested():
                                log_cb("Batch processing stopped.")
                                break
                                
                            self.signals.status.emit(f"Processing Chapter {idx+1} ({i+1}/{total})...")
                            self.signals.progress_val.emit(int((i / total) * 100))
                            
                            text = loader.get_chapter_content(idx)
                            if not text: continue
                            
                            out_file = out_dir / f"ch_{idx+1}{output_ext}"
                            BatchService.convert_chapter(
                                text, model_path, ref_path, str(out_file), 
                                progress_callback=log_cb,
                                check_stop_callback=stop_cb,
                                engine=engine,
                                voice=voice,
                                silence_gap=silence_gap,
                                max_retries=batch_retries,
                                temperature=temperature,
                                concurrent_chunks=concurrent_chunks,
                                voice_description=voice_description,
                            )
                            
                            if self.isInterruptionRequested():
                                break
                                
                            outputs.append(str(out_file))
                        
                        if not self.isInterruptionRequested() and merge and outputs:
                            self.signals.status.emit("Merging...")
                            BatchService.merge_audios(outputs, str(out_dir / "full_book.mp3"))

                    self.signals.finished.emit()
                    
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    print(f"Worker Error Traceback:\n{tb}")
                    self.signals.error.emit(f"{str(e)}\n\nCheck console for details.")
        app = QApplication(sys.argv)
        app.setStyleSheet(qdarktheme.load_stylesheet())
        window = MainWindow()
        window.show()
        sys.exit(app.exec())

    except Exception as e:
        with open("qt_error.log", "w") as f:
            f.write(traceback.format_exc())
        print(f"CRASH: {e}")
        input("Press Enter to Exit...")

if __name__ == "__main__":
    main()
