#!/usr/bin/env python3
"""
Запуск объединённого сервера:
- API: /api/*
- Gradio: /gradio
- React (static): /
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gradio as gr
import uvicorn
from fastapi.staticfiles import StaticFiles

from scripts.run_gradio import build_app
from src.api import app as api_app
from src.config import load_config


def create_app():
    cfg = load_config()
    app = api_app

    gradio_app = build_app()
    app = gr.mount_gradio_app(app, gradio_app, path="/gradio")

    react_dist = ROOT / "frontend" / "dist"
    if react_dist.exists():
        app.mount("/", StaticFiles(directory=react_dist, html=True), name="react")

    return app, cfg


if __name__ == "__main__":
    app, cfg = create_app()
    uvicorn.run(
        app,
        host=cfg.get("api_host", "0.0.0.0"),
        port=int(cfg.get("api_port", 8000)),
    )
