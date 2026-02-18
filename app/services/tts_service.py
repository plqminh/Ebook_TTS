"""
TTS Service — Multi-engine text-to-speech with VieNeu, Edge, and Google.
"""
import os
import json
import asyncio
import threading
from pathlib import Path

import edge_tts
from gtts import gTTS


class TTSService:
    """Provides TTS generation across multiple engines (Edge, Google, VieNeu)."""

    PRONUNCIATION_DICT_FILE = "pronunciation_dict.json"

    _vieneu_instance = None
    _vieneu_lock = threading.Lock()  # llama-cpp-python is NOT thread-safe

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
        elif engine == "vieneu":
            # Hardcoded preset voices — avoids initializing the heavy model at startup
            # (PyQt6 DLL search order conflicts with PyTorch's c10.dll)
            return [
                {"name": "VieNeu: Bình (nam miền Bắc)",  "id": "vieneu_preset:Binh"},
                {"name": "VieNeu: Tuyên (nam miền Bắc)", "id": "vieneu_preset:Tuyen"},
                {"name": "VieNeu: Vĩnh (nam miền Nam)",  "id": "vieneu_preset:Vinh"},
                {"name": "VieNeu: Đoan (nữ miền Nam)",   "id": "vieneu_preset:Doan"},
                {"name": "VieNeu: Ly (nữ miền Bắc)",     "id": "vieneu_preset:Ly"},
                {"name": "VieNeu: Ngọc (nữ miền Bắc)",   "id": "vieneu_preset:Ngoc"},
                {"name": "VieNeu: Custom Reference",      "id": "vieneu_custom"},
            ]
        return []

    # ── VieNeu Engine ──────────────────────────────────────────────────

    @staticmethod
    def _get_vieneu():
        """Lazy-init singleton Vieneu instance (0.3B GGUF on CPU)."""
        if TTSService._vieneu_instance is None:
            print("Loading VieNeu-TTS SDK (0.3B GGUF on CPU)...")
            from vieneu import Vieneu
            TTSService._vieneu_instance = Vieneu()
            print("VieNeu-TTS SDK loaded successfully.")
        return TTSService._vieneu_instance

    @staticmethod
    def _run_vieneu(text, output_path, voice_id=None, ref_path=None):
        """Run VieNeu synthesis (thread-safe via lock)."""
        with TTSService._vieneu_lock:
            tts = TTSService._get_vieneu()

            if voice_id and voice_id.startswith("vieneu_preset:"):
                preset_id = voice_id.split(":", 1)[1]
                voice_data = tts.get_preset_voice(preset_id)
                audio = tts.infer(text=text, voice=voice_data)
            elif ref_path and os.path.exists(ref_path):
                ref_text = ""
                ref_txt_file = Path(ref_path).with_suffix(".txt")
                if ref_txt_file.exists():
                    try:
                        ref_text = ref_txt_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass
                audio = tts.infer(text=text, ref_audio=ref_path, ref_text=ref_text)
            else:
                audio = tts.infer(text=text)

            tts.save(audio, output_path)

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
        engine="edge", ref_path=None,
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

        elif engine == "vieneu":
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: TTSService._run_vieneu(final_text, output_path, voice, ref_path)
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
