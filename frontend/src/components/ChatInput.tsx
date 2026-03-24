import { useState } from "react";

type Props = {
  disabled?: boolean;
  onSend: (message: string) => Promise<void>;
};

export default function ChatInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  async function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    setValue("");
    await onSend(text);
  }

  return (
    <form
      className="chatInputForm"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <textarea
        className="chatInput"
        placeholder="Введите вопрос по данным..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit();
          }
        }}
        rows={2}
        disabled={disabled}
      />
      <button className="sendBtn" type="submit" disabled={disabled}>
        Отправить
      </button>
    </form>
  );
}
