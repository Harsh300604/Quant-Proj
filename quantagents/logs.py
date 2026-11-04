"""Logging setup: console + a file under the storage root, with secrets redacted."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from quantagents.env_secrets import RedactingFilter

_CONFIGURED = False


def setup_logging(log_dir: Path | None = None, name: str = "quantagents",
                  level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    root = logging.getLogger()
    if not _CONFIGURED:
        root.setLevel(level)
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.addFilter(RedactingFilter())
        root.addHandler(console)
        _CONFIGURED = True
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / f"{name}_{datetime.now():%Y%m%d}.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        fh.addFilter(RedactingFilter())
        root.addHandler(fh)
    for noisy in ("urllib3", "yfinance", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(name)
