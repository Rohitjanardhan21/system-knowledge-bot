import { useEffect, useRef, useState } from "react";

export function useWebSocket(url: string) {
  const [data, setData] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (wsRef.current) return; // 🔥 prevent multiple connections

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("✅ WebSocket connected");
    };

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setData(parsed);
      } catch (err) {
        console.error("Invalid WS data:", err);
      }
    };

    ws.onclose = () => {
      console.log("🔴 WebSocket closed");
      wsRef.current = null;
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [url]);

  return data;
}
