import { useEffect, useState } from "react";
import { listFiles, readFile } from "../api";
import type { FileEntry, TodoItem } from "../types";

const STATUS_ICON: Record<string, string> = {
  pending: "○",
  in_progress: "◐",
  completed: "●",
};

export function SidePanel({ todos, refreshKey }: { todos: TodoItem[]; refreshKey: number }) {
  const [tab, setTab] = useState<"tasks" | "files">("tasks");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [openFile, setOpenFile] = useState<{ path: string; content: string } | null>(null);

  useEffect(() => {
    if (tab === "files") {
      listFiles().then(setFiles).catch(() => setFiles([]));
    }
  }, [tab, refreshKey]);

  return (
    <aside className="side-panel">
      <div className="tabs">
        <button className={tab === "tasks" ? "tab active" : "tab"} onClick={() => setTab("tasks")}>
          Plan
        </button>
        <button className={tab === "files" ? "tab active" : "tab"} onClick={() => setTab("files")}>
          Workspace
        </button>
      </div>

      {tab === "tasks" && (
        <div className="panel-body">
          {todos.length === 0 && <div className="muted pad">No plan yet</div>}
          {todos.map((t, i) => (
            <div key={i} className={`todo ${t.status}`}>
              <span className="todo-icon">{STATUS_ICON[t.status] ?? "○"}</span>
              {t.content}
            </div>
          ))}
        </div>
      )}

      {tab === "files" && !openFile && (
        <div className="panel-body">
          {files.length === 0 && <div className="muted pad">Workspace is empty</div>}
          {files.map((f) => (
            <div
              key={f.path}
              className="file-row"
              onClick={() =>
                readFile(f.path).then((content) => setOpenFile({ path: f.path, content }))
              }
            >
              <span className="file-path">{f.path}</span>
              <span className="muted">{(f.size / 1024).toFixed(1)} kB</span>
            </div>
          ))}
        </div>
      )}

      {tab === "files" && openFile && (
        <div className="panel-body file-view">
          <div className="file-view-header">
            <button className="ghost small" onClick={() => setOpenFile(null)}>
              ← back
            </button>
            <span className="file-path">{openFile.path}</span>
          </div>
          <pre>{openFile.content}</pre>
        </div>
      )}
    </aside>
  );
}
