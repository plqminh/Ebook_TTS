"""
Batch Service — Convert book chapters to audio files.
"""
import os
import time
import random
import asyncio
import subprocess
from pathlib import Path

try:
    from app.libs.utils.normalize_text import normalize_text
except ImportError:
    normalize_text = lambda x: x


class BatchService:
    """Batch-convert text chapters to audio using Edge, Google, or VieNeu TTS."""

    _vieneu_instance = None

    @classmethod
    def _get_vieneu(cls):
        """Lazy-init shared Vieneu instance for batch processing."""
        if cls._vieneu_instance is None:
            print("Loading VieNeu-TTS SDK for batch processing...")
            from vieneu import Vieneu
            cls._vieneu_instance = Vieneu()
            print("VieNeu-TTS SDK loaded.")
        return cls._vieneu_instance

    # ── Text Chunking ──────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(text):
        """Split text into sentence-level chunks for TTS processing."""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        safe = text.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|")
        safe = safe.replace("\n", "|")
        return [c.strip() for c in safe.split("|") if c.strip()]

    # ── Main Conversion ────────────────────────────────────────────────

    @staticmethod
    def convert_chapter(
        text, model_path, ref_path, output_path,
        progress_callback=print, check_stop_callback=None,
        engine="vieneu", voice=None,
    ):
        """Convert a chapter's text to a single audio file."""
        if check_stop_callback and check_stop_callback():
            return

        import soundfile as sf
        import numpy as np

        progress_callback(f"Converting chapter to {output_path}...")
        chunks = BatchService._chunk_text(normalize_text(text))
        progress_callback(f"Split into {len(chunks)} chunks.")

        temp_dir = Path(output_path).parent / "temp_chunks" / Path(output_path).stem
        temp_dir.mkdir(parents=True, exist_ok=True)

        if engine in ("edge", "google"):
            all_waves, sr = BatchService._convert_cloud(
                chunks, voice, engine, temp_dir, progress_callback, check_stop_callback
            )
        else:
            all_waves, sr = BatchService._convert_vieneu(
                chunks, voice, ref_path, temp_dir, progress_callback, check_stop_callback
            )

        # Concatenate and save
        if all_waves:
            final_wav = np.concatenate(all_waves)
            sf.write(output_path, final_wav, sr)
            progress_callback(f"Saved: {output_path}")
        else:
            progress_callback("No audio generated.")

    # ── Edge / Google Branch ───────────────────────────────────────────

    @staticmethod
    def _convert_cloud(chunks, voice, engine, temp_dir, progress_cb, stop_cb):
        """Generate audio using Edge TTS or Google TTS (cloud-based)."""
        import soundfile as sf
        import numpy as np
        from app.services.tts_service import TTSService

        def run_sync(coro):
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)

        all_waves = []
        sample_rate = 24000
        max_retries = 3

        for i, chunk in enumerate(chunks):
            if stop_cb and stop_cb():
                progress_cb("Conversion stopped by user.")
                return all_waves, sample_rate

            progress_cb(f"Processing chunk {i+1}/{len(chunks)}: {chunk[:40]}...")
            chunk_path = temp_dir / f"chunk_{i}.wav"

            for attempt in range(max_retries):
                try:
                    run_sync(TTSService.generate_audio_file(chunk, voice, str(chunk_path), engine=engine))
                    data, sample_rate = sf.read(str(chunk_path))
                    all_waves.append(data)
                    all_waves.append(np.zeros(int(sample_rate * 0.3)))  # 0.3s silence
                    break
                except Exception as e:
                    print(f"Error chunk {i} (attempt {attempt+1}): {e}")
                    if attempt < max_retries - 1:
                        time.sleep(1 + random.random())

        return all_waves, sample_rate

    # ── VieNeu Branch ──────────────────────────────────────────────────

    @staticmethod
    def _convert_vieneu(chunks, voice, ref_path, temp_dir, progress_cb, stop_cb):
        """Generate audio using VieNeu SDK (local GGUF model)."""
        import soundfile as sf
        import numpy as np

        tts = BatchService._get_vieneu()
        sample_rate = 24000

        # Resolve voice
        voice_data = None
        if voice and voice.startswith("vieneu_preset:"):
            preset_id = voice.split(":", 1)[1]
            try:
                voice_data = tts.get_preset_voice(preset_id)
                print(f"Using preset voice: {preset_id}")
            except Exception as e:
                print(f"Warning: preset voice '{preset_id}' not found: {e}")

        # Resolve reference audio (for voice cloning)
        ref_text = ""
        use_ref = ref_path and os.path.exists(ref_path) and voice_data is None
        if use_ref:
            txt_file = Path(ref_path).with_suffix(".txt")
            if txt_file.exists():
                try:
                    ref_text = txt_file.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

        all_waves = []
        for i, chunk in enumerate(chunks):
            if stop_cb and stop_cb():
                progress_cb("Conversion stopped by user.")
                return all_waves, sample_rate

            progress_cb(f"Processing chunk {i+1}/{len(chunks)}: {chunk[:40]}...")

            try:
                if voice_data is not None:
                    audio = tts.infer(text=chunk, voice=voice_data)
                elif use_ref:
                    audio = tts.infer(text=chunk, ref_audio=ref_path, ref_text=ref_text)
                else:
                    audio = tts.infer(text=chunk)

                chunk_path = temp_dir / f"chunk_{i}.wav"
                tts.save(audio, str(chunk_path))

                wav_data, sr = sf.read(str(chunk_path))
                all_waves.append(wav_data)
                all_waves.append(np.zeros(int(sr * 0.3)))  # 0.3s silence
                sample_rate = sr
            except Exception as e:
                print(f"Error chunk {i}: {e}")

        return all_waves, sample_rate

    # ── Merge ──────────────────────────────────────────────────────────

    @staticmethod
    def merge_audios(file_list, output_path):
        """Merge multiple audio files into one MP3."""
        try:
            from pydub import AudioSegment
            combined = AudioSegment.empty()
            for f in file_list:
                combined += AudioSegment.from_file(f)
            combined.export(output_path, format="mp3")
            return
        except ImportError:
            pass

        # Fallback: FFmpeg concat
        list_file = Path(output_path).parent / "files.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for p in file_list:
                f.write(f"file '{Path(p).resolve().as_posix()}'\n")
        subprocess.check_call([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(output_path), "-y"
        ])
        os.remove(list_file)
