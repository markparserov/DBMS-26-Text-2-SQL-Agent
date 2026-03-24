import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import SqlBlock from "./SqlBlock";
import type { ChatMessage } from "../api";

type Props = {
  message: ChatMessage;
};

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const isPdf = message.downloadUrl?.toLowerCase().endsWith(".pdf");
  const isExcel = message.downloadUrl?.toLowerCase().match(/\.xlsx?$/);
  return (
    <div className={`messageRow ${isUser ? "userRow" : "assistantRow"}`}>
      <div className={`bubble ${isUser ? "userBubble" : "assistantBubble"}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        {!isUser && message.sql ? <SqlBlock sql={message.sql} /> : null}
        {!isUser && message.downloadUrl ? (
          <p className="downloadLinkWrap">
            <a href={message.downloadUrl} download className="downloadReportLink">
              {isPdf ? "Скачать отчёт (PDF)" : isExcel ? "Скачать Excel" : "Скачать файл"}
            </a>
          </p>
        ) : null}
      </div>
    </div>
  );
}
