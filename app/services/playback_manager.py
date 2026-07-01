from PyQt6.QtCore import QObject, pyqtSignal, QThread, QUrl, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from pathlib import Path
import threading
import time
import shutil

from app.logger import logger


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
        self.temperature = 1.0
        self.rate = "+0%"
        self.pitch = "+0Hz"
        self._next_to_gen = 0   # Next sentence index to generate
        self._stop_flag = False
        self._wake = threading.Event()

    def setup(self, sentences, voice_id, temperature=1.0, rate="+0%", pitch="+0Hz"):
        self.sentences = sentences
        self.voice_id = voice_id
        self.temperature = temperature
        self.rate = rate
        self.pitch = pitch
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

            # Generate all sentences ahead
            while not self._stop_flag and self._next_to_gen < len(self.sentences):
                idx = self._next_to_gen
                text = self.sentences[idx]
                self._next_to_gen += 1

                try:
                    import uuid

                    # Decide engine
                    if self.voice_id.startswith("vieneu"):
                        engine = "vieneu"
                    elif self.voice_id.startswith("omnivoice"):
                        engine = "omnivoice"
                    elif "|" in self.voice_id:
                        engine = "google"
                    else:
                        engine = "edge"

                    # Use correct extension: Edge/Google produce MP3, others WAV
                    ext = ".mp3" if engine in ("edge", "google") else ".wav"
                    out_path = Path("temp_audio") / f"sentence_{idx}_{uuid.uuid4().hex[:8]}{ext}"
                    out_path.parent.mkdir(exist_ok=True)

                    # Generate (synchronous call, runs in this thread)
                    actual_path = asyncio.run(self.tts.generate_audio_file(
                        text=text,
                        voice=self.voice_id,
                        output_path=str(out_path),
                        engine=engine,
                        temperature=self.temperature,
                        rate=self.rate,
                        pitch=self.pitch,
                    ))

                    self.generated.emit(idx, actual_path)
                except Exception as e:
                    logger.error(f"Generation error for sentence {idx}: {e}")
                    self.gen_error.emit(idx, str(e))

                if self._stop_flag:
                    break

            # All done or stopped — wait for next wake


