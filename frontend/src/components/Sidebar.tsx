import type { ThreadInfo } from "../types";

interface Props {
  threads: ThreadInfo[];
  activeId: string | null;
  username: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
  onSettings: () => void;
}

export function Sidebar({
  threads,
  activeId,
  username,
  onSelect,
  onNew,
  onDelete,
  onLogout,
  onSettings,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span className="brand">Deep Harness</span>
        <button className="primary small" onClick={onNew}>
          + New
        </button>
      </div>
      <nav className="thread-list">
        {threads.map((t) => (
          <div
            key={t.id}
            className={`thread-item ${t.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(t.id)}
          >
            <span className="thread-title">{t.title}</span>
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
          </div>
        ))}
        {threads.length === 0 && <div className="muted pad">No conversations yet</div>}
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
