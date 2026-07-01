import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.logger import logger


class HistoryManager:
    """
    Manages saving and loading of reading progress and recent files.
    """
    FILE = "reading_history.json"
    MAX_RECENT = 10

    @staticmethod
    def _load_raw() -> Dict[str, Any]:
        if not os.path.exists(HistoryManager.FILE):
            return {}
        try:
            with open(HistoryManager.FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            logger.warning("Could not load reading history, starting fresh.")
            return {}

    @staticmethod
    def _save_raw(data: Dict[str, Any]):
        try:
            with open(HistoryManager.FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save reading history: {e}")

    # ── Progress ───────────────────────────────────────────────────

    @staticmethod
    def save_progress(file_path: str, chapter_idx: int, sentence_idx: int = 0):
        """Save reading position (chapter + sentence) for a file."""
        history = HistoryManager._load_raw()
        key = str(Path(file_path).absolute())
        
        history[key] = {
            "chapter_index": chapter_idx,
            "sentence_index": sentence_idx,
            "last_read": str(os.path.getmtime(file_path)) if os.path.exists(file_path) else None
        }
        
        HistoryManager._save_raw(history)

    @staticmethod
    def get_progress(file_path: str) -> Dict[str, int]:
        """Return saved position: {'chapter_index': int, 'sentence_index': int}."""
        history = HistoryManager._load_raw()
        key = str(Path(file_path).absolute())
        entry = history.get(key, {})
        return {
            "chapter_index": entry.get("chapter_index", 0),
            "sentence_index": entry.get("sentence_index", 0),
        }

    # ── Recent Files ───────────────────────────────────────────────

    @staticmethod
    def get_recent_files() -> List[str]:
        """Return list of recently opened file paths (most recent first)."""
        history = HistoryManager._load_raw()
        # Sort by last_read timestamp descending
        items = []
        for path, data in history.items():
            ts = float(data.get("last_read", 0) or 0)
            items.append((path, ts))
        items.sort(key=lambda x: x[1], reverse=True)
        return [path for path, _ in items[:HistoryManager.MAX_RECENT]]
