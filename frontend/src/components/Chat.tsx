import { useEffect, useRef, useState } from "react";
import { Beaker, Folder, ListChecks, PanelLeftOpen, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ActionRequest, ChatItem, Decision, Initiative, InspectorTab, TodoItem } from "../types";
import { ApprovalCard } from "./ApprovalCard";

type ActivityItem = Extract<ChatItem, { kind: "activity" }>;
type RenderBlock = ChatItem | { kind: "activity-group"; key: string; items: ActivityItem[] };

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

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children, href }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
        table: ({ children }) => (
          <div className="markdown-table-wrap">
            <table>{children}</table>
          </div>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function isGroupedActivity(item: ChatItem): item is ActivityItem {
  return item.kind === "activity" && !item.label.toLowerCase().includes("error");
}

function groupChatItems(items: ChatItem[]): RenderBlock[] {
  const blocks: RenderBlock[] = [];
  let pending: ActivityItem[] = [];
  let pendingStart = 0;

  function flush() {
    if (pending.length === 0) return;
    blocks.push({ kind: "activity-group", key: `activity-${pendingStart}`, items: pending });
    pending = [];
  }

  items.forEach((item, index) => {
    if (isGroupedActivity(item)) {
      if (pending.length === 0) pendingStart = index;
      pending.push(item);
      return;
    }

    flush();
    blocks.push(item);
  });
  flush();

  return blocks;
}

function activityName(label: string) {
  return label.replace(/^[→✓]\s*/, "").trim();
}

function ActivityGroup({ items, live }: { items: ActivityItem[]; live: boolean }) {
  const toolNames = Array.from(new Set(items.map((item) => activityName(item.label)).filter(Boolean)));
  const visibleNames = toolNames.slice(0, 3).join(", ");
  const extraNames = toolNames.length > 3 ? ` +${toolNames.length - 3}` : "";
  const eventLabel = `${items.length} event${items.length === 1 ? "" : "s"}`;
  const latest = toolNames[toolNames.length - 1] ?? "tools";

  return (
    <details className={`activity-group ${live ? "live" : ""}`}>
      <summary>
        <span className="activity-group-main">
          <span className="activity-group-title">{live ? "Agent is using tools" : "Agent used tools"}</span>
          <span className="activity-group-names">{visibleNames ? `${visibleNames}${extraNames}` : latest}</span>
        </span>
        <span className="activity-group-count">{eventLabel}</span>
      </summary>
      <div className="activity-group-body">
        {items.map((item, index) => (
          <div className="activity-row" key={`${item.label}-${index}`}>
            <span className="activity-label">{item.label}</span>
            {item.source !== "agent" && <span className="source-tag">{item.source}</span>}
            {item.detail && <span className="activity-detail">{item.detail}</span>}
          </div>
        ))}
      </div>
    </details>
  );
}

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
  const blocks = groupChatItems(items);

  return (
    <section className="chat">
      <header className="chat-header">
        <div className="chat-title-group">
          <div className="chat-eyebrow">
            <Sparkles size={14} strokeWidth={2} />
            Precision Psychiatry
          </div>
          <div className="chat-title">{initiative?.name ?? "Research workspace"}</div>
          {initiative?.goal && <div className="chat-subtitle">{initiative.goal}</div>}
        </div>
        <div className="chat-actions" aria-label="Workspace panels">
          <button
            className={`icon-button labeled ${sidebarOpen ? "active" : ""}`}
            title={sidebarOpen ? "Collapse sidebar" : "Open sidebar"}
            onClick={onToggleSidebar}
            aria-pressed={sidebarOpen}
          >
            <PanelLeftOpen size={17} />
            <span>Co-Scientist</span>
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
        {blocks.map((item, i) => {
          if (item.kind === "activity-group") {
            const live = busy && !streamingText && i === blocks.length - 1;
            return <ActivityGroup key={item.key} items={item.items} live={live} />;
          }
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
                <div className="markdown-content">
                  <MarkdownContent content={item.content} />
                </div>
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
            <div className="markdown-content">
              <MarkdownContent content={streamingText} />
            </div>
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
