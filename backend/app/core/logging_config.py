"""Logging configuration for ChronoGraph AI."""

import logging
import logging.handlers
import os
from app.core.config import settings


def setup_logging() -> None:
    """Configure root logger with console + rotating file handlers."""
    os.makedirs(os.path.dirname(settings.log_file), exist_ok=True)

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(log_level)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    # Rotating file handler (10 MB × 5 backups)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError as exc:
        logging.warning("Could not open log file %s: %s", settings.log_file, exc)

