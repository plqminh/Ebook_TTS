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
    """Batch-convert text chapters to audio using Edge, Google, or OmniVoice TTS."""

    _omnivoice_instance = None

    @classmethod
    def _get_omnivoice(cls):
        """Lazy-init shared OmniVoice instance for batch processing."""
        if cls._omnivoice_instance is None:
            import torch
            from omnivoice import OmniVoice

            use_gpu = torch.cuda.is_available()
            device = "cuda:0" if use_gpu else "cpu"
            dtype = torch.float16 if use_gpu else torch.float32

            print(f"Loading OmniVoice for batch (GPU={use_gpu})...")
            cls._omnivoice_instance = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice",
                device_map=device,
                dtype=dtype,
            )
            print("OmniVoice loaded.")
        return cls._omnivoice_instance

    # ── Text Chunking ──────────────────────────────────────────────────

    @staticmethod
    def _chunk_text(text, engine="edge"):
        """Split text into paragraphs for batch processing."""
        import re
        # Split by one or more newlines to extract paragraphs
        paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
        return paragraphs

    # ── Main Conversion ────────────────────────────────────────────────

    @staticmethod
    def convert_chapter(
        text, model_path, ref_path, output_path,
        progress_callback=print, check_stop_callback=None,
        engine="omnivoice", voice=None,
        silence_gap=0.0, max_retries=3, temperature=1.0,
        concurrent_chunks=3, voice_description=None,
    ):
        """Convert a chapter's text to a single audio file."""
        if check_stop_callback and check_stop_callback():
            return

        import soundfile as sf
        import numpy as np

        progress_callback(f"Converting chapter to {output_path}...")
        chunks = BatchService._chunk_text(normalize_text(text), engine=engine)
        progress_callback(f"Split into {len(chunks)} chunks.")

        temp_dir = Path(output_path).parent / "temp_chunks" / Path(output_path).stem
        temp_dir.mkdir(parents=True, exist_ok=True)

        if engine in ("edge", "google"):
            all_waves, sr = BatchService._convert_cloud(
                chunks, voice, engine, temp_dir, progress_callback, check_stop_callback,
                silence_gap=silence_gap, max_retries=max_retries, concurrent_chunks=concurrent_chunks
            )
        else:
            all_waves, sr = BatchService._convert_omnivoice(
                chunks, voice, ref_path, temp_dir, progress_callback, check_stop_callback,
                silence_gap=silence_gap, voice_description=voice_description,
                concurrent_chunks=concurrent_chunks,
            )

        # Concatenate and save
        if all_waves:
            final_wav = np.concatenate(all_waves)
            
            if str(output_path).lower().endswith(".mp3"):
                temp_wav = str(output_path)[:-4] + "_temp.wav"
                sf.write(temp_wav, final_wav, sr)
                try:
                    from pydub import AudioSegment
                    audio = AudioSegment.from_wav(temp_wav)
                    audio.export(output_path, format="mp3")
                except Exception as e:
                    progress_callback(f"MP3 conversion failed, saving as WAV: {e}")
                    sf.write(str(output_path)[:-4] + ".wav", final_wav, sr)
                finally:
                    if os.path.exists(temp_wav):
                        os.remove(temp_wav)
            else:
                sf.write(output_path, final_wav, sr)
                
            progress_callback(f"Saved: {output_path}")
        else:
            progress_callback("No audio generated.")

    # ── Edge / Google Branch ───────────────────────────────────────────

    @staticmethod
    def _convert_cloud(chunks, voice, engine, temp_dir, progress_cb, stop_cb,
                       silence_gap=0.0, max_retries=3, concurrent_chunks=3):
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

        sample_rate = 24000
        results = [None] * len(chunks)

        async def process_chunk(i, chunk, sem):
            async with sem:
                if stop_cb and stop_cb():
                    return i, None

                progress_cb(f"Processing chunk {i+1}/{len(chunks)}: {chunk[:40]}...")
                chunk_path = temp_dir / f"chunk_{i}.wav"

                for attempt in range(max_retries):
                    try:
                        await TTSService.generate_audio_file(chunk, voice, str(chunk_path), engine=engine)
                        data, sr = sf.read(str(chunk_path))
                        # Return tuple: (index, data, sample_rate)
                        return i, (data, sr)
                    except Exception as e:
                        print(f"Error chunk {i} (attempt {attempt+1}): {e}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1 + random.random())
                
                # Failed permanently
                return i, None

        async def run_all():
            sem = asyncio.Semaphore(concurrent_chunks)
            tasks = [process_chunk(i, chunk, sem) for i, chunk in enumerate(chunks)]
            return await asyncio.gather(*tasks)

        # Run the concurrent batch
        gathered_results = run_sync(run_all())

        all_waves = []
        
        # Check if stopped during processing
        if stop_cb and stop_cb():
            progress_cb("Conversion stopped by user.")
            return [], sample_rate
            
        # Reassemble in order
        for i, res in sorted(gathered_results, key=lambda x: x[0]):
            if res is not None:
                data, sr = res
                sample_rate = sr
                all_waves.append(data)
                if silence_gap > 0:
                    all_waves.append(np.zeros(int(sample_rate * silence_gap)))

        return all_waves, sample_rate



    # ── OmniVoice Branch ────────────────────────────────────────────

    @staticmethod
    def _convert_omnivoice(chunks, voice, ref_path, temp_dir, progress_cb, stop_cb,
                           silence_gap=0.0, voice_description=None, concurrent_chunks=1):
        """Generate audio using OmniVoice (HuggingFace model)."""
        import soundfile as sf
        import numpy as np

        model = BatchService._get_omnivoice()
        sample_rate = 24000

        # Resolve reference audio for voice cloning
        ref_text = ""
        use_ref = (voice == "omnivoice_custom" and ref_path
                   and os.path.exists(ref_path))
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
                return [], sample_rate

            progress_cb(f"Processing chunk {i+1}/{len(chunks)}: {chunk[:40]}...")

            try:
                from app.services.tts_service import TTSService
                with TTSService._omnivoice_lock:
                    synth_kwargs = {"text": chunk}

                    if use_ref:
                        synth_kwargs["ref_audio"] = ref_path
                        if ref_text:
                            synth_kwargs["ref_text"] = ref_text
                    elif voice == "omnivoice_design" and voice_description:
                        synth_kwargs["instruct"] = voice_description
                    # else: random voice (no extra args)

                    audios = model.generate(**synth_kwargs)

                chunk_path = temp_dir / f"chunk_{i}.wav"
                with open(str(chunk_path), "wb") as f:
                    sf.write(f, audios[0], model.sampling_rate, format="WAV")

                wav_data, sr = sf.read(str(chunk_path))
                all_waves.append(wav_data)
                if silence_gap > 0:
                    all_waves.append(np.zeros(int(sr * silence_gap)))
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
