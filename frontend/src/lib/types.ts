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
