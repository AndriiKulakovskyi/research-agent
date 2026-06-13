import { useState } from "react";
import type { Initiative, InitiativeStatus, ThreadInfo } from "../types";

interface Props {
  threads: ThreadInfo[];
  initiatives: Initiative[];
  activeId: string | null;
  activeInitiativeId: string | null;
  username: string;
  onSelect: (id: string) => void;
  onSelectInitiative: (id: string | null) => void;
  onNew: (initiativeId?: string | null) => void;
  onNewInitiative: (name: string, goal?: string) => void;
  onUpdateInitiative: (
    id: string,
    patch: { name?: string; goal?: string; status?: InitiativeStatus },
  ) => void;
  onDeleteInitiative: (id: string) => void;
  onMoveThread: (id: string, initiativeId: string | null) => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
  onSettings: () => void;
}

const STATUSES: InitiativeStatus[] = ["active", "completed", "archived"];

export function Sidebar({
  threads,
  initiatives,
  activeId,
  activeInitiativeId,
  username,
  onSelect,
  onSelectInitiative,
  onNew,
  onNewInitiative,
  onUpdateInitiative,
  onDeleteInitiative,
  onMoveThread,
  onDelete,
  onLogout,
  onSettings,
}: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [newName, setNewName] = useState<string | null>(null);

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const threadsFor = (initiativeId: string | null) =>
    threads.filter((t) => (t.initiative_id ?? null) === initiativeId);

  const knownIds = new Set(initiatives.map((i) => i.id));
  const unfiled = threads.filter((t) => !t.initiative_id || !knownIds.has(t.initiative_id));

  function submitNew() {
    const name = (newName ?? "").trim();
    if (name) onNewInitiative(name);
    setNewName(null);
  }

  function renderThread(t: ThreadInfo) {
    return (
      <div
        key={t.id}
        className={`thread-item ${t.id === activeId ? "active" : ""}`}
        onClick={() => onSelect(t.id)}
      >
        <span className="thread-title">{t.title}</span>
        <span className="thread-controls">
          <select
            className="move-select"
            title="Move to initiative"
            value={t.initiative_id ?? ""}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => onMoveThread(t.id, e.target.value || null)}
          >
            <option value="">Unfiled</option>
            {initiatives.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
          <button
            className="ghost small"
            title="Delete thread"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(t.id);
            }}
          >
            ✕
          </button>
        </span>
      </div>
    );
  }

  function renderInitiative(initiative: Initiative) {
    const isCollapsed = collapsed.has(initiative.id);
    const groupThreads = threadsFor(initiative.id);
    return (
      <div key={initiative.id} className="initiative-group">
        <div
          className={`initiative-header ${initiative.id === activeInitiativeId ? "active" : ""}`}
          onClick={() => onSelectInitiative(initiative.id)}
        >
          <button
            className="chevron"
            title={isCollapsed ? "Expand" : "Collapse"}
            onClick={(e) => {
              e.stopPropagation();
              toggle(initiative.id);
            }}
          >
            {isCollapsed ? "▸" : "▾"}
          </button>
          <span className="initiative-name">{initiative.name}</span>
          <span className={`status-pill status-${initiative.status}`}>{initiative.status}</span>
          <span className="muted count">{groupThreads.length}</span>
          <span className="initiative-controls">
            <select
              className="status-select"
              title="Change status"
              value={initiative.status}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) =>
                onUpdateInitiative(initiative.id, { status: e.target.value as InitiativeStatus })
              }
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <button
              className="ghost small"
              title="Rename initiative"
              onClick={(e) => {
                e.stopPropagation();
                const name = window.prompt("Rename initiative", initiative.name);
                if (name && name.trim()) onUpdateInitiative(initiative.id, { name: name.trim() });
              }}
            >
              ✎
            </button>
            <button
              className="ghost small"
              title="New thread in this initiative"
              onClick={(e) => {
                e.stopPropagation();
                onNew(initiative.id);
              }}
            >
              +
            </button>
            <button
              className="ghost small"
              title="Delete initiative (threads are kept)"
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm(`Delete initiative "${initiative.name}"? Its threads are kept.`))
                  onDeleteInitiative(initiative.id);
              }}
            >
              ✕
            </button>
          </span>
        </div>
        {!isCollapsed && (
          <div className="initiative-threads">
            {groupThreads.map(renderThread)}
            {groupThreads.length === 0 && (
              <div className="muted pad small-pad">No threads yet</div>
            )}
          </div>
        )}
      </div>
    );
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="brand">Deep Harness</span>
        <button className="primary small" onClick={() => onNew()}>
          + New
        </button>
      </div>

      <div className="initiatives-bar">
        <span className="section-label">Initiatives</span>
        {newName === null ? (
          <button className="ghost small" title="New initiative" onClick={() => setNewName("")}>
            + New initiative
          </button>
        ) : (
          <input
            className="initiative-input"
            autoFocus
            placeholder="Initiative name…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submitNew();
              if (e.key === "Escape") setNewName(null);
            }}
            onBlur={submitNew}
          />
        )}
      </div>

      <nav className="thread-list">
        {initiatives.map(renderInitiative)}

        <div className="initiative-group">
          <div
            className={`initiative-header unfiled ${activeInitiativeId === null ? "active" : ""}`}
            onClick={() => onSelectInitiative(null)}
          >
            <span className="initiative-name">Unfiled</span>
            <span className="muted count">{unfiled.length}</span>
            <span className="initiative-controls">
              <button
                className="ghost small"
                title="New unfiled thread"
                onClick={(e) => {
                  e.stopPropagation();
                  onNew(null);
                }}
              >
                +
              </button>
            </span>
          </div>
          <div className="initiative-threads">{unfiled.map(renderThread)}</div>
        </div>

        {threads.length === 0 && initiatives.length === 0 && (
          <div className="muted pad">No conversations yet</div>
        )}
      </nav>

      <div className="sidebar-footer">
        <span className="muted">@{username}</span>
        <span>
          <button className="ghost small" title="Compute settings" onClick={onSettings}>
            ⚙ Settings
          </button>
          <button className="ghost small" onClick={onLogout}>
            Sign out
          </button>
        </span>
      </div>
    </aside>
  );
}
