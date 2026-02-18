"""
VieNeu Downloader — Simplified setup using the vieneu pip SDK.
The SDK auto-downloads the 0.3B GGUF model on first initialization.
"""
import shutil
from pathlib import Path


class VieNeuDownloader:
    """Handles VieNeu-TTS SDK installation and reference voice setup."""

    BASE_DIR = Path(__file__).parent.parent.parent  # Project root
    REF_VOICES_DIR = BASE_DIR / "assets" / "ref_voices"

    @classmethod
    def is_setup_complete(cls):
        """Check if the vieneu SDK is installed."""
        try:
            import vieneu  # noqa: F401
            return True
        except ImportError:
            return False

    @classmethod
    def run_full_setup(cls, progress_callback=print):
        """Install vieneu SDK and trigger first model download."""
        try:
            # Step 1: Install SDK
            progress_callback("Checking vieneu SDK installation...")
            if not cls.is_setup_complete():
                progress_callback("Installing vieneu SDK via pip...")
                import subprocess, sys
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", "vieneu",
                    "--extra-index-url",
                    "https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/",
                ])
                progress_callback("vieneu SDK installed.")
            else:
                progress_callback("vieneu SDK already installed.")

            # Step 2: Warmup — triggers model auto-download
            progress_callback("Initializing VieNeu-TTS (downloading model if needed)...")
            from vieneu import Vieneu
            Vieneu()
            progress_callback("VieNeu-TTS model loaded.")

            # Step 3: Copy sample reference voices
            cls._setup_ref_voices(progress_callback)

            progress_callback("Setup complete!")
            return True

        except Exception as e:
            progress_callback(f"Error: {e}")
            raise

    @classmethod
    def _setup_ref_voices(cls, progress_callback=None):
        """Copy bundled reference voices to assets/ref_voices."""
        cls.REF_VOICES_DIR.mkdir(parents=True, exist_ok=True)

        count = 0
        legacy_samples = cls.BASE_DIR / "app" / "libs" / "VieNeu-TTS" / "sample"
        if legacy_samples.exists():
            for f in legacy_samples.glob("*.wav"):
                shutil.copy2(f, cls.REF_VOICES_DIR / f.name)
                count += 1
            for f in legacy_samples.glob("*.txt"):
                shutil.copy2(f, cls.REF_VOICES_DIR / f.name)

        if progress_callback:
            progress_callback(f"Installed {count} reference voices.")
