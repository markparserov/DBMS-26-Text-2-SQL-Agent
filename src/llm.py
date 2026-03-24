"""
Клиент GigaChat для генерации SQL и вызова инструментов (schema, query, explain).
"""
import os
from typing import Any


DEFAULT_GIGACHAT_MAX_RETRIES = 3
DEFAULT_GIGACHAT_RETRY_BACKOFF_FACTOR = 0.5
DEFAULT_GIGACHAT_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)

def get_gigachat_model(credentials: str | None = None, preferred: str = "GigaChat-Max", timeout: float = 120.0) -> str:
    """
    Возвращает id модели: preferred, если доступна, иначе третья из get_models().
    """
    creds = credentials or os.environ.get("GIGACHAT_CREDENTIALS", "")
    if not creds:
        return preferred

    try:
        from gigachat import GigaChat
    except ImportError:
        return preferred

    with GigaChat(
        credentials=creds,
        verify_ssl_certs=False,
        timeout=timeout,
        max_retries=DEFAULT_GIGACHAT_MAX_RETRIES,
        retry_backoff_factor=DEFAULT_GIGACHAT_RETRY_BACKOFF_FACTOR,
        retry_on_status_codes=DEFAULT_GIGACHAT_RETRY_STATUS_CODES,
    ) as client:
        models = client.get_models()
        if models.data:
            for m in models.data:
                if getattr(m, "id", None) == preferred or getattr(m, "id_", None) == preferred:
                    return preferred
            if len(models.data) >= 3:
                third = models.data[2]
                return getattr(third, "id_", None) or getattr(third, "id", None) or preferred
    return preferred


def get_gigachat_functions(enable_web_search: bool = False) -> list[Any]:
    """Описания инструментов для GigaChat (schema, query, explain)."""
    try:
        from gigachat.models import Function, FunctionParameters
    except ImportError:
        return []

    functions = [
        Function(
            name="schema",
            description="Получить схему БД: DDL таблиц и комментарии к таблицам/колонкам. Вызови перед генерацией SQL, чтобы узнать имена таблиц и полей.",
            parameters=FunctionParameters(
                type="object",
                properties={
                    "format": {
                        "type": "string",
                        "enum": ["full", "compact"],
                        "description": "full — полная схема с DDL, compact — только имена таблиц и колонок",
                    }
                },
                required=[],
            ),
        ),
        Function(
            name="query",
            description="Выполнить read-only SQL (только SELECT). Возвращает таблицу. При ошибке в ответе будет указана причина — исправь SQL и вызови query снова.",
            parameters=FunctionParameters(
                type="object",
                properties={
                    "sql": {"type": "string", "description": "SQL запрос (только SELECT)"},
                    "limit": {"type": "integer", "description": "Максимум строк (по умолчанию 100)"},
                    "timeout_sec": {"type": "number", "description": "Таймаут в секундах"},
                },
                required=["sql"],
            ),
        ),
        Function(
            name="explain",
            description="Получить план выполнения запроса (EXPLAIN QUERY PLAN) и проверку синтаксиса. Можно вызвать для проверки SQL перед query.",
            parameters=FunctionParameters(
                type="object",
                properties={
                    "sql": {"type": "string", "description": "SQL запрос (SELECT) для анализа"},
                },
                required=["sql"],
            ),
        ),
    ]
    if enable_web_search:
        functions.append(
            Function(
                name="web_search",
                description=(
                    "Поиск в интернете для определений, методологии, нормативов, внешних показателей и проверки актуальности данных, "
                    "когда этой информации нет в БД. Не использовать для чистой SQL-аналитики по данным БД."
                ),
                parameters=FunctionParameters(
                    type="object",
                    properties={
                        "query": {"type": "string", "description": "Поисковый запрос"},
                        "max_results": {"type": "integer", "description": "Максимум результатов (по умолчанию 5)"},
                    },
                    required=["query"],
                ),
            )
        )
    return functions


