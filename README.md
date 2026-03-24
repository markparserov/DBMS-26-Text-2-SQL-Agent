# SQL Agent (проект по курсу «Основы баз данных»)

Русскоязычный Text-to-SQL агент для анализа данных в SQLite, с RAG-контекстом, FastAPI, Gradio и React UI. Проект выполнили Фёдор Грозовский и Иван Заболонков.

## Что есть в проекте

- Агент на GigaChat с инструментами `schema`, `query`, `explain`, опционально `web_search`.
- RAG-слой на Chroma + `sentence-transformers` для схемы БД и примеров запросов.
- API на FastAPI: чат, очистка контекста, скачивание выгрузок, эмбеддинги.
- Два интерфейса:
  - Gradio (`/gradio` и отдельный запуск),
  - React (`frontend/`).
- Сессии пользователей и backend-логирование в SQLite.
- Режимы ответа: `chat`, `excel` (выгрузка), `report` (текстовый отчет + PDF при успешной генерации).
- Поддержка нескольких SQL-запросов в одном ответе с последующим синтезом итогового ответа.
- Защита от prompt-injection и безопасная санитизация ошибок SQL для повторных попыток запроса.
- Fallback-логика при недоступном web search: ответ по данным БД с явной пометкой о внешних данных.

## Скриншоты

[!картинка1](https://github.com/user-attachments/assets/1b7d9b5d-cfad-451a-a3c5-8414bb94934f)

(https://github.com/user-attachments/assets/55f3ceb7-de37-4b52-bb5d-256631d817fb)
(https://github.com/user-attachments/assets/048ffe10-5f4b-4423-ade0-5a8e06e8e7ae)
(https://github.com/user-attachments/assets/977b3f4f-011c-4908-bc0b-928c04ee25c0)
(https://github.com/user-attachments/assets/f2794c4a-2048-45f8-92c3-c10253f83f58)


## Структура

- `src/` — backend-логика (агент, API, конфиг, безопасность, RAG, SQL-инструменты).
- `scripts/` — запуск и служебные скрипты.
- `frontend/` — React/Vite клиент.
- `data/` — рабочие данные:
  - `db/` — SQLite база,
  - `chroma/` — RAG-индексы,
  - `exports/` — Excel/PDF выгрузки,
  - `logs/` — логи,
  - `parquet/` — исходные parquet/xlsx.
- `tests/` — unit-тесты SQL-валидатора и инструментов БД.

## Требования

- Linux/macOS (проект ориентирован на запуск в shell + tmux).
- Python 3.10+.
- Node.js 18+ и npm (для React).
- Conda (рекомендуется, скрипты учитывают conda-окружение).
- tmux (для запуска через `scripts/run_agent_app.sh`).
- curl (для проверки доступности SearXNG в `run_agent_app.sh`).
- Для web search: Docker/Docker Compose (для SearXNG), если включаете поиск.

## Быстрый старт

### 1) Окружение и зависимости

```bash
conda create -n sql_agent python=3.11 -y
conda activate sql_agent
pip install -r requirements.txt
```

Для React:

```bash
cd frontend
npm install
cd ..
```

### 2) Подготовка данных

Собрать SQLite из `data/parquet`:

```bash
python scripts/build_db.py
```

Построить RAG-индекс:

```bash
python scripts/build_rag_index.py
```

### 3) Настройка конфига

Основной файл: `config.yaml`.

Ключевые параметры:
- `db_path`, `chroma_path`
- `schema_descriptions_path`, `example_queries_path`
- `max_rows`, `query_timeout_sec`
- `llm_model`, `gigachat_timeout_sec`
- `api_host`, `api_port`
- `session_*`, `logging_db_path`
- `enable_web_search`, `searxng_url`

Любой параметр можно переопределить переменной окружения формата:
- `SQL_AGENT_<KEY_IN_UPPERCASE>`

Примеры:
- `SQL_AGENT_API_PORT=8010`
- `SQL_AGENT_MAX_ROWS=200`

Отдельно поддерживается:
- `GIGACHAT_CREDENTIALS` (приоритетно для ключа доступа LLM),
- `ENABLE_WEB_SEARCH` и `SEARXNG_URL` (для интернет-поиска),
- `SQL_AGENT_API_URL` (для standalone Gradio-клиента),
- `CONDA_ENV` (для `scripts/run_agent_app.sh`, по умолчанию `sql_agent`).

## Запуск

### Вариант A: все в `tmux` (рекомендуется)

Скрипт поднимает 3 окна (`api`, `gradio`, `react`) в сессии `agent_app`:

```bash
bash scripts/run_agent_app.sh
```

Адреса:
- API: `http://localhost:8000`
- Gradio: `http://localhost:7860`
- React dev: `http://localhost:3000`

Если `ENABLE_WEB_SEARCH=1`, скрипт предварительно проверяет SearXNG и пытается поднять его через `docker-compose.searxng.yml`.

### Вариант B: только API

```bash
python scripts/run_api_only.py
```

### Вариант C: единый сервер (API + Gradio + React static)

Сначала собрать frontend:

```bash
cd frontend
npm run build
cd ..
python scripts/run_server.py
```

После этого React будет доступен на `/`, Gradio на `/gradio`.

### Вариант C1: только Gradio как клиент к API

Скрипт `scripts/run_gradio.py` не поднимает backend-движок, а обращается к уже запущенному API.

```bash
# в отдельном терминале сначала API
python scripts/run_api_only.py

# затем Gradio
python scripts/run_gradio.py
```

При необходимости адрес API задается переменной:

```bash
SQL_AGENT_API_URL=http://127.0.0.1:8000 python scripts/run_gradio.py
```

### Вариант D: CLI вопрос-ответ

```bash
python scripts/run_agent.py "Сколько записей в таблице consumption?"
```

или

```bash
echo "Сколько записей в таблице consumption?" | python scripts/run_agent.py
```

### Вариант E: MCP-сервер

```bash
python scripts/run_mcp_server.py
```

## API

- `GET /api/health` — проверка состояния.
- `POST /api/chat` — основной чат-запрос.
- `POST /api/clear` — очистка истории сессии.
- `GET /api/download/{filename}` — скачивание файла выгрузки.
- `POST /api/embeddings` — получение эмбеддингов по списку текстов.
- `GET /docs` — Swagger UI для интерактивной проверки API.

Пример `POST /api/chat`:

```json
{
  "message": "Сравни среднюю зарплату по регионам",
  "session_id": null,
  "show_sql": false,
  "mode": "chat"
}
```

## Тесты

```bash
pytest -q
```

Текущие тесты покрывают:
- SQL-валидацию (`tests/test_sql_validator.py`),
- инструменты `schema/query/explain` (`tests/test_tools.py`).

## Полезные замечания

- Web search по умолчанию выключен; включается через `ENABLE_WEB_SEARCH=1`.
- При включенном web search скрипт `run_agent_app.sh` пытается поднять SearXNG через `docker-compose.searxng.yml`.
- Экспортные файлы сохраняются в `data/exports/`.
- Логи взаимодействий и LLM-вызовов сохраняются в `data/logs/logs.db`.
- Для data-вопросов агент принудительно пытается использовать `schema -> query`, даже если модель сначала ушла в текстовый ответ без SQL.
