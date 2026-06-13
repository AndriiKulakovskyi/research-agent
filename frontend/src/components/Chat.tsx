import { useEffect, useRef, useState } from "react";
import type { ActionRequest, ChatItem, Decision } from "../types";
import { ApprovalCard } from "./ApprovalCard";

interface Props {
  items: ChatItem[];
  streamingText: string;
  busy: boolean;
  onSend: (content: string) => void;
  pendingApproval: ActionRequest | null;
  onDecide: (decision: Decision, message: string | null) => void;
}

export function Chat({ items, streamingText, busy, onSend, pendingApproval, onDecide }: Props) {
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

  return (
    <section className="chat">
      <div className="messages">
        {items.length === 0 && !busy && (
          <div className="empty-hint">
            Ask the agent to analyze data, build pipelines, write code, query the
            knowledge graph, or document variable semantics.
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
            placeholder={busy ? "Agent is working…" : "Send a task to the agent"}
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
          <button className="primary" onClick={submit} disabled={busy || !draft.trim()}>
            Send
          </button>
        </div>
      )}
    </section>
  );
}
