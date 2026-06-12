import type { FileEntry, HistoryMessage, StreamEvent, ThreadInfo, TodoItem } from "./types";

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

export const listThreads = () => request<ThreadInfo[]>("/api/threads");
export const createThread = () =>
  request<ThreadInfo>("/api/threads", { method: "POST", body: JSON.stringify({}) });
export const deleteThread = (id: string) =>
  request<void>(`/api/threads/${id}`, { method: "DELETE" });
export const getHistory = (id: string) => request<HistoryMessage[]>(`/api/threads/${id}/messages`);
export const getTodos = (id: string) => request<TodoItem[]>(`/api/threads/${id}/todos`);
export const listFiles = () => request<FileEntry[]>("/api/files");

export async function readFile(path: string): Promise<string> {
  const response = await fetch(`/api/files/${encodeURIComponent(path)}`, { headers: headers() });
  if (!response.ok) throw new Error(`cannot read ${path}`);
  return response.text();
}

/** POST a message and invoke `onEvent` for every SSE event until `done`. */
export async function streamMessage(
  threadId: string,
  content: string,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(`/api/threads/${threadId}/messages`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ content }),
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
