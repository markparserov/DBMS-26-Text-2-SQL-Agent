#!/usr/bin/env python3
"""
Запуск только API (без Gradio и React). Для использования с tmux/отдельными процессами.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from src.api import app
from src.config import load_config

if __name__ == "__main__":
    cfg = load_config()
    uvicorn.run(
        app,
        host=cfg.get("api_host", "0.0.0.0"),
        port=int(cfg.get("api_port", 8000)),
    )
