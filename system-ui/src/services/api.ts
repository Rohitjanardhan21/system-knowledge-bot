import axios from "axios";
import {
  getAccessToken,
  refreshAccessToken,
} from "./auth";

const API_BASE = "http://127.0.0.1:8000";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status !== 401 ||
      originalRequest?._retry
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    const newToken = await refreshAccessToken();

    if (!newToken) {
      return Promise.reject(error);
    }

    originalRequest.headers.Authorization = `Bearer ${newToken}`;

    return api(originalRequest);
  },
);

export async function fetchSystemStatus() {
  const response = await api.get("/os/status");
  return response.data;
}


// ==================== COGNITIVE API ====================

export interface CognitivePrediction {
  id: string;
  type: string;
  eta_minutes: number;
  confidence: number;
  confidence_label?: string;
  message?: string;
  action?: string;
  severity?: string;
  acknowledged?: boolean;
  trustworthy?: boolean;
  explanation?: unknown;
}

export async function fetchCognitivePredictions(): Promise<CognitivePrediction[]> {
  const { data } = await api.get("/cognitive/predictions");
  return data ?? [];
}

export async function acknowledgeCognitivePrediction(id: string) {
  const { data } = await api.post(
    `/cognitive/predictions/${encodeURIComponent(id)}/acknowledge`
  );
  return data;
}

export async function resolveCognitivePrediction(
  id: string,
  wasCorrect: boolean
) {
  const { data } = await api.post(
    `/cognitive/predictions/${encodeURIComponent(id)}/resolve`,
    undefined,
    { params: { was_correct: wasCorrect } }
  );
  return data;
}

export async function fetchCognitiveDNA() {
  const { data } = await api.get("/cognitive/dna");
  return data ?? {};
}

export async function fetchCognitiveRemediationStatus() {
  const { data } = await api.get("/cognitive/remediation/status");
  return data ?? {};
}

export async function fetchCognitiveRemediationLog(limit = 20) {
  const { data } = await api.get("/cognitive/remediation/log", {
    params: { limit },
  });
  return data ?? [];
}

export async function fetchCognitiveIncidents() {
  const { data } = await api.get("/cognitive/incidents");
  return data ?? [];
}

export async function fetchCognitiveNotifications() {
  const { data } = await api.get("/cognitive/notifications");
  return data ?? [];
}
