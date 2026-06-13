export interface ThreadInfo {
  id: string;
  title: string;
  initiative_id?: string | null;
  created_at: number;
  updated_at: number;
}

export type InitiativeStatus = "active" | "completed" | "archived";

export interface Initiative {
  id: string;
  name: string;
  goal: string;
  status: InitiativeStatus;
  created_at: number;
  updated_at: number;
  thread_count: number;
  experiment_count: number;
}

export interface TodoItem {
  content: string;
  status: string;
}

export interface FileEntry {
  path: string;
  size: number;
}

export interface HistoryMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls: { name: string; args: Record<string, unknown> }[];
  tool_name?: string | null;
}

export interface ActionRequest {
  name: string;
  args: Record<string, unknown>;
  description: string;
}

export type StreamEvent =
  | { type: "token"; text: string; source: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown>; source: string }
  | { type: "tool_result"; name: string; preview: string; source: string }
  | { type: "todos"; items: TodoItem[] }
  | { type: "message"; role: string; content: string; source: string }
  | { type: "approval_required"; requests: ActionRequest[] }
  | { type: "error"; detail: string }
  | { type: "done" };

export type Decision = "approve" | "reject" | "respond";

export interface ComputeSettings {
  compute_backend: "local" | "modal" | string;
  gpu_type: string;
  modal_token_id: string;
  modal_token_secret_set: boolean;
  gate_plan: boolean;
  gate_training_jobs: boolean;
  gate_shell: boolean;
}

export interface ExperimentRecord {
  id: string;
  name: string;
  timestamp: number;
  metrics: Record<string, unknown>;
  params: Record<string, unknown>;
  artifacts: string[];
  notes: string;
  initiative_id?: string | null;
  initiative_name?: string | null;
}

export type ChatItem =
  | { kind: "user"; content: string }
  | { kind: "assistant"; content: string; source: string }
  | { kind: "activity"; label: string; detail: string; source: string };
