"""
Клиент web-поиска через SearXNG.
"""
from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _parse_bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def is_web_search_enabled(config: dict[str, Any] | None = None) -> bool:
    """
    Определяет, включен ли web-поиск.
    Приоритет: ENABLE_WEB_SEARCH (env) > config.enable_web_search > False.
    """
    env_value = os.environ.get("ENABLE_WEB_SEARCH")
    if env_value is not None:
        return _parse_bool(env_value)
    cfg = config or {}
    return bool(cfg.get("enable_web_search", False))


def searxng_base_url(config: dict[str, Any] | None = None) -> str:
    env_url = (os.environ.get("SEARXNG_URL") or "").strip()
    if env_url:
        return env_url.rstrip("/")
    cfg = config or {}
    return str(cfg.get("searxng_url", "http://localhost:8080")).rstrip("/")


def _query_with_domain_filter(query: str, domain_filter: list[str] | None) -> str:
    q = (query or "").strip()
    if not q:
        return q
    domains = [d.strip() for d in (domain_filter or []) if d and d.strip()]
    if not domains:
        return q
    if len(domains) == 1:
        return f"{q} site:{domains[0]}"
    domain_expr = " OR ".join(f"site:{d}" for d in domains)
    return f"{q} ({domain_expr})"


def web_search(
    query: str,
    *,
    max_results: int = 5,
    domain_filter: list[str] | None = None,
    config: dict[str, Any] | None = None,
    timeout_sec: float = 10.0,
) -> dict[str, Any]:
    """
    Выполняет поиск через SearXNG JSON API.
    Возвращает словарь: ok, results, error.
    """
    q = _query_with_domain_filter(query, domain_filter)
    if not q:
        return {"ok": False, "results": [], "error": "Пустой поисковый запрос."}

    base = searxng_base_url(config)
    params = {
        "q": q,
        "format": "json",
        "categories": "general",
        "language": "ru",
        "engines": "duckduckgo,brave,bing,wikipedia",
    }
    url = f"{base}/search?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        err_str = str(e)[:160]
        hint = " (возможно, SearXNG не запущен)" if ("111" in err_str or "Connection refused" in err_str or "refused" in err_str.lower()) else ""
        return {"ok": False, "results": [], "error": f"Поиск временно недоступен{hint}: {err_str}"}

    out: list[dict[str, str]] = []
    for item in (payload.get("results") or [])[: max(1, int(max_results))]:
        out.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "snippet": str(item.get("content", "")).strip(),
            }
        )
    return {"ok": True, "results": out, "error": None}
