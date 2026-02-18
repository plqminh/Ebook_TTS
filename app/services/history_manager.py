import json
import os
from pathlib import Path
from typing import Dict, Any

class HistoryManager:
    """
    Manages saving and loading of reading progress.
    """
    FILE = "reading_history.json"

    @staticmethod
    def load_history() -> Dict[str, Any]:
        if not os.path.exists(HistoryManager.FILE):
            return {}
        try:
            with open(HistoryManager.FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    @staticmethod
    def save_progress(file_path: str, chapter_idx: int):
        history = HistoryManager.load_history()
        # Key by filename or full path? Full path is safer for local app.
        key = str(Path(file_path).absolute())
        
        history[key] = {
            "chapter_index": chapter_idx,
            "last_read": str(os.path.getmtime(file_path)) if os.path.exists(file_path) else None
        }
        
        with open(HistoryManager.FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)

    @staticmethod
    def get_progress(file_path: str) -> int:
        history = HistoryManager.load_history()
        key = str(Path(file_path).absolute())
        if key in history:
            return history[key].get("chapter_index", 0)
        return 0
