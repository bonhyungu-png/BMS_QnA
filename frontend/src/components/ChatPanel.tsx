// frontend/src/components/ChatPanel.tsx
import { useState } from "react";
import { sendChat } from "../api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSend() {
    const question = input.trim();
    if (!question || loading) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const answer = await sendChat(question);
      setMessages((prev) => [...prev, { role: "assistant", text: answer }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", text: `오류: ${(err as Error).message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-message chat-message--${m.role}`}>
            {m.text}
          </div>
        ))}
        {loading && <div className="chat-message chat-message--assistant">답변 생성 중...</div>}
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") handleSend(); }}
          placeholder="질문을 입력하세요"
        />
        <button onClick={handleSend} disabled={loading}>전송</button>
      </div>
    </div>
  );
}
