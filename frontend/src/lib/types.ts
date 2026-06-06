export type Counts = Record<string, number>;

export interface BatchItem {
  item_id: string;
  patient_id: string;
  request_type: string;
  med_id: string;
  status: string;
  current_node: string | null;
  error: string | null;
  model_used: string | null;
  updated_at: number | null;
}

export interface AuditEvent {
  server: string;
  tool: string;
  ok: boolean;
  error: string | null;
  ts: number;
}

export interface ChaosEntry {
  server: string;
  tool: string;
  mode: string;
  latency_s: number;
}

export interface NodeEvent {
  node: string;
  status: string | null;
  detail?: string | null;
}

export interface InteractiveBody {
  item_id?: string;
  patient_id: string;
  request_type: string;
  med_id: string;
  raw_text?: string;
}

export interface NarrativeStep {
  icon: string;
  title: string;
  detail?: string;
}

export interface HistoryFact {
  med: string;
  request_type: string;
  outcome: string;
  reason: string;
  ts: number;
}

export interface ReturningPatient {
  visits: number;
  last_ts: number;
  history: HistoryFact[];
}

export interface RequestNarrative {
  status: string;
  degraded: boolean;
  med: string;
  steps: NarrativeStep[];
  patient_message: string;
  clinic_flag: string | null;
  suggested_alternative: { med: string; reason: string } | null;
  returning_patient?: ReturningPatient | null;
}

export interface RequestSummary {
  request_id: string;
  patient_id: string;
  patient_name: string;
  med: string;
  status: string;
  narrative: RequestNarrative;
  created_at: number;
}

export interface SystemState {
  degraded: boolean;
  primary_model: string;
  active_model: string;
  llm_killed: boolean;
  gateway_failover?: boolean;
  active_chaos: ChaosEntry[];
}

export interface ResilienceEvent {
  run_id: string | null;
  ts: number;
  layer: "llm" | "tool" | "memory";
  target: string;
  attempt: number;
  mode: string | null;
  backoff_ms: number;
  outcome: "fail" | "recovered" | "degraded";
  recovered_by: string | null;
}

export interface ResilienceSummary {
  attempts: number;
  recovered: boolean;
  degraded: boolean;
}

export interface XrayRun {
  request_id: string;
  patient_id: string;
  thread_id: string;
  status: string | null;
  model_used: string | null;
  steps: { node: string; detail: string }[];
  resilience?: ResilienceSummary;
  created_at: number;
}
