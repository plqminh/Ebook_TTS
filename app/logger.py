"""
Centralized logging for the Ebook TTS application.

Usage:
    from app.logger import logger
    logger.info("Something happened")
    logger.error("Something went wrong", exc_info=True)
"""
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(name="ebook_tts", log_file="ebook_tts.log"):
    """Configure and return the application logger."""
    log = logging.getLogger(name)
    if log.handlers:
        return log  # Already configured

    log.setLevel(logging.DEBUG)

    # Console handler — INFO and above
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    log.addHandler(console)

    # File handler — DEBUG and above, rotating 5 MB × 3 backups
    try:
        fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3,
                                 encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        log.addHandler(fh)
    except Exception:
        log.warning("Could not create log file handler, logging to console only.")

    return log


logger = setup_logger()
