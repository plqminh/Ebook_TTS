"""
Ebook TTS Player — Application Launcher.

Thin entry point that handles DLL pre-loading, creates the QApplication,
applies the theme, and launches the MainWindow.
"""
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
        from PyQt6.QtWidgets import QApplication
        import qdarktheme

        from app.main_window import MainWindow

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