class PlaybackManager(QObject):
    sig_sentence_changed = pyqtSignal(int, str)  # index, text
    sig_playback_finished = pyqtSignal()
    sig_status = pyqtSignal(str)

    # No artificial gap between sentences since the SILENCE_PAD_MS
    # already provides a natural tiny pause.
    SENTENCE_GAP_MS = 0

    def __init__(self, tts_service):
        super().__init__()
        self.tts_service = tts_service
        self.sentences = []
        self.current_index = 0
        self.is_playing = False
        self.voice_id = "vi"  # Default
        self.temperature = 1.0
        self.rate = "+0%"
        self.pitch = "+0Hz"

        # Keep audio device awake using a silent loop player
        # This prevents Windows WASAPI initialization latency from clipping the first words
        self._silence_player = QMediaPlayer()
        self._silence_audio_out = QAudioOutput()
        self._silence_audio_out.setVolume(0.01) # Near zero volume
        self._silence_player.setAudioOutput(self._silence_audio_out)
        self._silence_player.setLoops(QMediaPlayer.Loops.Infinite)
        silence_path = str(Path("silence_loop.wav").resolve())
        self._silence_player.setSource(QUrl.fromLocalFile(silence_path))
        self._silence_player.play()

        # Double-buffered players for gapless playback
        self._players = []
        self._audio_outputs = []
        for i in range(2):
            player = QMediaPlayer()
            audio_out = QAudioOutput()
            player.setAudioOutput(audio_out)
            player.mediaStatusChanged.connect(
                lambda status, p=i: self._on_media_status(p, status)
            )
            self._players.append(player)
            self._audio_outputs.append(audio_out)

        self._active_player = 0   # Index of currently playing player (0 or 1)
        self._next_preloaded = False  # Whether the standby player has next sentence loaded
        self._standby_ready = False   # Whether standby media is fully loaded (LoadedMedia)

        # State flags for deferred playback (wait for LoadedMedia before play())
        self._waiting_for_active_load = False   # Active player: source set, waiting to play
        self._waiting_for_standby = False       # Standby player: EndOfMedia fired, waiting to swap

        self.audio_cache = {}  # index -> path

        self.retry_count = 0
        self.MAX_RETRIES = 3

        # Background generator thread
        self._gen_thread = GeneratorThread(tts_service)
        self._gen_thread.generated.connect(self._on_audio_ready)
        self._gen_thread.gen_error.connect(self._on_gen_error)

    @staticmethod
    def _split_sentences(text, voice_id="edge"):
        """Split text into engine-appropriate chunks for TTS."""
        from app.services.text_chunker import chunk_text, get_engine_from_voice_id
        engine = get_engine_from_voice_id(voice_id)
        return chunk_text(text, engine=engine)

    def reset(self, text):
        # Store raw text so we can re-chunk when voice changes
        self._last_text = text

        # Split into engine-appropriate chunks
        self.sentences = self._split_sentences(text, self.voice_id)

        self.current_index = 0
        self.is_playing = False
        self.retry_count = 0
        self._next_preloaded = False
        self._standby_ready = False
        self._waiting_for_active_load = False
        self._waiting_for_standby = False

        # Stop both players
        for p in self._players:
            p.stop()
            p.setSource(QUrl())

        self.audio_cache.clear()

        # Stop old generator
        if self._gen_thread.isRunning():
            self._gen_thread.request_stop()
            self._gen_thread.wait(3000)

        # Preload: start generating audio for upcoming sentences immediately
        self._gen_thread = GeneratorThread(self.tts_service)
        self._gen_thread.generated.connect(self._on_audio_ready)
        self._gen_thread.gen_error.connect(self._on_gen_error)
        self._gen_thread.setup(self.sentences, self.voice_id, self.temperature,
                               self.rate, self.pitch)
        self._gen_thread.start()
        self._gen_thread.wake()

        self.sig_status.emit(f"Ready. {len(self.sentences)} sentences. Preloading...")

    def play(self):
        if not self.sentences:
            return
        self.is_playing = True

        # Only restart generation if nothing is cached for current sentence
        if self.current_index not in self.audio_cache:
            self._gen_thread.skip_to(self.current_index)
            if not self._gen_thread.isRunning():
                self._gen_thread.setup(self.sentences, self.voice_id, self.temperature,
                                       self.rate, self.pitch)
                self._gen_thread.start()
            self._gen_thread.wake()

        self._try_play_current()

    def pause(self):
        self.is_playing = False
        self._players[self._active_player].pause()
        self.sig_status.emit("Paused")

    def stop(self):
        self.is_playing = False
        self._waiting_for_active_load = False
        self._waiting_for_standby = False
        for p in self._players:
            p.stop()
        self.current_index = 0
        self.retry_count = 0
        self._next_preloaded = False
        self._standby_ready = False
        self.sig_status.emit("Stopped")

    def set_voice(self, voice_id):
        from app.services.text_chunker import get_engine_from_voice_id

        old_engine = get_engine_from_voice_id(self.voice_id)
        new_engine = get_engine_from_voice_id(voice_id)
        self.voice_id = voice_id
        self.audio_cache.clear()
        self._next_preloaded = False
        self._standby_ready = False
        self._waiting_for_active_load = False
        self._waiting_for_standby = False

        # Re-chunk text if engine type changed (different max chunk sizes)
        if old_engine != new_engine and hasattr(self, '_last_text') and self._last_text:
            self.sentences = self._split_sentences(self._last_text, self.voice_id)
            self.current_index = 0

        # Stop both standby players (don't interrupt active playback mid-sentence)
        standby = 1 - self._active_player
        self._players[standby].stop()
        self._players[standby].setSource(QUrl())

        # Restart generator with new voice
        if self._gen_thread.isRunning():
            self._gen_thread.request_stop()
            self._gen_thread.wait(3000)

        if self.sentences:
            self._gen_thread = GeneratorThread(self.tts_service)
            self._gen_thread.generated.connect(self._on_audio_ready)
            self._gen_thread.gen_error.connect(self._on_gen_error)
            self._gen_thread.setup(self.sentences, self.voice_id, self.temperature,
                                   self.rate, self.pitch)
            self._gen_thread.start()
            self._gen_thread.wake()

    # ── Speed & Pitch ──────────────────────────────────────────────────

    def set_rate(self, rate_str):
        """Set TTS speaking rate, e.g. '+20%' or '-10%'."""
        self.rate = rate_str
        self.audio_cache.clear()
        self._restart_generator()

    def set_pitch(self, pitch_str):
        """Set TTS pitch offset, e.g. '+10Hz' or '-5Hz'."""
        self.pitch = pitch_str
        self.audio_cache.clear()
        self._restart_generator()

    def _restart_generator(self):
        """Restart the generator thread with current settings."""
        if self._gen_thread.isRunning():
            self._gen_thread.request_stop()
            self._gen_thread.wait(3000)
        if self.sentences:
            self._gen_thread = GeneratorThread(self.tts_service)
            self._gen_thread.generated.connect(self._on_audio_ready)
            self._gen_thread.gen_error.connect(self._on_gen_error)
            self._gen_thread.setup(self.sentences, self.voice_id, self.temperature,
                                   self.rate, self.pitch)
            self._gen_thread.start()
            self._gen_thread.skip_to(self.current_index)
            self._gen_thread.wake()

    # ── Sentence Navigation ────────────────────────────────────────────

    def skip_next(self):
        """Skip to the next sentence."""
        if self.current_index < len(self.sentences) - 1:
            self._players[self._active_player].stop()
            self.current_index += 1
            self._next_preloaded = False
            self._standby_ready = False
            self._waiting_for_active_load = False
            self._waiting_for_standby = False
            if self.is_playing:
                self._try_play_current()
            self.sig_sentence_changed.emit(
                self.current_index, self.sentences[self.current_index]
            )

    def skip_prev(self):
        """Skip to the previous sentence."""
        if self.current_index > 0:
            self._players[self._active_player].stop()
            self.current_index -= 1
            self._next_preloaded = False
            self._standby_ready = False
            self._waiting_for_active_load = False
            self._waiting_for_standby = False
            if self.is_playing:
                self._try_play_current()
            self.sig_sentence_changed.emit(
                self.current_index, self.sentences[self.current_index]
            )

    def set_position(self, sentence_index):
        """Jump to a specific sentence index (for resume)."""
        if 0 <= sentence_index < len(self.sentences):
            self.current_index = sentence_index
            self._next_preloaded = False
            self._standby_ready = False

    # ── Temp File Cleanup ──────────────────────────────────────────────

    @staticmethod
    def cleanup_temp_audio():
        """Delete all files in the temp_audio/ directory."""
        temp_dir = Path("temp_audio")
        if temp_dir.exists():
            count = 0
            for f in temp_dir.iterdir():
                if f.is_file():
                    try:
                        f.unlink()
                        count += 1
                    except Exception:
                        pass  # File may be in use
            logger.info(f"Cleaned up {count} temp audio files.")
            return count
        return 0

    # ── Graceful Shutdown ──────────────────────────────────────────────

    def shutdown(self):
        """Stop all playback and threads. Call on app close."""
        self.is_playing = False
        for p in self._players:
            p.stop()
        self._silence_player.stop()

        if self._gen_thread.isRunning():
            self._gen_thread.request_stop()
            self._gen_thread.wait(3000)
        logger.info("PlaybackManager shut down.")

    # ── Internal Playback Logic ────────────────────────────────────────

    def _try_play_current(self):
        """Play current sentence if audio is ready, otherwise wait for generator."""
        if not self.is_playing:
            return
        if self.current_index >= len(self.sentences):
            self.sig_playback_finished.emit()
            self.stop()
            return

        if self.current_index in self.audio_cache:
            self.retry_count = 0
            self._load_on_active(self.audio_cache[self.current_index])
        else:
            self.sig_status.emit(f"Generating sentence {self.current_index + 1}...")
            # _on_audio_ready will automatically start playback when ready

    def _load_on_active(self, path):
        """Load audio on the active player. Playback starts when LoadedMedia fires."""
        player = self._players[self._active_player]
        abs_path = str(Path(path).resolve())

        # Set source — do NOT call play() yet!
        # Playback will start from _on_media_status when LoadedMedia is received.
        player.stop()
        player.setSource(QUrl.fromLocalFile(abs_path))
        self._waiting_for_active_load = True

        self.sig_sentence_changed.emit(self.current_index, self.sentences[self.current_index])
        self.sig_status.emit(f"Loading {self.current_index + 1}/{len(self.sentences)}...")

    def _actually_play_active(self):
        """Called after the active player's media is confirmed loaded. Safe to play."""
        if not self.is_playing:
            return
        self._waiting_for_active_load = False

        player = self._players[self._active_player]
        player.setPosition(0)
        player.play()

        self.sig_status.emit(f"Playing {self.current_index + 1}/{len(self.sentences)}")

        # Preload next sentence on the standby player
        self._next_preloaded = False
        self._standby_ready = False
        self._try_preload_next()

    def _try_preload_next(self):
        """Preload the next sentence into the standby player if available."""
        next_idx = self.current_index + 1
        if next_idx < len(self.sentences) and next_idx in self.audio_cache:
            standby = 1 - self._active_player
            standby_player = self._players[standby]
            abs_path = str(Path(self.audio_cache[next_idx]).resolve())
            standby_player.stop()
            standby_player.setSource(QUrl.fromLocalFile(abs_path))
            self._next_preloaded = True
            self._standby_ready = False
            # _standby_ready will be set True when we receive LoadedMedia
            # for the standby player in _on_media_status

    def _on_audio_ready(self, index, path):
        """Called by generator thread when a sentence's audio is ready."""
        self.audio_cache[index] = path

        if not self.is_playing:
            return

        # If this is the current sentence and we're not actively playing, start it
        if index == self.current_index:
            active = self._players[self._active_player]
            state = active.playbackState()
            if state != QMediaPlayer.PlaybackState.PlayingState:
                self.retry_count = 0
                self._load_on_active(path)
            return

        # If this is the next sentence, preload it on standby player
        if index == self.current_index + 1 and not self._next_preloaded:
            self._try_preload_next()

    def _on_gen_error(self, index, err):
        """Called by generator thread when generation fails."""
        if not self.is_playing:
            return

        if index == self.current_index:
            self.retry_count += 1
            logger.warning(f"Gen Error (Retry {self.retry_count}): {err}")

            if self.retry_count >= self.MAX_RETRIES:
                # Skip this sentence
                self.sig_status.emit(f"Skipping sentence {self.current_index + 1}: {err}")
                self.current_index += 1
                self.retry_count = 0
                QTimer.singleShot(50, self._try_play_current)

    def _start_standby_playback(self):
        """Start playback on the standby player after it's confirmed loaded."""
        if not self.is_playing:
            return
        if self.current_index >= len(self.sentences):
            self.sig_playback_finished.emit()
            self.stop()
            return

        old_active = self._active_player
        self._active_player = 1 - self._active_player
        self._next_preloaded = False
        self._standby_ready = False
        self._waiting_for_standby = False

        # Seek to beginning to ensure nothing is clipped, then play
        new_player = self._players[self._active_player]
        new_player.setPosition(0)
        new_player.play()

        self.sig_sentence_changed.emit(
            self.current_index, self.sentences[self.current_index]
        )
        self.sig_status.emit(
            f"Playing {self.current_index + 1}/{len(self.sentences)}"
        )

        # Stop old player and preload next on it
        self._players[old_active].stop()
        self._players[old_active].setSource(QUrl())
        self._try_preload_next()

    def _on_media_status(self, player_idx, status):
        """Handle media status changes for either player."""

        # ── Active player: waiting for LoadedMedia to start playback ──
        if (player_idx == self._active_player
                and self._waiting_for_active_load
                and status in (QMediaPlayer.MediaStatus.LoadedMedia,
                               QMediaPlayer.MediaStatus.BufferedMedia)):
            self._actually_play_active()
            return

        # ── Standby player: track when it becomes ready ──
        standby_idx = 1 - self._active_player
        if player_idx == standby_idx and self._next_preloaded:
            if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                          QMediaPlayer.MediaStatus.BufferedMedia):
                self._standby_ready = True
                # If we were waiting for standby to become ready, start playback now
                if self._waiting_for_standby:
                    QTimer.singleShot(self.SENTENCE_GAP_MS, self._start_standby_playback)
                return

        # ── Only handle active player events below ──
        if player_idx != self._active_player:
            return

        # Guard against re-entrant calls during player swap
        if getattr(self, '_switching', False):
            return

        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.is_playing:
                self._switching = True
                self.current_index += 1

                # Swap players — if next is preloaded AND fully ready, play after gap
                if (self._next_preloaded and self._standby_ready
                        and self.current_index < len(self.sentences)):
                    QTimer.singleShot(self.SENTENCE_GAP_MS, self._start_standby_playback)
                elif self._next_preloaded and self.current_index < len(self.sentences):
                    # Source is set but not yet loaded — wait for it
                    self._waiting_for_standby = True
                    self.sig_status.emit(
                        f"Buffering sentence {self.current_index + 1}..."
                    )
                else:
                    # Fallback: no preload available, use normal path
                    self._try_play_current()

                self._switching = False

        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            logger.warning(f"Invalid media for sentence {self.current_index + 1}, retrying...")
            # Retry once by re-setting the source instead of immediately skipping
            if self.is_playing and self.current_index in self.audio_cache:
                self.retry_count += 1
                if self.retry_count < self.MAX_RETRIES:
                    path = self.audio_cache[self.current_index]
                    QTimer.singleShot(100, lambda: self._load_on_active(path))
                    return
            # Only skip after retries exhausted
            self.sig_status.emit(f"Skipping sentence {self.current_index + 1}: Invalid media")
            if self.is_playing:
                self.current_index += 1
                self.retry_count = 0
                self._next_preloaded = False
                self._standby_ready = False
                self._try_play_current()
