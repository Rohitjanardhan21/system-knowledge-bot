import { useState } from "react";

export default function AgentChat() {

  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");

  const sendMessage = async () => {

    if (!input) return;

    const res = await fetch("http://127.0.0.1:8000/system/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: input })
    });

    const data = await res.json();

    setMessages(prev => [
      ...prev,
      { role: "user", text: input },
      { role: "agent", text: data.response }
    ]);

    setInput("");
  };

  return (
    <div className="bg-gray-900 p-4 rounded-xl space-y-2">

      <h3 className="text-sm text-gray-400">🤖 System Agent</h3>

      <div className="h-56 overflow-y-auto space-y-2">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-blue-400" : "text-green-400"}>
            {m.text}
          </div>
        ))}
      </div>

      <div className="flex">
        <input
          className="flex-1 bg-black p-2 text-sm"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Ask your system..."
        />
        <button onClick={sendMessage} className="bg-green-600 px-3">
          Send
        </button>
      </div>

    </div>
  );
}
