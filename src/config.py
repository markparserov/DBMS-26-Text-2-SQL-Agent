"""
Конфигурация агента: YAML + переменные окружения.
"""
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parent.parent


def load_config(config_path: str | Path | None = None) -> dict:
    """Загружает config.yaml или config.example.yaml; переопределяет из env."""
    path = Path(config_path) if config_path else ROOT / "config.yaml"
    if not path.exists():
        path = ROOT / "config.example.yaml"
    if not path.exists() or yaml is None:
        base = {}
    else:
        base = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def get(key: str, default=None, coerce=str):
        env_key = "SQL_AGENT_" + key.upper()
        if env_key in os.environ:
            val = os.environ[env_key]
            if coerce is int:
                return int(val)
            if coerce is float:
                return float(val)
            if coerce is bool:
                return str(val).strip().lower() in ("1", "true", "yes", "on")
            return val
        return base.get(key, default)

    def resolve_path(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else ROOT / path

    db = get("db_path", "data/db/business.db")
    chroma = get("chroma_path", "data/chroma")
    schema_desc = get("schema_descriptions_path", "data/schema_descriptions.json")
    examples = get("example_queries_path", "data/example_queries.json")
    log_path = get("log_path", "data/logs/agent.jsonl")
    session_db_path = get("session_db_path", "data/sessions.db")
    logging_db_path = get("logging_db_path", "data/logs/logs.db")

    return {
        "db_path": resolve_path(db),
        "chroma_path": resolve_path(chroma),
        "schema_descriptions_path": resolve_path(schema_desc),
        "example_queries_path": resolve_path(examples),
        "max_rows": get("max_rows", 100, int),
        "query_timeout_sec": get("query_timeout_sec", 30, int),
        "gigachat_credentials": get("gigachat_credentials") or os.environ.get("GIGACHAT_CREDENTIALS", ""),
        "llm_model": get("llm_model", "GigaChat-2-Max"),
        "rag_k_ddl": get("rag_k_ddl", 5, int),
        "rag_k_examples": get("rag_k_examples", 2, int),
        "log_path": resolve_path(log_path),
        "session_db_path": resolve_path(session_db_path),
        "session_max_age_hours": get("session_max_age_hours", 24, int),
        "session_max_history_turns": get("session_max_history_turns", 20, int),
        "logging_db_path": resolve_path(logging_db_path),
        "api_host": get("api_host", "0.0.0.0"),
        "api_port": get("api_port", 8000, int),
        "max_input_length": get("max_input_length", 2000, int),
        "app_language": get("app_language", "ru"),
        "project_locale": get("project_locale", "ru_RU"),
        "gigachat_verify_ssl": False,
        "gigachat_timeout_sec": get("gigachat_timeout_sec", 120, int),
        "max_completion_tokens": get("max_completion_tokens", 4096, int),
        "enable_web_search": get("enable_web_search", False, bool),
        "searxng_url": get("searxng_url", "http://localhost:8080"),
    }
