import { useState, useRef, useEffect } from "react";

interface Props {
isOpen: boolean;
onClose: () => void;
}

export default function AIChatPanel({ isOpen, onClose }: Props) {

const [messages, setMessages] = useState<any[]>([]);
const [input, setInput] = useState("");
const [loading, setLoading] = useState(false);

const bottomRef = useRef<HTMLDivElement | null>(null);

// --------------------------------------------------
// AUTO SCROLL
// --------------------------------------------------
useEffect(() => {
bottomRef.current?.scrollIntoView({ behavior: "smooth" });
}, [messages]);

// --------------------------------------------------
// SMART SUGGESTIONS
// --------------------------------------------------
const suggestions = [
"Why is CPU high?",
"Any anomalies right now?",
"Predict system failure",
"What should I fix?",
"Is system stable?",
"Top risky process?"
];

// --------------------------------------------------
// SEND MESSAGE (STREAMING)
// --------------------------------------------------
const sendMessage = async (customInput?: string) => {

```
const query = customInput || input;
if (!query) return;

const userMsg = { role: "user", text: query };
setMessages(prev => [...prev, userMsg]);

setInput("");
setLoading(true);

try {
  const res = await fetch("http://localhost:8000/ai/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ query })
  });

  const reader = res.body?.getReader();
  let text = "";

  const botMsg = { role: "bot", text: "" };
  setMessages(prev => [...prev, botMsg]);

  while (true) {
    const { done, value } = await reader!.read();
    if (done) break;

    text += new TextDecoder().decode(value);

    setMessages(prev => {
      const updated = [...prev];
      updated[updated.length - 1].text = text;
      return updated;
    });
  }

} catch (err) {
  setMessages(prev => [
    ...prev,
    { role: "bot", text: "⚠️ AI service unavailable" }
  ]);
}

setLoading(false);
```

};

// --------------------------------------------------
// UI
// --------------------------------------------------
if (!isOpen) return null;

return ( <div className="fixed bottom-0 left-0 w-full h-[65%] bg-black border-t border-zinc-800 flex flex-col z-50">

```
  {/* HEADER */}
  <div className="flex justify-between items-center p-4 border-b border-zinc-800">
    <div>
      <div className="font-semibold text-lg">AI System Assistant</div>
      <div className="text-xs text-zinc-500">
        Context-aware • No fabricated insights • Human validation required
      </div>
    </div>
    <button onClick={onClose} className="text-zinc-400 hover:text-white">
      ✕
    </button>
  </div>

  {/* SUGGESTIONS */}
  <div className="flex gap-2 overflow-x-auto p-3 border-b border-zinc-800">
    {suggestions.map((s, i) => (
      <button
        key={i}
        onClick={() => sendMessage(s)}
        className="px-3 py-1 text-xs bg-zinc-800 rounded-full hover:bg-zinc-700 whitespace-nowrap"
      >
        {s}
      </button>
    ))}
  </div>

  {/* MESSAGES */}
  <div className="flex-1 overflow-y-auto p-4 space-y-3">

    {messages.length === 0 && (
      <div className="text-zinc-500 text-sm">
        Ask anything about your system.  
        <br />
        Example: "Why is CPU usage high?"
      </div>
    )}

    {messages.map((m, i) => (
      <div
        key={i}
        className={`max-w-[75%] p-3 rounded-xl text-sm ${
          m.role === "user"
            ? "bg-blue-600 ml-auto"
            : "bg-zinc-800"
        }`}
      >
        {m.text}
      </div>
    ))}

    {loading && (
      <div className="text-zinc-500 text-sm animate-pulse">
        AI is thinking...
      </div>
    )}

    <div ref={bottomRef} />

  </div>

  {/* HUMAN SAFETY NOTE */}
  <div className="text-[11px] text-zinc-500 px-4 py-2 border-t border-zinc-800">
    ⚠️ AI suggestions are assistive. Always validate before executing critical actions.
  </div>

  {/* INPUT */}
  <div className="p-4 border-t border-zinc-800 flex gap-2">

    <input
      value={input}
      onChange={(e) => setInput(e.target.value)}
      placeholder="Ask about your system..."
      className="flex-1 bg-zinc-900 px-3 py-2 rounded-lg outline-none text-sm"
      onKeyDown={(e) => e.key === "Enter" && sendMessage()}
    />

    <button
      onClick={() => sendMessage()}
      disabled={loading}
      className="bg-blue-600 px-4 py-2 rounded-lg text-sm hover:bg-blue-500 disabled:opacity-50"
    >
      Send
    </button>

  </div>

</div>
```

);
}
