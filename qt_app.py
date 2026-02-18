import sys
import os
import traceback

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
        from PyQt6.QtCore import Qt, QSize
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
                self.settings_view.btn_refresh.clicked.connect(self.populate_voices)
                
                # Playback Signals
                self.reader_view.btn_play.clicked.connect(self.playback_manager.play)
                self.reader_view.btn_pause.clicked.connect(self.playback_manager.pause)
                self.reader_view.btn_stop.clicked.connect(self.playback_manager.stop)
                self.playback_manager.sig_sentence_changed.connect(lambda i, t: self.reader_view.highlight_text(t))
                
                # Nav Signals
                self.reader_view.btn_prev.clicked.connect(self.prev_chapter)
                self.reader_view.btn_next.clicked.connect(self.next_chapter)
                self.reader_view.toc_list.currentRowChanged.connect(self.on_toc_chapter_selected)
                
                self.current_chapter_index = 0
                self.chapter_titles = []
                
                # Setup Batch
                self.setup_batch_connections()
                
                # VieNeu SDK handles model paths internally
                self.batch_view.edit_model.setText("vieneu SDK (auto)")

                self.populate_ref_voices()
                self.populate_voices()

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
                # Aggregate all voices
                voices = []
                voices.extend(self.tts_service.get_voices("edge"))
                voices.extend(self.tts_service.get_voices("google"))
                voices.extend(self.tts_service.get_voices("vieneu"))
                
                self.reader_view.combo_voice.clear()
                for v in voices:
                    # Format: "Name (ID)"
                    self.reader_view.combo_voice.addItem(f"{v['name']} ({v['id']})", v['id'])
                    
                # Set default if available (e.g. Google VN)
                index = self.reader_view.combo_voice.findData("vi")
                if index >= 0: self.reader_view.combo_voice.setCurrentIndex(index)

            def change_voice(self, index):
                voice_id = self.reader_view.combo_voice.itemData(index)
                if voice_id:
                    self.playback_manager.set_voice(voice_id)

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
                reply = QMessageBox.question(self, "Auto Setup", 
                                           "Download VieNeu-TTS code and models (~1GB++)?\nThis requires a stable internet connection.",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                
                if reply == QMessageBox.StandardButton.Yes:
                    self.batch_view.lbl_status.setText("Setting up... (Check Console)")
                    self.batch_view.progress_bar.setValue(0)
                    
                    # Use Worker
                    self.setup_worker = QtBatchWorker("setup")
                    self.setup_worker.signals.progress.connect(self.update_batch_status)
                    self.setup_worker.signals.finished.connect(self.on_setup_finished)
                    self.setup_worker.start()

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
                # For VieNeu engine, model path is handled by SDK
                if not model_path:
                     model_path = "vieneu SDK (auto)"

                # Get Engine & Voice
                engine_map = {
                    "Edge TTS": "edge",
                    "Google TTS": "google",
                    "VieNeu-TTS": "vieneu"
                }
                engine = engine_map.get(self.batch_view.combo_engine.currentText(), "edge")
                voice = self.batch_view.combo_voice.currentData()
                
                # Check Voice
                if not voice:
                     QMessageBox.warning(self, "Error", "Please select a voice.")
                     return

                # Get Ref from Combo (Only if VieNeu + custom voice)
                ref_path = self.batch_view.combo_ref.currentData() if engine == "vieneu" else None

                merge = self.batch_view.chk_merge.isChecked()
                
                # Start Worker
                self.batch_view.btn_start.setEnabled(False)
                self.batch_view.btn_stop.setEnabled(True)
                self.batch_worker = QtBatchWorker("convert", indices=indices, model_path=model_path, ref_path=ref_path, merge=merge, book_loader=self.book_loader, engine=engine, voice=voice)
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
                
            def on_setup_finished(self):
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(self, "Success", "VieNeu-TTS SDK Setup Complete!")
                self.batch_view.edit_model.setText("vieneu SDK (auto)")

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
                    if self.task_type == "setup":
                        from app.services.downloader import VieNeuDownloader
                        def cb(msg): self.signals.progress.emit(msg)
                        VieNeuDownloader.run_full_setup(progress_callback=cb)
                        
                    elif self.task_type == "convert":
                        from app.services.batch_service import BatchService
                        from app.services.parser import FileParser
                        from pathlib import Path
                        
                        indices = self.kwargs['indices']
                        model_path = self.kwargs['model_path']
                        ref_path = self.kwargs['ref_path']
                        merge = self.kwargs['merge']
                        loader = self.kwargs['book_loader']
                        engine = self.kwargs.get('engine', 'vieneu')
                        voice = self.kwargs.get('voice', None)
                        
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
                            
                            out_file = out_dir / f"ch_{idx+1}.mp3"
                            # Pass flags
                            BatchService.convert_chapter(
                                text, model_path, ref_path, str(out_file), 
                                progress_callback=log_cb,
                                check_stop_callback=stop_cb,
                                engine=engine,
                                voice=voice
                            )
                            
                            # If stopped inside convert_chapter, we should break here too if file wasn't fully made
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
