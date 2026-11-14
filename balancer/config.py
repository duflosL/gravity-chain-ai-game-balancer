"""Local application paths and supported model choices."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
DATABASE = Path(os.environ.get("GC_BALANCER_DB", str(RUNTIME / "analyses.sqlite3")))
DEMO = ROOT / "data" / "demo.csv"
MODEL_CHOICES = ("qwen3:8b", "qwen3:4b", "qwen3:1.7b")
LEVEL_COLORS = {"accent": "#e4ba70", "context": "#807d8b", "danger": "#e69184"}
STATUS_LABELS = {"pending": "En attente", "accepted": "Acceptée", "rejected": "Rejetée"}


def app_logger() -> logging.Logger:
    logger = logging.getLogger("gravity-chain")
    if not logger.handlers:
        RUNTIME.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            RUNTIME / "balancer.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
