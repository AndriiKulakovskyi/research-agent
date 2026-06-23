import { useEffect, useRef, useState } from "react";
import { Beaker, Folder, ListChecks, PanelLeftOpen, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ActionRequest, ChatItem, Decision, Initiative, InspectorTab, TodoItem } from "../types";
import { ApprovalCard } from "./ApprovalCard";

interface Props {
  items: ChatItem[];
  streamingText: string;
  busy: boolean;
  onSend: (content: string) => void;
  pendingApproval: ActionRequest | null;
  onDecide: (decision: Decision, message: string | null) => void;
  initiative: Initiative | null;
  todos: TodoItem[];
  sidebarOpen: boolean;
  inspectorOpen: boolean;
  activeInspectorTab: InspectorTab;
  onToggleSidebar: () => void;
  onOpenInspector: (tab: InspectorTab) => void;
}

const INSPECTOR_ACTIONS: { tab: InspectorTab; label: string; icon: LucideIcon }[] = [
  { tab: "plan", label: "Plan", icon: ListChecks },
  { tab: "files", label: "Files", icon: Folder },
  { tab: "experiments", label: "Runs", icon: Beaker },
];

export function Chat({
  items,
  streamingText,
  busy,
  onSend,
  pendingApproval,
  onDecide,
  initiative,
  todos,
  sidebarOpen,
  inspectorOpen,
  activeInspectorTab,
  onToggleSidebar,
  onOpenInspector,
}: Props) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, streamingText]);

  function submit() {
    const content = draft.trim();
    if (!content || busy) return;
    setDraft("");
    onSend(content);
  }

  const completedTodos = todos.filter((t) => t.status === "completed").length;

  return (
    <section className="chat">
      <header className="chat-header">
        <div className="chat-title-group">
          <div className="chat-eyebrow">
            <Sparkles size={14} strokeWidth={2} />
            Deep Harness
          </div>
          <div className="chat-title">{initiative?.name ?? "Research workspace"}</div>
          {initiative?.goal && <div className="chat-subtitle">{initiative.goal}</div>}
        </div>
        <div className="chat-actions" aria-label="Workspace panels">
          <button
            className={`icon-button labeled ${sidebarOpen ? "active" : ""}`}
            title={sidebarOpen ? "Collapse Deep Harness" : "Open Deep Harness"}
            onClick={onToggleSidebar}
            aria-pressed={sidebarOpen}
          >
            <PanelLeftOpen size={17} />
            <span>Deep Harness</span>
          </button>
          {INSPECTOR_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.tab}
                className={`icon-button labeled ${
                  inspectorOpen && activeInspectorTab === action.tab ? "active" : ""
                }`}
                title={`Open ${action.label}`}
                onClick={() => onOpenInspector(action.tab)}
                aria-pressed={inspectorOpen && activeInspectorTab === action.tab}
              >
                <Icon size={17} />
                <span>{action.label}</span>
              </button>
            );
          })}
          {todos.length > 0 && (
            <span className="progress-pill">
              {completedTodos}/{todos.length}
            </span>
          )}
        </div>
      </header>
      <div className="messages">
        {items.length === 0 && !busy && (
          <div className="empty-hint">
            <div className="empty-mark">
              <Sparkles size={22} />
            </div>
            <h1>What should we work on?</h1>
          </div>
        )}
        {items.map((item, i) => {
          if (item.kind === "user") {
            return (
              <div key={i} className="bubble user">
                {item.content}
              </div>
            );
          }
          if (item.kind === "assistant") {
            return (
              <div key={i} className="bubble assistant">
                {item.source !== "agent" && <span className="source-tag">{item.source}</span>}
                <pre>{item.content}</pre>
              </div>
            );
          }
          return (
            <div key={i} className="activity">
              <span className="activity-label">{item.label}</span>
              {item.source !== "agent" && <span className="source-tag">{item.source}</span>}
              {item.detail && <span className="activity-detail">{item.detail}</span>}
            </div>
          );
        })}
        {streamingText && (
          <div className="bubble assistant streaming">
            <pre>{streamingText}</pre>
          </div>
        )}
        {busy && !streamingText && !pendingApproval && <div className="thinking">working…</div>}
        <div ref={bottomRef} />
      </div>
      {pendingApproval ? (
        <div className="composer approval">
          <ApprovalCard request={pendingApproval} busy={busy} onDecide={onDecide} />
        </div>
      ) : (
        <div className="composer">
          <textarea
            value={draft}
            placeholder={busy ? "Agent is working…" : "Enter your question"}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={3}
            disabled={busy}
          />
          <button
            className="send-button"
            onClick={submit}
            disabled={busy || !draft.trim()}
            title="Send"
            aria-label="Send message"
          >
            <span>Send</span>
          </button>
        </div>
      )}
    </section>
  );
}
