import { useState } from "react";

export default function ChatPanel() {
  const [msg, setMsg] = useState("");
  const [response, setResponse] = useState("");

  const send = async () => {
    const res = await fetch("http://127.0.0.1:8000/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ message: msg }),
    });

    const data = await res.json();
    setResponse(data.response);
  };

  return (
    <div className="glass-card p-4">
      <h2 className="text-lg">💬 System Chat</h2>

      <input
        value={msg}
        onChange={(e) => setMsg(e.target.value)}
        className="w-full p-2 text-black rounded mt-2"
        placeholder="Ask about system..."
      />

      <button onClick={send} className="mt-2 bg-blue-500 px-3 py-1 rounded">
        Ask
      </button>

      <p className="mt-2 text-sm">{response}</p>
    </div>
  );
}