def _messages_to_gigachat(messages: list[dict]) -> list[Any]:
    """Конвертирует messages [{"role", "content", "name"?}] в список gigachat.models.Messages."""
    from gigachat.models import Messages, MessagesRole

    out = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            out.append(Messages(role=MessagesRole.SYSTEM, content=content))
        elif role == "assistant":
            out.append(Messages(role=MessagesRole.ASSISTANT, content=content or ""))
        elif role == "function":
            # Результат вызова инструмента — передаём как user-сообщение
            name = m.get("name", "tool")
            out.append(Messages(role=MessagesRole.USER, content=f"[Результат {name}]\n{content}"))
        else:
            out.append(Messages(role=MessagesRole.USER, content=content))
    return out


def chat_with_tools(
    messages: list[dict],
    functions: list[Any],
    credentials: str | None = None,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    verify_ssl_certs: bool = False,
    timeout: float = 120.0,
) -> Any:
    """
    Один запрос к GigaChat с инструментами. Возвращает response (объект ответа API).
    Если модель вызвала инструмент: response.choices[0].finish_reason == "function_call",
    response.choices[0].message.function_call.name и .arguments (JSON-строка).
    """
    creds = credentials or os.environ.get("GIGACHAT_CREDENTIALS", "")
    if not creds:
        raise RuntimeError("Не заданы учётные данные GigaChat.")

    from gigachat import GigaChat
    from gigachat.models import Chat

    model_id = model or get_gigachat_model(creds)
    gc_messages = _messages_to_gigachat(messages)
    chat = Chat(messages=gc_messages, functions=functions)

    with GigaChat(
        credentials=creds,
        model=model_id,
        temperature=temperature,
        max_tokens=max_tokens,
        verify_ssl_certs=verify_ssl_certs,
        timeout=timeout,
        max_retries=DEFAULT_GIGACHAT_MAX_RETRIES,
        retry_backoff_factor=DEFAULT_GIGACHAT_RETRY_BACKOFF_FACTOR,
        retry_on_status_codes=DEFAULT_GIGACHAT_RETRY_STATUS_CODES,
    ) as client:
        response = client.chat(chat)

    if not response.choices or len(response.choices) == 0:
        raise RuntimeError("GigaChat API вернул ответ без choices.")
    return response


def chat_completion(
    messages: list[dict[str, str]],
    credentials: str | None = None,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    verify_ssl_certs: bool = False,
    timeout: float = 120.0,
) -> str:
    """
    Один запрос к GigaChat без инструментов. Возвращает content ответа.
    """
    creds = credentials or os.environ.get("GIGACHAT_CREDENTIALS", "")
    if not creds:
        raise RuntimeError("Не заданы учётные данные GigaChat. Укажите gigachat_credentials в config.yaml или GIGACHAT_CREDENTIALS.")

    try:
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole
    except ImportError as e:
        raise RuntimeError("Установите gigachat: pip install gigachat") from e

    model_id = model or get_gigachat_model(creds)
    gc_messages = _messages_to_gigachat(messages)
    chat = Chat(messages=gc_messages)

    try:
        with GigaChat(
            credentials=creds,
            model=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            verify_ssl_certs=verify_ssl_certs,
            timeout=timeout,
            max_retries=DEFAULT_GIGACHAT_MAX_RETRIES,
            retry_backoff_factor=DEFAULT_GIGACHAT_RETRY_BACKOFF_FACTOR,
            retry_on_status_codes=DEFAULT_GIGACHAT_RETRY_STATUS_CODES,
        ) as client:
            response = client.chat(chat)
            if not response.choices or len(response.choices) == 0:
                raise RuntimeError("GigaChat API вернул ответ без choices. Проверьте модель (llm_model) и квоты.")
            content = response.choices[0].message.content
            if content is None or (isinstance(content, str) and not content.strip()):
                raise RuntimeError("GigaChat API вернул пустой текст. Попробуйте другую модель в config или проверьте квоты.")
            return (content if isinstance(content, str) else str(content)).strip()
    except Exception as e:
        err = str(e).strip() or type(e).__name__
        raise RuntimeError(f"Ошибка GigaChat: {err}") from e
