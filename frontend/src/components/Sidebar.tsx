import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  LogOut,
  MessageSquare,
  PanelLeftClose,
  Pencil,
  Plus,
  Settings,
  Trash2,
} from "lucide-react";
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
  onClose: () => void;
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
  onClose,
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
        <span className="thread-title">
          <MessageSquare size={14} />
          {t.title}
        </span>
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
            className="icon-button subtle"
            title="Delete thread"
            aria-label="Delete thread"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(t.id);
            }}
          >
            <Trash2 size={14} />
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
            {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
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
              className="icon-button subtle"
              title="Rename initiative"
              aria-label="Rename initiative"
              onClick={(e) => {
                e.stopPropagation();
                const name = window.prompt("Rename initiative", initiative.name);
                if (name && name.trim()) onUpdateInitiative(initiative.id, { name: name.trim() });
              }}
            >
              <Pencil size={14} />
            </button>
            <button
              className="icon-button subtle"
              title="New thread in this initiative"
              aria-label="New thread in this initiative"
              onClick={(e) => {
                e.stopPropagation();
                onNew(initiative.id);
              }}
            >
              <Plus size={14} />
            </button>
            <button
              className="icon-button subtle"
              title="Delete initiative (threads are kept)"
              aria-label="Delete initiative"
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm(`Delete initiative "${initiative.name}"? Its threads are kept.`))
                  onDeleteInitiative(initiative.id);
              }}
            >
              <Trash2 size={14} />
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
        <span className="sidebar-header-actions">
          <button className="new-chat-button" onClick={() => onNew()}>
            <Plus size={16} />
            New
          </button>
          <button
            className="icon-button subtle"
            title="Collapse Deep Harness"
            aria-label="Collapse Deep Harness"
            onClick={onClose}
          >
            <PanelLeftClose size={16} />
          </button>
        </span>
      </div>

      <div className="initiatives-bar">
        <span className="section-label">Initiatives</span>
        {newName === null ? (
          <button
            className="icon-button subtle"
            title="New initiative"
            aria-label="New initiative"
            onClick={() => setNewName("")}
          >
            <Plus size={14} />
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
                className="icon-button subtle"
                title="New unfiled thread"
                aria-label="New unfiled thread"
                onClick={(e) => {
                  e.stopPropagation();
                  onNew(null);
                }}
              >
                <Plus size={14} />
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
        <div className="account-chip">
          <span className="avatar-dot">{username.slice(0, 1).toUpperCase()}</span>
          <span>@{username}</span>
        </div>
        <div className="footer-actions">
          <button className="icon-button subtle" title="Compute settings" aria-label="Compute settings" onClick={onSettings}>
            <Settings size={16} />
          </button>
          <button className="icon-button subtle" title="Sign out" aria-label="Sign out" onClick={onLogout}>
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
