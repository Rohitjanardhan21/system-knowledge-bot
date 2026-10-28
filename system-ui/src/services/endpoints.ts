export const API_BASE = import.meta.env.DEV ? "http://127.0.0.1:8020" : "";

export const WS_BASE = import.meta.env.DEV
  ? "ws://127.0.0.1:8020"
  : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
