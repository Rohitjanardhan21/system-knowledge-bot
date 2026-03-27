export function connectWebSocket(callback: (data: any) => void) {
  const ws = new WebSocket("ws://127.0.0.1:8000/ws/system");

  // -----------------------------------------
  // CONNECTED
  // -----------------------------------------
  ws.onopen = () => {
    console.log("✅ WebSocket connected");
  };

  // -----------------------------------------
  // RECEIVE DATA
  // -----------------------------------------
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      callback(data);
    } catch (err) {
      console.error("❌ WebSocket parse error:", err);
    }
  };

  // -----------------------------------------
  // ERROR
  // -----------------------------------------
  ws.onerror = (err) => {
    console.error("❌ WebSocket error:", err);
  };

  // -----------------------------------------
  // CLOSE
  // -----------------------------------------
  ws.onclose = () => {
    console.log("🔌 WebSocket disconnected");
  };

  // 🔥 CRITICAL: RETURN INSTANCE
  return ws;
}
