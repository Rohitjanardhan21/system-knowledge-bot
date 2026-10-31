import axios from "axios";
import {
  getAccessToken,
  refreshAccessToken,
} from "./auth";
import { API_BASE } from "./endpoints";

declare global {
  interface Window {
    pywebview?: {
      api?: {
        get_api_key: () => Promise<string>;
        quit_cvis: () => Promise<{ status: string }>;
      };
    };
  }
}

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
});

api.interceptors.request.use(async (config) => {
  const desktopApi = window.pywebview?.api;
  if (desktopApi?.get_api_key) {
    const apiKey = await desktopApi.get_api_key();
    if (!apiKey) {
      throw new Error("The desktop application API key is unavailable.");
    }
    config.headers.set("X-API-Key", apiKey);
    config.headers.delete("Authorization");
    return config;
  }

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
    const requestUrl = String(originalRequest?.url ?? "");

    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      requestUrl.includes("/auth/refresh") ||
      requestUrl.includes("/auth/login")
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    const newToken = await refreshAccessToken();

    if (!newToken) {
      return Promise.reject(error);
    }

    originalRequest.headers = originalRequest.headers ?? {};
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

export interface PredictionAccuracy {
  available: boolean;
  reason?: string;
  resolved_predictions?: number;
  active_predictions?: number;
  correct_predictions?: number;
  incorrect_predictions?: number;
  false_positives?: number;
  false_negatives?: number;
  accuracy?: number | null;
  average_lead_time_seconds?: number | null;
}

export async function fetchPredictionAccuracy(): Promise<PredictionAccuracy> {
  const { data } = await api.get<PredictionAccuracy>(
    "/cognitive/predictions/accuracy"
  );
  return data;
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
  const { data } = await api.get<CognitiveIncident[]>("/cognitive/incidents");
  return data ?? [];
}

export interface CognitiveIncidentReplay {
  incident?: CognitiveIncident;
  timeline?: CognitiveIncidentTimelineEntry[];
  replay?: {
    evidence_count?: number;
    reconstruction?: "recorded" | "reconstructed";
    evidence_text?: string | null;
    outcome?: {
      status?: string;
      verified?: boolean;
      note?: string;
    };
    counterfactual?: {
      status?: string;
      note?: string;
    };
  };
}

export async function fetchCognitiveIncidentReplay(incidentId: string) {
  const { data } = await api.get<CognitiveIncidentReplay>(
    `/cognitive/incidents/${encodeURIComponent(incidentId)}/replay`,
  );
  return data;
}

export async function acknowledgeAlert(alertId: string) {
  const { data } = await api.post(
    `/alerts/${encodeURIComponent(alertId)}/acknowledge`
  );
  return data;
}

export async function snoozeAlert(alertId: string, minutes = 30) {
  const { data } = await api.post(
    `/alerts/${encodeURIComponent(alertId)}/snooze`,
    { minutes }
  );
  return data;
}

export async function unsnoozeAlert(alertId: string) {
  const { data } = await api.delete(
    `/alerts/${encodeURIComponent(alertId)}/snooze`
  );
  return data;
}

export async function suppressAlertProcess(processName: string, minutes = 60) {
  const { data } = await api.post("/alerts/process-suppressions", {
    process_name: processName,
    minutes,
  });
  return data;
}

export async function unsuppressAlertProcess(processName: string) {
  const { data } = await api.delete(
    `/alerts/process-suppressions/${encodeURIComponent(processName)}`
  );
  return data;
}

export async function fetchAlertProcessSuppressions() {
  const { data } = await api.get<
    Array<{ process_name: string; suppressed_until: number }>
  >("/alerts/process-suppressions");
  return Array.isArray(data) ? data : [];
}

export interface CognitiveIncidentTimelineEntry {
  t_minus_mins?: number;
  time_str?: string;
  event?: string;
  metric?: string;
  value?: number | null;
  unit?: string;
  significance?: string;
}

export interface CognitiveIncidentContributor {
  pid?: number;
  name?: string;
  recent_cpu_percent?: number;
  recent_memory_percent?: number;
  cpu_growth_percent?: number;
  memory_growth_percent?: number;
  observations?: number;
  memory_risk?: "normal" | "elevated" | "high";
  explanation?: string;
  confidence?: number;
}

export interface CognitiveIncident {
  incident_id?: string;
  type?: string;
  description?: string;
  occurred_at?: number;
  occurred_str?: string;
  timeline?: CognitiveIncidentTimelineEntry[];
  plain_timeline?: string;
  likely_contributors?: CognitiveIncidentContributor[];
}

export async function fetchCognitiveNotifications() {
  const { data } = await api.get("/cognitive/notifications");
  return data ?? [];
}

export interface DesktopSettings {
  available: boolean;
  configured?: boolean;
  background_monitoring?: boolean;
}

export async function fetchDesktopSettings(): Promise<DesktopSettings> {
  const { data } = await api.get<DesktopSettings>("/desktop/settings");
  return data;
}

export async function saveDesktopSettings(
  backgroundMonitoring: boolean
): Promise<DesktopSettings> {
  const { data } = await api.put<DesktopSettings>("/desktop/settings", {
    background_monitoring: backgroundMonitoring,
  });
  return data;
}

export async function quitDesktopApp(): Promise<void> {
  const desktopApi = window.pywebview?.api;
  if (!desktopApi) {
    throw new Error("The desktop application API is unavailable.");
  }
  await desktopApi.quit_cvis();
}
