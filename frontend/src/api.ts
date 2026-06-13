import type {
  ComputeSettings,
  ExperimentRecord,
  FileEntry,
  HistoryMessage,
  StreamEvent,
  ThreadInfo,
  TodoItem,
} from "./types";

const TOKEN_KEY = "deep-harness-token";
const USER_KEY = "deep-harness-user";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername(): string | null {
  return localStorage.getItem(USER_KEY);
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function headers(): Record<string, string> {
  const token = getToken();
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: { ...headers(), ...init.headers } });
  if (response.status === 401) {
    clearAuth();
    window.location.reload();
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function authenticate(
  mode: "login" | "register",
  username: string,
  password: string,
): Promise<void> {
  const data = await request<{ token: string; username: string }>(`/api/auth/${mode}`, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, data.username);
}

export async function logout(): Promise<void> {
  // Revoke server-side first; clear local credentials regardless of outcome.
  try {
    await fetch("/api/auth/logout", { method: "POST", headers: headers() });
  } finally {
    clearAuth();
  }
}

export const listThreads = () => request<ThreadInfo[]>("/api/threads");
export const createThread = () =>
  request<ThreadInfo>("/api/threads", { method: "POST", body: JSON.stringify({}) });
export const deleteThread = (id: string) =>
  request<void>(`/api/threads/${id}`, { method: "DELETE" });
export const getHistory = (id: string) => request<HistoryMessage[]>(`/api/threads/${id}/messages`);
export const getTodos = (id: string) => request<TodoItem[]>(`/api/threads/${id}/todos`);
export const listFiles = () => request<FileEntry[]>("/api/files");
export const getComputeSettings = () => request<ComputeSettings>("/api/settings");
export const updateComputeSettings = (body: {
  compute_backend: string;
  gpu_type: string;
  modal_token_id: string | null;
  modal_token_secret: string | null;
  gate_plan: boolean;
  gate_training_jobs: boolean;
  gate_shell: boolean;
}) => request<ComputeSettings>("/api/settings", { method: "PUT", body: JSON.stringify(body) });

export const listExperiments = () => request<ExperimentRecord[]>("/api/experiments");

export interface FileContent {
  kind: "text" | "image";
  text?: string;
  objectUrl?: string;
}

/** Read a workspace file: images come back as a blob object URL for <img>. */
export async function readFile(path: string): Promise<FileContent> {
  const response = await fetch(`/api/files/${encodeURIComponent(path)}`, { headers: headers() });
  if (!response.ok) throw new Error(`cannot read ${path}`);
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.startsWith("image/")) {
    return { kind: "image", objectUrl: URL.createObjectURL(await response.blob()) };
  }
  return { kind: "text", text: await response.text() };
}

async function consumeSSE(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    throw new Error(`stream failed: HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (line.startsWith("data: ")) {
        onEvent(JSON.parse(line.slice(6)) as StreamEvent);
      }
    }
  }
}

/** POST a message and invoke `onEvent` for every SSE event until `done`. */
export const streamMessage = (
  threadId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
) => consumeSSE(`/api/threads/${threadId}/messages`, { content }, onEvent);

/** Resolve an approval gate and stream the continuation. `message` carries
 * plan-change feedback for a `respond` decision. */
export const resumeMessage = (
  threadId: string,
  decision: "approve" | "reject" | "respond",
  message: string | null,
  onEvent: (event: StreamEvent) => void,
) => consumeSSE(`/api/threads/${threadId}/resume`, { decision, message }, onEvent);
