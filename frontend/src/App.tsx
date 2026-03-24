import { useEffect, useState } from "react";
import ChatInput from "./components/ChatInput";
import ChatWindow from "./components/ChatWindow";
import { clearSession, sendChatMessage, type ChatMessage, type ChatMode } from "./api";

const SESSION_KEY = "sql_agent_session_id";

function uid() {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: "assistant",
      content: "Здравствуйте! Задайте вопрос по вашим данным."
    }
  ]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [showSql, setShowSql] = useState(false);
  const [mode, setMode] = useState<ChatMode>("chat");

  useEffect(() => {
    const stored = localStorage.getItem(SESSION_KEY);
    if (stored) {
      setSessionId(stored);
    }
  }, []);

  async function handleSend(message: string) {
    setError("");
    setIsLoading(true);
    setMessages((prev) => [...prev, { id: uid(), role: "user", content: message }]);
    try {
      const response = await sendChatMessage(message, sessionId, showSql, mode);
      setSessionId(response.session_id);
      localStorage.setItem(SESSION_KEY, response.session_id);
      let assistantText = response.answer;
      if (mode === "excel" && response.download_url) {
        assistantText = `${assistantText}\n\n[Скачать Excel-файл](${response.download_url})`;
      }
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          content: assistantText,
          sql: showSql ? response.sql || "" : "",
          downloadUrl: response.download_url || ""
        }
      ]);
    } catch (e) {
      setError("Не удалось получить ответ от сервера.");
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          content: "Произошла ошибка при обращении к серверу. Повторите попытку."
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleClear() {
    if (!sessionId) {
      setMessages([
        {
          id: uid(),
          role: "assistant",
          content: "Контекст очищен. Начинаем новый диалог."
        }
      ]);
      return;
    }

    try {
      await clearSession(sessionId);
      setMessages([
        {
          id: uid(),
          role: "assistant",
          content: "Контекст очищен. Можете задать новый вопрос."
        }
      ]);
    } catch {
      setError("Не удалось очистить контекст.");
    }
  }

  return (
    <main className="appRoot">
      <header className="appHeader">
        <div>
          <h1>SQL Agent</h1>
          <p>Аналитика муниципальных данных в формате чата</p>
        </div>
        <div className="headerControls">
          <label className="modeLabel">
            Режим:
            <select
              className="modeSelect"
              value={mode}
              onChange={(e) => setMode(e.target.value as ChatMode)}
              disabled={isLoading}
            >
              <option value="chat">Чат</option>
              <option value="excel">Выгрузка в Excel</option>
              <option value="report">Отчёт</option>
            </select>
          </label>
          <label className="checkboxLabel">
            <input
              type="checkbox"
              checked={showSql}
              onChange={(e) => setShowSql(e.target.checked)}
              disabled={isLoading}
            />
            Показывать SQL-запрос
          </label>
          <button className="clearBtn" onClick={handleClear} disabled={isLoading}>
            Очистить контекст
          </button>
        </div>
      </header>

      {error ? <div className="errorBox">{error}</div> : null}

      <ChatWindow messages={messages} isLoading={isLoading} />
      <ChatInput onSend={handleSend} disabled={isLoading} />
    </main>
  );
}
