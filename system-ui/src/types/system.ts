export type TemporalMetric = {
  pattern: string;
  slope: number;
  confidence: number;
};

export type Temporal = {
  cpu: TemporalMetric;
  memory: TemporalMetric;
  disk: TemporalMetric;
};

export type Causal = {
  type: string;
  confidence: number;
  reason: string;
};

export type Decision = {
  urgency: string;
  action: string;
  time_window: string;
  reason: string;
};

export type SystemData = {
  cpu: number;
  memory: number;
  disk: number;

  posture: string;

  temporal: Temporal;
  causal: Causal;
  decision: Decision;

  explanation: string;
};

// 🔥 IMPORTANT: force module export (fixes Vite edge case)
export {};
