import { useEffect, useRef } from "react";
import type { ChatMessage } from "../api";
import MessageBubble from "./MessageBubble";
import Spinner from "./Spinner";

type Props = {
  messages: ChatMessage[];
  isLoading: boolean;
};

export default function ChatWindow({ messages, isLoading }: Props) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <section className="chatWindow">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isLoading ? (
        <div className="messageRow assistantRow">
          <div className="bubble assistantBubble">
            <Spinner />
          </div>
        </div>
      ) : null}
      <div ref={endRef} />
    </section>
  );
}
