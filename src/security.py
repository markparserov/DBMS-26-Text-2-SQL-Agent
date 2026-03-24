"""
Базовая защита от prompt-injection и утечки внутренней информации.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PromptGuard:
    max_input_length: int = 2000

    _injection_patterns = (
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(all\s+)?rules",
        r"you\s+are\s+now",
        r"system\s+prompt",
        r"reveal\s+(your\s+)?(tools|instructions|prompt)",
        r"show\s+(your\s+)?(internal|hidden)\s+prompt",
        r"developer\s+message",
        r"tool\s+schema",
        r"function[_\s]?call",
        r"base64",
    )

    _sensitive_output_patterns = (
        r"SYSTEM_PROMPT[_A-Z]*\s*=",
        r"\bfunction_call\b",
        r"\bgigachat\.models\b",
        r"\btool_schema\b",
        r"\btool_query\b",
        r"\btool_explain\b",
        r"Результат\s+(schema|query|explain)",
    )

    # Утечка рассуждений модели и служебных фраз — не показывать пользователю
    _internal_leak_patterns = (
        r"\(вызов инструмента\)",
        r"обратной косой черты",
        r"Провёл несколько проверок",
        r"Попробую использовать альтернативный подход",
        r"ошибк[ау].*символ",
        r"не устраняется стандартными методами",
        r"максимально упростив его структуру",
        r"Несмотря на многократную попытку исправить",
    )

    def sanitize_input(self, text: str) -> str:
        cleaned = (text or "").replace("\x00", " ").strip()
        cleaned = re.sub(r"[\x01-\x08\x0B-\x1F\x7F]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) > self.max_input_length:
            cleaned = cleaned[: self.max_input_length]
        return cleaned

    def is_injection_attempt(self, text: str) -> bool:
        normalized = (text or "").lower()
        return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in self._injection_patterns)

    def injection_reply(self) -> str:
        return (
            "Не могу выполнить этот запрос в таком виде. "
            "Сформулируйте, пожалуйста, вопрос по данным или SQL-аналитике без запросов к внутренним инструкциям агента."
        )

    def is_internal_reasoning_leak(self, text: str) -> bool:
        """Проверяет, что текст — утечка рассуждений модели или служебная фраза (вызов инструмента), а не ответ пользователю."""
        if not (text or "").strip():
            return False
        t = (text or "").strip()
        return any(re.search(p, t, re.IGNORECASE) for p in self._internal_leak_patterns)

    def sanitize_output(self, text: str) -> str:
        out = (text or "").strip()
        if not out:
            return out
        for pattern in self._sensitive_output_patterns:
            out = re.sub(pattern, "[скрыто]", out, flags=re.IGNORECASE)
        # Не отдаём технические трассировки
        out = re.sub(r"Traceback[\s\S]*", "Произошла техническая ошибка обработки ответа.", out, flags=re.IGNORECASE)
        return out.strip()
