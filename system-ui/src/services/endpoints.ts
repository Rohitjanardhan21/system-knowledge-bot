export const API_BASE = import.meta.env.DEV ? "http://127.0.0.1:8000" : "";

export const WS_BASE = import.meta.env.DEV
  ? "ws://127.0.0.1:8000"
  : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
