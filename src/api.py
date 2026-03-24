"""
HTTP API для SQL-агента.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from src.agent_tools import run_agent_with_tools
from src.config import load_config
from src.export import export_report_to_pdf, export_to_excel, generate_report
from src.logging_db import LoggingDB
from src.rag.embeddings import DEFAULT_EMBEDDING_MODEL, get_embeddings
from src.security import PromptGuard
from src.sessions import SessionManager


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Сообщение пользователя")
    session_id: str | None = Field(default=None, description="Идентификатор сессии")
    show_sql: bool = Field(default=False, description="Показывать SQL в ответе")
    mode: Literal["chat", "excel", "report"] = Field(default="chat", description="Режим ответа")


class ChatResponse(BaseModel):
    ok: bool
    session_id: str
    mode: Literal["chat", "excel", "report"] = "chat"
    answer: str
    sql: str = ""
    table_md: str = ""
    download_url: str = ""
    report: str = ""
    error: str | None = None
    row_count: int = 0


class ClearRequest(BaseModel):
    session_id: str


class ClearResponse(BaseModel):
    ok: bool
    session_id: str
    deleted_messages: int


class EmbeddingsRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="Список текстов для эмбеддингов")
    model: str = Field(default=DEFAULT_EMBEDDING_MODEL)


class EmbeddingsResponse(BaseModel):
    ok: bool = True
    model: str
    embeddings: list[list[float]]


cfg = load_config()
session_manager = SessionManager(cfg["session_db_path"])
logging_db = LoggingDB(cfg["logging_db_path"])
guard = PromptGuard(max_input_length=cfg.get("max_input_length", 2000))
exports_dir = Path(cfg.get("exports_dir", "data/exports"))
if not exports_dir.is_absolute():
    exports_dir = Path(__file__).resolve().parent.parent / exports_dir
exports_dir.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warmup эмбеддера при старте, чтобы модель загрузилась до первого запроса
    try:
        await run_in_threadpool(get_embeddings, ["warmup"], DEFAULT_EMBEDDING_MODEL)
        logging.getLogger("src.api").info("Embeddings warmup done.")
    except Exception as e:
        logging.getLogger("src.api").warning("Embeddings warmup failed: %s", e)
    yield


app = FastAPI(
    title="Русскоязычный SQL Agent API",
    description="API для чата с Text-2-SQL агентом на русском языке",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "status": "healthy", "language": cfg.get("app_language", "ru")}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    msg = guard.sanitize_input(payload.message)
    sid = session_manager.ensure_session(payload.session_id)
    if guard.is_injection_attempt(msg):
        text = guard.injection_reply()
        session_manager.add_message(sid, "user", msg, visible_to_user=True)
        session_manager.add_message(sid, "assistant", text, visible_to_user=True, meta={"blocked": True})
        logging_db.log_event("security_blocked_prompt_injection", {"message": msg[:500]}, session_id=sid)
        return ChatResponse(
            ok=False,
            session_id=sid,
            mode=payload.mode,
            answer=text,
            error="Запрос заблокирован политикой безопасности.",
        )

    result = run_agent_with_tools(msg, cfg, session_id=sid)
    answer = result.get("answer", "")
    download_url = ""
    report = ""
    rows = result.get("rows", [])
    all_query_results = result.get("all_query_results") or []

    if payload.mode == "excel":
        if not rows and all_query_results:
            for item in all_query_results:
                item_rows = item.get("rows", [])
                if item_rows:
                    rows = item_rows
                    break
        if rows:
            file_path = export_to_excel(rows, export_dir=exports_dir, filename_prefix="sql_export")
            download_url = f"/api/download/{file_path.name}"
            answer = f"{answer}\n\nФайл Excel сформирован и готов к скачиванию."
            logging_db.log_event("excel_export_ready", {"filename": file_path.name}, session_id=sid)
        else:
            answer = f"{answer}\n\nНет данных для выгрузки в Excel."
    elif payload.mode == "report":
        has_report_data = bool(rows) or any(item.get("rows") for item in all_query_results)
        if has_report_data:
            report = generate_report(
                question=msg,
                rows=rows,
                sql=result.get("sql", ""),
                config=cfg,
                all_query_results=all_query_results,
            )
            answer = report
            try:
                pdf_path = export_report_to_pdf(
                    report,
                    export_dir=exports_dir,
                    filename_prefix="report",
                )
                download_url = f"/api/download/{pdf_path.name}"
                answer = f"{answer}\n\n[Скачать отчёт (PDF)]({download_url})"
            except Exception as e:
                logging_db.log_event("report_pdf_error", {"error": str(e)[:200]}, session_id=sid)
            logging_db.log_event("report_generated", {"row_count": len(rows)}, session_id=sid)
        else:
            if result.get("sql"):
                answer = f"{answer}\n\nЗапрос выполнен, но строк не найдено. Построить отчёт невозможно."
            else:
                answer = f"{answer}\n\nНевозможно построить отчёт: запрос не вернул данных."

    return ChatResponse(
        ok=bool(result.get("ok")),
        session_id=result.get("session_id", sid),
        mode=payload.mode,
        answer=answer,
        sql=result.get("sql", ""),
        table_md=result.get("table_md", ""),
        download_url=download_url,
        report=report,
        error=result.get("error"),
        row_count=int(result.get("row_count", 0)),
    )


@app.post("/api/clear", response_model=ClearResponse)
def clear(payload: ClearRequest) -> ClearResponse:
    sid = session_manager.ensure_session(payload.session_id)
    deleted = session_manager.clear_session(sid)
    logging_db.log_session_action(
        session_id=sid,
        action="clear",
        total_messages=0,
        details={"deleted_messages": deleted},
    )
    return ClearResponse(ok=True, session_id=sid, deleted_messages=deleted)


def _download_media_type(filename: str) -> str:
    suf = Path(filename).suffix.lower()
    if suf == ".pdf":
        return "application/pdf"
    if suf in (".xlsx", ".xls"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/octet-stream"


@app.get("/api/download/{filename}")
def download_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    file_path = exports_dir / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")
    return FileResponse(
        path=file_path,
        filename=safe_name,
        media_type=_download_media_type(safe_name),
    )


@app.post("/api/embeddings", response_model=EmbeddingsResponse)
async def embeddings(payload: EmbeddingsRequest) -> EmbeddingsResponse:
    vectors = await run_in_threadpool(get_embeddings, payload.texts, payload.model)
    return EmbeddingsResponse(model=payload.model, embeddings=vectors)
