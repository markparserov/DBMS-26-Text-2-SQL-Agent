export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sql?: string;
  downloadUrl?: string;
};

export type ChatMode = "chat" | "excel" | "report";

export type ChatApiResponse = {
  ok: boolean;
  session_id: string;
  mode: ChatMode;
  answer: string;
  sql: string;
  table_md: string;
  download_url: string;
  report: string;
  error?: string | null;
  row_count: number;
};

const API_BASE = "";

export async function sendChatMessage(
  message: string,
  sessionId: string | null,
  showSql: boolean,
  mode: ChatMode
): Promise<ChatApiResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      show_sql: showSql,
      mode
    })
  });

  if (!response.ok) {
    throw new Error("Ошибка запроса к серверу.");
  }
  return response.json();
}

export async function clearSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  });
  if (!response.ok) {
    throw new Error("Не удалось очистить контекст.");
  }
}
