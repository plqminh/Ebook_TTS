from PyQt6.QtCore import QObject, pyqtSignal, QThread, QUrl, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from pathlib import Path
import threading
import time


# Dedicated background thread that continuously generates upcoming sentences
class GeneratorThread(QThread):
    """Generates audio for sentences in order, always working ahead of playback."""
    generated = pyqtSignal(int, str)  # index, file_path
    gen_error = pyqtSignal(int, str)  # index, error_msg

    def __init__(self, tts_service):
        super().__init__()
        self.tts = tts_service
        self.sentences = []
        self.voice_id = ""
        self._next_to_gen = 0   # Next sentence index to generate
        self._stop_flag = False
        self._wake = threading.Event()

    def setup(self, sentences, voice_id):
        self.sentences = sentences
        self.voice_id = voice_id
        self._next_to_gen = 0
        self._stop_flag = False

    def request_stop(self):
        self._stop_flag = True
        self._wake.set()

    def wake(self):
        """Signal the thread to start/resume generating."""
        self._wake.set()

    def skip_to(self, index):
        """Jump generation cursor to a specific index."""
        self._next_to_gen = index
        self._wake.set()

    def run(self):
        import asyncio
        while not self._stop_flag:
            # Wait until woken up
            self._wake.wait()
            self._wake.clear()

            # Generate sentences ahead (up to 3 ahead of what's needed)
            while not self._stop_flag and self._next_to_gen < len(self.sentences):
                idx = self._next_to_gen
                text = self.sentences[idx]
                self._next_to_gen += 1

                try:
                    out_path = Path("temp_audio") / f"sentence_{idx}.mp3"
                    out_path.parent.mkdir(exist_ok=True)

                    # Decide engine
                    if self.voice_id.startswith("vieneu"):
                        engine = "vieneu"
                    elif "|" in self.voice_id:
                        engine = "google"
                    else:
                        engine = "edge"

                    # Generate (synchronous call, runs in this thread)
                    actual_path = asyncio.run(self.tts.generate_audio_file(
                        text=text,
                        voice=self.voice_id,
                        output_path=str(out_path),
                        engine=engine
                    ))
                    self.generated.emit(idx, actual_path)
                except Exception as e:
                    self.gen_error.emit(idx, str(e))

                if self._stop_flag:
                    break

            # All done or stopped — wait for next wake
        

class PlaybackManager(QObject):
    sig_sentence_changed = pyqtSignal(int, str) # index, text
    sig_playback_finished = pyqtSignal()
    sig_status = pyqtSignal(str)
    
    def __init__(self, tts_service):
        super().__init__()
        self.tts_service = tts_service
        self.sentences = []
        self.current_index = 0
        self.is_playing = False
        self.voice_id = "vi" # Default
        
        # Audio Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        
        self.audio_cache = {} # index -> path
        
        self.retry_count = 0
        self.MAX_RETRIES = 3

        # Background generator thread
        self._gen_thread = GeneratorThread(tts_service)
        self._gen_thread.generated.connect(self._on_audio_ready)
        self._gen_thread.gen_error.connect(self._on_gen_error)
        
    def reset(self, text):
        # Split by paragraphs (newlines)
        raw = text.replace('\r\n', '\n').replace('\r', '\n')
        self.sentences = [s.strip() for s in raw.split('\n') if s.strip()]
                
        self.current_index = 0
        self.is_playing = False
        self.retry_count = 0
        self.player.stop()
        self.audio_cache.clear()

        # Stop old generator
        if self._gen_thread.isRunning():
            self._gen_thread.request_stop()
            self._gen_thread.wait(3000)

        self.sig_status.emit(f"Ready. {len(self.sentences)} sentences.")

    def play(self):
        if not self.sentences: return
        self.is_playing = True

        # Start background generation from current position
        self._gen_thread.setup(self.sentences, self.voice_id)
        self._gen_thread.skip_to(self.current_index)
        if not self._gen_thread.isRunning():
            self._gen_thread.start()
        self._gen_thread.wake()

        self._try_play_current()

    def pause(self):
        self.is_playing = False
        self.player.pause()
        self.sig_status.emit("Paused")

    def stop(self):
        self.is_playing = False
        self.player.stop()
        self.current_index = 0
        self.retry_count = 0
        self.sig_status.emit("Stopped")

    def set_voice(self, voice_id):
        self.voice_id = voice_id
        self.audio_cache.clear()

    def _try_play_current(self):
        """Play current sentence if audio is ready, otherwise wait."""
        if not self.is_playing: return
        if self.current_index >= len(self.sentences):
            self.sig_playback_finished.emit()
            self.stop()
            return

        if self.current_index in self.audio_cache:
            self.retry_count = 0
            self.play_audio(self.audio_cache[self.current_index])
        else:
            self.sig_status.emit(f"Generating sentence {self.current_index+1}...")

    def _on_audio_ready(self, index, path):
        """Called by generator thread when a sentence's audio is ready."""
        self.audio_cache[index] = path
        
        # If this is what we're waiting for, play it
        if index == self.current_index and self.is_playing:
            self.retry_count = 0
            self.play_audio(path)

    def _on_gen_error(self, index, err):
        """Called by generator thread when generation fails."""
        if not self.is_playing: return
        
        if index == self.current_index:
            self.retry_count += 1
            print(f"Gen Error (Retry {self.retry_count}): {err}")
            
            if self.retry_count >= self.MAX_RETRIES:
                # Skip this sentence
                self.sig_status.emit(f"Skipping sentence {self.current_index+1}: {err}")
                self.current_index += 1
                self.retry_count = 0
                QTimer.singleShot(100, self._try_play_current)

    def play_audio(self, path):
        abs_path = str(Path(path).resolve())
        self.player.setSource(QUrl.fromLocalFile(abs_path))
        self.player.play()
        self.sig_sentence_changed.emit(self.current_index, self.sentences[self.current_index])
        self.sig_status.emit(f"Playing {self.current_index+1}/{len(self.sentences)}")

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_playing:
                self.current_index += 1
                self._try_play_current()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
             self.sig_status.emit("Media Error: Invalid File. Skipping.")
             if self.is_playing:
                 self.current_index += 1
                 self._try_play_current()
