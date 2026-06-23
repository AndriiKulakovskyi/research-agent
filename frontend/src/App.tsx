import { useCallback, useEffect, useRef, useState } from "react";
import {
  createInitiative,
  createThread,
  deleteInitiative,
  deleteThread,
  getHistory,
  getToken,
  getTodos,
  getUsername,
  listInitiatives,
  listThreads,
  logout,
  resumeMessage,
  setThreadInitiative,
  streamMessage,
  updateInitiative,
} from "./api";
import { Chat } from "./components/Chat";
import { Login } from "./components/Login";
import { SettingsDialog } from "./components/SettingsDialog";
import { Sidebar } from "./components/Sidebar";
import { SidePanel } from "./components/SidePanel";
import type {
  ActionRequest,
  ChatItem,
  Decision,
  Initiative,
  InspectorTab,
  InitiativeStatus,
  StreamEvent,
  ThreadInfo,
  TodoItem,
} from "./types";

export default function App() {
  const [authed, setAuthed] = useState(() => getToken() !== null);
  const [threads, setThreads] = useState<ThreadInfo[]>([]);
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeInitiativeId, setActiveInitiativeId] = useState<string | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const [pendingApproval, setPendingApproval] = useState<ActionRequest | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("plan");
  const streamBuffer = useRef("");

  const refreshThreads = useCallback(async () => {
    setThreads(await listThreads());
  }, []);

  const refreshInitiatives = useCallback(async () => {
    setInitiatives(await listInitiatives());
  }, []);

  useEffect(() => {
    if (authed) {
      refreshThreads().catch(() => undefined);
      refreshInitiatives().catch(() => undefined);
    }
  }, [authed, refreshThreads, refreshInitiatives]);

  const openThread = useCallback(
    async (id: string) => {
      setActiveId(id);
      // Scope the inspector to the thread's initiative.
      setActiveInitiativeId(threads.find((t) => t.id === id)?.initiative_id ?? null);
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
    },
    [threads],
  );

  function openInspector(tab: InspectorTab) {
    setInspectorTab(tab);
    setInspectorOpen(true);
  }

  async function newThread(initiativeId?: string | null) {
    const t = await createThread(initiativeId);
    await refreshThreads();
    setActiveInitiativeId(initiativeId ?? null);
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

  const handleEvent = useCallback((event: StreamEvent) => {
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
      case "approval_required":
        // The run paused on a gate; surface the first request for the user.
        setPendingApproval(event.requests[0] ?? null);
        break;
      case "error":
        setItems((prev) => [
          ...prev,
          { kind: "activity", label: "⚠ error", detail: event.detail, source: "agent" },
        ]);
        break;
    }
  }, []);

  const finishStream = useCallback(() => {
    setBusy(false);
    setStreamingText("");
    streamBuffer.current = "";
    setRefreshKey((k) => k + 1);
    refreshThreads().catch(() => undefined);
    refreshInitiatives().catch(() => undefined);
  }, [refreshThreads, refreshInitiatives]);

  async function moveThread(id: string, initiativeId: string | null) {
    await setThreadInitiative(id, initiativeId);
    if (id === activeId) setActiveInitiativeId(initiativeId);
    await Promise.all([refreshThreads(), refreshInitiatives()]);
  }

  async function addInitiative(name: string, goal = "") {
    const created = await createInitiative(name, goal);
    await refreshInitiatives();
    setActiveInitiativeId(created.id);
  }

  async function changeInitiative(
    id: string,
    patch: { name?: string; goal?: string; status?: InitiativeStatus },
  ) {
    await updateInitiative(id, patch);
    await refreshInitiatives();
  }

  async function removeInitiative(id: string) {
    await deleteInitiative(id);
    if (activeInitiativeId === id) setActiveInitiativeId(null);
    await Promise.all([refreshInitiatives(), refreshThreads()]);
  }

  async function send(content: string) {
    let threadId = activeId;
    if (!threadId) {
      // A thread started by typing inherits the currently selected initiative.
      const t = await createThread(activeInitiativeId);
      threadId = t.id;
      setActiveId(threadId);
    }
    setItems((prev) => [...prev, { kind: "user", content }]);
    setBusy(true);
    streamBuffer.current = "";
    try {
      await streamMessage(threadId, content, handleEvent);
    } finally {
      finishStream();
    }
  }

  async function decide(decision: Decision, message: string | null) {
    if (!activeId) return;
    const request = pendingApproval;
    setPendingApproval(null);
    setItems((prev) => [
      ...prev,
      {
        kind: "activity",
        label: decision === "approve" ? "✓ approved" : decision === "reject" ? "✕ rejected" : "✎ changes requested",
        detail: message ?? request?.name ?? "",
        source: "agent",
      },
    ]);
    setBusy(true);
    streamBuffer.current = "";
    try {
      await resumeMessage(activeId, decision, message, handleEvent);
    } finally {
      finishStream();
    }
  }

  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;

  const activeInitiative =
    initiatives.find((i) => i.id === activeInitiativeId) ?? null;

  return (
    <div className="layout">
      <Sidebar
        threads={threads}
        initiatives={initiatives}
        activeId={activeId}
        activeInitiativeId={activeInitiativeId}
        username={getUsername() ?? ""}
        onSelect={openThread}
        onSelectInitiative={setActiveInitiativeId}
        onNew={newThread}
        onNewInitiative={addInitiative}
        onUpdateInitiative={changeInitiative}
        onDeleteInitiative={removeInitiative}
        onMoveThread={moveThread}
        onDelete={removeThread}
        onLogout={() => {
          logout().finally(() => setAuthed(false));
        }}
        onSettings={() => setShowSettings(true)}
      />
      <Chat
        items={items}
        streamingText={streamingText}
        busy={busy}
        onSend={send}
        pendingApproval={pendingApproval}
        onDecide={decide}
        initiative={activeInitiative}
        todos={todos}
        inspectorOpen={inspectorOpen}
        onOpenInspector={openInspector}
      />
      {inspectorOpen && (
        <button
          className="inspector-scrim"
          aria-label="Close inspector"
          onClick={() => setInspectorOpen(false)}
        />
      )}
      <SidePanel
        todos={todos}
        refreshKey={refreshKey}
        initiative={activeInitiative}
        open={inspectorOpen}
        activeTab={inspectorTab}
        onTabChange={setInspectorTab}
        onClose={() => setInspectorOpen(false)}
      />
      {showSettings && <SettingsDialog onClose={() => setShowSettings(false)} />}
    </div>
  );
}
