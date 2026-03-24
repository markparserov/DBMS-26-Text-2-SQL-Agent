#!/usr/bin/env bash
# Единый entry: поднимает API, Gradio и React в tmux-сессии agent_app (три окна).
# Использование: ./scripts/run_agent_app.sh   или   bash scripts/run_agent_app.sh

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SESSION_NAME="agent_app"
ENV_FILE="$ROOT/.env"

# Подтянуть переменные окружения проекта (если есть .env)
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Если включён веб-поиск — проверить SearXNG и при необходимости запустить
SEARXNG_URL="${SEARXNG_URL:-http://127.0.0.1:8080}"
if [ "${ENABLE_WEB_SEARCH:-0}" = "1" ]; then
  searx_ok() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 6 "${SEARXNG_URL%/}/search?format=json&q=test" 2>/dev/null || true)
    [ "$code" = "200" ]
  }
  if ! searx_ok; then
    echo "SearXNG не отвечает на ${SEARXNG_URL}. Запуск через Docker..."
    run_compose() {
      local cmd
      if docker compose version >/dev/null 2>&1; then
        cmd=(docker compose -f "$ROOT/docker-compose.searxng.yml" up -d)
      elif command -v docker-compose >/dev/null 2>&1; then
        cmd=(docker-compose -f "$ROOT/docker-compose.searxng.yml" up -d)
      else
        return 1
      fi
      "${cmd[@]}" 2>/dev/null && return 0
      if command -v sudo >/dev/null 2>&1; then
        sudo "${cmd[@]}" 2>/dev/null
      else
        return 1
      fi
    }
    if command -v docker >/dev/null 2>&1 && run_compose; then
      echo "Ожидание готовности SearXNG (до 45 с)..."
      for _ in $(seq 1 15); do
        sleep 3
        if searx_ok; then echo "SearXNG запущен."; break; fi
      done
      searx_ok || echo "Предупреждение: SearXNG так и не ответил; веб-поиск может быть недоступен."
    else
      echo "Предупреждение: не удалось запустить SearXNG (установлен ли Docker?). Веб-поиск будет недоступен."
    fi
  fi
fi

# Убить старую сессию, если есть
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Тише загрузка моделей HF и прогресс-бары (общее для всех окон)
export HF_HUB_DISABLE_TELEMETRY=1
export TRANSFORMERS_VERBOSITY=error
export TQDM_DISABLE=1

CONDA_ENV="${CONDA_ENV:-sql_agent}"
PY_CMD="conda run --no-capture-output -n $CONDA_ENV python -u"

# Создать сессию и первое окно (API)
tmux new-session -d -s "$SESSION_NAME" -n api "cd $ROOT && $PY_CMD scripts/run_api_only.py"

# Окно Gradio
tmux new-window -t "$SESSION_NAME" -n gradio "cd $ROOT && $PY_CMD scripts/run_gradio.py"

# Окно React (dev-сервер)
tmux new-window -t "$SESSION_NAME" -n react "cd $ROOT/frontend && npm run dev"

echo "Tmux-сессия '$SESSION_NAME' запущена."
echo "  Окно 0 (api):    http://localhost:8000"
echo "  Окно 1 (gradio): http://localhost:7860"
echo "  Окно 2 (react):  http://localhost:3000"
echo "  ENABLE_WEB_SEARCH=${ENABLE_WEB_SEARCH:-0}"
echo ""
echo "Подключиться: tmux attach -t $SESSION_NAME"
echo "Переключение окон: Ctrl+b 0, Ctrl+b 1, Ctrl+b 2"
