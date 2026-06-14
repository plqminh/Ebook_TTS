"""
TTS Service — Multi-engine text-to-speech with Edge, Google, and OmniVoice.
"""
import os
import json
import asyncio
import threading
from pathlib import Path

import edge_tts
from gtts import gTTS


class TTSService:
    """Provides TTS generation across multiple engines (Edge, Google, OmniVoice)."""

    PRONUNCIATION_DICT_FILE = "pronunciation_dict.json"
    CUSTOM_VOICES_FILE = "assets/ref_voices/custom_voices.json"

    _omnivoice_instance = None
    _omnivoice_lock = threading.Lock()  # PyTorch models are NOT thread-safe

    # ── Whisper (faster-whisper) ──────────────────────────────────────
    WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3"]
    _whisper_instance = None
    _whisper_model_size = None
    _whisper_lock = threading.Lock()

    # ── Voice Catalog ──────────────────────────────────────────────────

    @staticmethod
    def get_voices(engine="edge") -> list:
        """Return available voices for the given engine."""
        if engine == "edge":
            return [
                {"name": "Vietnamese (Northern - HoaiMy)", "id": "vi-VN-HoaiMyNeural"},
                {"name": "Vietnamese (Southern - NamMinh)", "id": "vi-VN-NamMinhNeural"},
                {"name": "Multilingual (Male - Andrew)",    "id": "en-US-AndrewMultilingualNeural"},
                {"name": "Multilingual (Female - Ava)",     "id": "en-US-AvaMultilingualNeural"},
            ]
        elif engine == "google":
            return [
                {"name": "Vietnamese (Standard)", "id": "vi|com.vn"},
                {"name": "Vietnamese (Global)",   "id": "vi|com"},
                {"name": "Vietnamese (France)",   "id": "vi|fr"},
            ]

        elif engine == "omnivoice":
            voices = [
                {"name": "OmniVoice: Random Voice",    "id": "omnivoice_random"},
                {"name": "OmniVoice: Voice Design",    "id": "omnivoice_design"},
                {"name": "OmniVoice: Custom Reference", "id": "omnivoice_custom"},
            ]
            
            # Allow using custom cloned voices with OmniVoice
            for name in TTSService.get_custom_voice_names():
                # name is "custom_MyVoice", strip the prefix to match the filename
                clean_name = name.replace("custom_", "", 1)
                voices.append({"name": f"OmniVoice: Clone — {clean_name}", "id": f"omnivoice_clone:{clean_name}"})
                
            return voices
        return []

    # ── OmniVoice Engine ───────────────────────────────────────────────

    @staticmethod
    def _get_omnivoice():
        """Lazy-init singleton OmniVoice instance (HuggingFace model)."""
        if TTSService._omnivoice_instance is None:
            import torch
            from omnivoice import OmniVoice

            use_gpu = torch.cuda.is_available()
            device = "cuda:0" if use_gpu else "cpu"
            dtype = torch.float16 if use_gpu else torch.float32

            TTSService._omnivoice_instance = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice",
                device_map=device,
                dtype=dtype,
            )
            device_label = "GPU" if use_gpu else "CPU"
            print(f"OmniVoice loaded successfully ({device_label}, {dtype}).")
        return TTSService._omnivoice_instance

    @staticmethod
    def _run_omnivoice(text, output_path, voice_id=None, ref_path=None,
                       voice_description=None):
        """Run OmniVoice synthesis (thread-safe via lock)."""
        import soundfile as sf

        with TTSService._omnivoice_lock:
            model = TTSService._get_omnivoice()

            kwargs = {"text": text}

            # Voice Cloning mode: from user's custom clone library
            if voice_id and voice_id.startswith("omnivoice_clone:"):
                name = voice_id.split(":", 1)[1]
                ref_dir = Path("assets/ref_voices")
                # Find matching audio file (wav, mp3, etc)
                possible_files = [f for f in ref_dir.iterdir() if f.stem == name and f.suffix.lower() in [".wav", ".mp3", ".flac", ".m4a"]]
                if possible_files:
                    audio_file = possible_files[0]
                    kwargs["ref_audio"] = str(audio_file)
                    ref_txt_file = audio_file.with_suffix(".txt")
                    if ref_txt_file.exists():
                        try:
                            kwargs["ref_text"] = ref_txt_file.read_text(encoding="utf-8").strip()
                        except Exception:
                            pass

            # Voice Cloning mode: explicit reference audio + text (Batch Tab)
            elif voice_id == "omnivoice_custom" and ref_path and os.path.exists(ref_path):
                kwargs["ref_audio"] = ref_path
                # Load ref text from companion .txt file if available
                ref_txt_file = Path(ref_path).with_suffix(".txt")
                if ref_txt_file.exists():
                    try:
                        kwargs["ref_text"] = ref_txt_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

            # Voice Design mode: natural language description
            elif voice_id == "omnivoice_design" and voice_description:
                kwargs["instruct"] = voice_description

            # Random Voice mode: no extra args needed
            # (omnivoice_random or fallback)

            audios = model.generate(**kwargs)
            with open(output_path, "wb") as f:
                sf.write(f, audios[0], model.sampling_rate, format="WAV")

    # ── Whisper Transcription (faster-whisper) ─────────────────────────

    @staticmethod
    def _get_whisper(model_size="base"):
        """Lazy-init singleton faster-whisper model. Reloads if model size changed."""
        with TTSService._whisper_lock:
            if (TTSService._whisper_instance is None
                    or TTSService._whisper_model_size != model_size):
                from faster_whisper import WhisperModel
                import torch

                use_gpu = torch.cuda.is_available()
                device = "cuda" if use_gpu else "cpu"
                compute_type = "float16" if use_gpu else "int8"

                print(f"Loading Whisper model '{model_size}' on {device} ({compute_type})...")
                TTSService._whisper_instance = WhisperModel(
                    model_size, device=device, compute_type=compute_type
                )
                TTSService._whisper_model_size = model_size
                print(f"Whisper '{model_size}' loaded successfully.")

            return TTSService._whisper_instance

    @staticmethod
    def transcribe_audio(audio_path: str, model_size: str = "base",
                         language: str = "vi") -> str:
        """
        Transcribe an audio file using faster-whisper.
        Returns the full transcription text.
        """
        model = TTSService._get_whisper(model_size)
        segments, info = model.transcribe(
            audio_path, language=language, beam_size=5
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip()

    # ── Custom Voice Management ────────────────────────────────────────

    @staticmethod
    def _load_custom_voices_json() -> dict:
        """Load the custom_voices.json file."""
        path = Path(TTSService.CUSTOM_VOICES_FILE)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"presets": {}}

    @staticmethod
    def _save_custom_voices_json(data: dict):
        """Save the custom_voices.json file."""
        path = Path(TTSService.CUSTOM_VOICES_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


    @staticmethod
    def get_custom_voice_names() -> list:
        """Return just the display names of custom voices."""
        data = TTSService._load_custom_voices_json()
        return list(data.get("presets", {}).keys())

    @staticmethod
    def encode_and_save_voice(name: str, audio_path: str, ref_text: str):
        """
        Save custom voice preset for OmniVoice cloning.
        """
        import shutil
        key = f"custom_{name}"

        # Copy audio file to assets/ref_voices/
        ref_dir = Path("assets/ref_voices")
        ref_dir.mkdir(parents=True, exist_ok=True)
        src = Path(audio_path)
        dest = ref_dir / f"{name}{src.suffix}"
        shutil.copy2(str(src), str(dest))

        # Save ref text alongside audio
        dest.with_suffix(".txt").write_text(ref_text, encoding="utf-8")

        # Update custom_voices.json
        data = TTSService._load_custom_voices_json()
        data["presets"][key] = {
            "text": ref_text,
            "description": f"OmniVoice: Clone — {name}",
        }
        TTSService._save_custom_voices_json(data)

    @staticmethod
    def remove_custom_voice(name: str):
        """Remove a custom voice from the JSON and delete its files."""
        key = f"custom_{name}"

        # Remove from JSON
        data = TTSService._load_custom_voices_json()
        data["presets"].pop(key, None)
        TTSService._save_custom_voices_json(data)

        # Delete files
        ref_dir = Path("assets/ref_voices")
        for ext in (".wav", ".mp3", ".txt", ".pt"):
            f = ref_dir / f"{name}{ext}"
            if f.exists():
                f.unlink()

    # ── Pronunciation Dictionary ───────────────────────────────────────

    @staticmethod
    def load_dictionary():
        if os.path.exists(TTSService.PRONUNCIATION_DICT_FILE):
            try:
                with open(TTSService.PRONUNCIATION_DICT_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @staticmethod
    def update_dictionary(new_dict):
        with open(TTSService.PRONUNCIATION_DICT_FILE, "w", encoding="utf-8") as f:
            json.dump(new_dict, f, ensure_ascii=False, indent=4)

    @staticmethod
    def _apply_dictionary(text: str) -> str:
        dictionary = TTSService.load_dictionary()
        if not dictionary:
            return text
        for word in sorted(dictionary, key=len, reverse=True):
            text = text.replace(word, dictionary[word])
        return text

    # ── Public API ─────────────────────────────────────────────────────

    @staticmethod
    async def generate_audio_file(
        text: str, voice: str, output_path: str,
        rate="+0%", pitch="+0Hz", volume="+0%",
        engine="edge", ref_path=None, temperature=1.0,
        **kwargs,
    ) -> str:
        """Generate a single audio file from text."""
        final_text = TTSService._apply_dictionary(text)

        if engine == "edge":
            comm = edge_tts.Communicate(final_text, voice, rate=rate, pitch=pitch, volume=volume)
            await comm.save(output_path)

        elif engine == "google":
            lang, tld = (voice.split("|") + ["com.vn"])[:2]
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: gTTS(text=final_text, lang=lang, tld=tld).save(output_path)
            )


        elif engine == "omnivoice":
            voice_description = kwargs.get("voice_description", None)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: TTSService._run_omnivoice(
                    final_text, output_path, voice, ref_path, voice_description
                )
            )

        return output_path

    @staticmethod
    async def stream_audio(text: str, voice: str, rate="+0%", pitch="+0Hz", volume="+0%", engine="edge"):
        """Stream audio chunks (Edge TTS only)."""
        final_text = TTSService._apply_dictionary(text)
        if engine == "edge":
            comm = edge_tts.Communicate(final_text, voice, rate=rate, pitch=pitch, volume=volume)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
