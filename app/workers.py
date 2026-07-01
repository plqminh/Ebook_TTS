"""
Worker threads for background tasks (batch conversion, voice encoding, transcription).
Extracted from qt_app.py for cleaner architecture and reusability.
"""
from PyQt6.QtCore import QThread, pyqtSignal, QObject

from app.logger import logger


# ── Shared Signals ─────────────────────────────────────────────────────

class WorkerSignals(QObject):
    """Signals emitted by the batch worker thread."""
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str)       # text log line
    progress_val = pyqtSignal(int)   # 0-100
    status = pyqtSignal(str)         # status bar text


# ── Batch Conversion Worker ────────────────────────────────────────────

class QtBatchWorker(QThread):
    """Background thread for batch chapter-to-audio conversion."""

    def __init__(self, task_type, **kwargs):
        super().__init__()
        self.task_type = task_type
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._paused = False

    # ── Pause / Resume ────────────────────────────────────────
    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def _wait_if_paused(self):
        """Block the worker while paused (checked between chunks)."""
        import time
        while self._paused and not self.isInterruptionRequested():
            time.sleep(0.2)

    # ── Main Run ──────────────────────────────────────────────
    def run(self):
        try:
            if self.task_type == "convert":
                self._run_conversion()
            self.signals.finished.emit()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Batch worker error:\n{tb}")
            self.signals.error.emit(f"{str(e)}\n\nCheck logs for details.")

    def _run_conversion(self):
        from app.services.batch_service import BatchService
        from pathlib import Path
        import time

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
        output_dir = Path(self.kwargs.get('output_dir', 'batch_output'))

        total = len(indices)
        outputs = []
        output_dir.mkdir(exist_ok=True)

        def log_cb(msg):
            self.signals.progress.emit(msg)

        def stop_cb():
            return self.isInterruptionRequested()

        start_time = time.time()

        for i, idx in enumerate(indices):
            # Check stop
            if self.isInterruptionRequested():
                log_cb("Batch processing stopped.")
                break

            # Check pause
            self._wait_if_paused()
            if self.isInterruptionRequested():
                log_cb("Batch processing stopped.")
                break

            # ETA calculation
            elapsed = time.time() - start_time
            if i > 0:
                avg_per_chapter = elapsed / i
                remaining = avg_per_chapter * (total - i)
                mins, secs = divmod(int(remaining), 60)
                eta_str = f" — ETA: ~{mins}m {secs}s" if mins else f" — ETA: ~{secs}s"
            else:
                eta_str = ""

            self.signals.status.emit(
                f"Processing Chapter {idx+1} ({i+1}/{total}){eta_str}"
            )
            self.signals.progress_val.emit(int((i / total) * 100))

            text = loader.get_chapter_content(idx)
            if not text:
                continue

            out_file = output_dir / f"ch_{idx+1}{output_ext}"
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
            BatchService.merge_audios(outputs, str(output_dir / f"full_book{output_ext}"))

        self.signals.progress_val.emit(100)


# ── Voice Encoding Worker ──────────────────────────────────────────────

class EncodeThread(QThread):
    """Background thread for encoding/saving a cloned voice reference."""
    finished = pyqtSignal(str)    # voice name
    error = pyqtSignal(str)

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
            logger.error(f"Voice encoding failed: {e}", exc_info=True)
            self.error.emit(str(e))


# ── Whisper Transcription Worker ───────────────────────────────────────

class TranscribeThread(QThread):
    """Background thread for Whisper audio transcription."""
    finished = pyqtSignal(str)    # transcribed text
    error = pyqtSignal(str)

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
            logger.error(f"Transcription failed: {e}", exc_info=True)
            self.error.emit(str(e))
