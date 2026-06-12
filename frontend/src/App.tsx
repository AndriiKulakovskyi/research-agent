import { useCallback, useEffect, useRef, useState } from "react";
import {
  createThread,
  deleteThread,
  getHistory,
  getToken,
  getTodos,
  getUsername,
  listThreads,
  logout,
  streamMessage,
} from "./api";
import { Chat } from "./components/Chat";
import { Login } from "./components/Login";
import { Sidebar } from "./components/Sidebar";
import { SidePanel } from "./components/SidePanel";
import type { ChatItem, ThreadInfo, TodoItem } from "./types";

export default function App() {
  const [authed, setAuthed] = useState(() => getToken() !== null);
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const streamBuffer = useRef("");

  const refreshThreads = useCallback(async () => {
    setThreads(await listThreads());
  }, []);

  useEffect(() => {
    if (authed) refreshThreads().catch(() => undefined);
  }, [authed, refreshThreads]);

  const openThread = useCallback(async (id: string) => {
    setActiveId(id);
    setStreamingText("");
    streamBuffer.current = "";
    const [history, threadTodos] = await Promise.all([getHistory(id), getTodos(id)]);
    setTodos(threadTodos);
    setItems(
      history.map((m): ChatItem => {
        if (m.role === "user") return { kind: "user", content: m.content };
        if (m.role === "tool") {
          return {
            kind: "activity",
            label: m.tool_name ?? "tool",
            detail: m.content.slice(0, 120),
            source: "agent",
          };
        }
        const calls = m.tool_calls.map((c) => c.name).join(", ");
        return m.content
          ? { kind: "assistant", content: m.content, source: "agent" }
          : { kind: "activity", label: `→ ${calls}`, detail: "", source: "agent" };
      }),
    );
  }, []);

  async function newThread() {
    const t = await createThread();
    await refreshThreads();
    await openThread(t.id);
  }

  async function removeThread(id: string) {
    await deleteThread(id);
    if (id === activeId) {
      setActiveId(null);
      setItems([]);
      setTodos([]);
    }
    await refreshThreads();
  }

  async function send(content: string) {
    let threadId = activeId;
    if (!threadId) {
      const t = await createThread();
      threadId = t.id;
      setActiveId(threadId);
    }
    setItems((prev) => [...prev, { kind: "user", content }]);
    setBusy(true);
    streamBuffer.current = "";
    try {
      await streamMessage(threadId, content, (event) => {
        switch (event.type) {
          case "token":
            if (event.source === "agent") {
              streamBuffer.current += event.text;
              setStreamingText(streamBuffer.current);
            }
            break;
          case "tool_call":
            setItems((prev) => [
              ...prev,
              {
                kind: "activity",
                label: `→ ${event.name}`,
                detail: JSON.stringify(event.args).slice(0, 120),
                source: event.source,
              },
            ]);
            break;
          case "tool_result":
            setItems((prev) => [
              ...prev,
              {
                kind: "activity",
                label: `✓ ${event.name}`,
                detail: event.preview.slice(0, 120),
                source: event.source,
              },
            ]);
            break;
          case "todos":
            setTodos(event.items);
            break;
          case "message":
            streamBuffer.current = "";
            setStreamingText("");
            if (event.source === "agent") {
              setItems((prev) => [
                ...prev,
                { kind: "assistant", content: event.content, source: event.source },
              ]);
            }
            break;
          case "error":
            setItems((prev) => [
              ...prev,
              { kind: "activity", label: "⚠ error", detail: event.detail, source: "agent" },
            ]);
            break;
        }
      });
    } finally {
      setBusy(false);
      setStreamingText("");
      streamBuffer.current = "";
      setRefreshKey((k) => k + 1);
      refreshThreads().catch(() => undefined);
    }
  }

  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;

  return (
    <div className="layout">
      <Sidebar
        threads={threads}
        activeId={activeId}
        username={getUsername() ?? ""}
        onSelect={openThread}
        onNew={newThread}
        onDelete={removeThread}
        onLogout={() => {
          logout().finally(() => setAuthed(false));
        }}
      />
      <Chat items={items} streamingText={streamingText} busy={busy} onSend={send} />
      <SidePanel todos={todos} refreshKey={refreshKey} />
    </div>
  );
}
