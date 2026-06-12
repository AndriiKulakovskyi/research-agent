import { useEffect, useState } from "react";
import { listExperiments, listFiles, readFile, type FileContent } from "../api";
import type { ExperimentRecord, FileEntry, TodoItem } from "../types";

const STATUS_ICON: Record<string, string> = {
  pending: "○",
  in_progress: "◐",
  completed: "●",
};

type Tab = "tasks" | "files" | "experiments";

export function SidePanel({ todos, refreshKey }: { todos: TodoItem[]; refreshKey: number }) {
  const [tab, setTab] = useState<Tab>("tasks");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [openFile, setOpenFile] = useState<({ path: string } & FileContent) | null>(null);

  useEffect(() => {
    if (tab === "files") listFiles().then(setFiles).catch(() => setFiles([]));
    if (tab === "experiments")
      listExperiments().then(setExperiments).catch(() => setExperiments([]));
  }, [tab, refreshKey]);

  async function open(path: string) {
    const content = await readFile(path);
    setOpenFile({ path, ...content });
    setTab("files");
  }

  return (
    <aside className="side-panel">
      <div className="tabs">
        <button className={tab === "tasks" ? "tab active" : "tab"} onClick={() => setTab("tasks")}>
          Plan
        </button>
        <button className={tab === "files" ? "tab active" : "tab"} onClick={() => setTab("files")}>
          Workspace
        </button>
        <button
          className={tab === "experiments" ? "tab active" : "tab"}
          onClick={() => setTab("experiments")}
        >
          Experiments
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
            <div key={f.path} className="file-row" onClick={() => open(f.path)}>
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
          {openFile.kind === "image" ? (
            <img className="file-image" src={openFile.objectUrl} alt={openFile.path} />
          ) : (
            <pre>{openFile.text}</pre>
          )}
        </div>
      )}

      {tab === "experiments" && (
        <div className="panel-body">
          {experiments.length === 0 && (
            <div className="muted pad">
              No experiments logged yet — the agent records every training and
              evaluation run here.
            </div>
          )}
          {experiments.map((e) => (
            <div key={e.id} className="experiment">
              <div className="experiment-head">
                <span className="experiment-name">{e.name}</span>
                <span className="muted">
                  {new Date(e.timestamp * 1000).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <div className="metric-chips">
                {Object.entries(e.metrics ?? {}).map(([k, v]) => (
                  <span key={k} className="chip">
                    {k}: {String(v)}
                  </span>
                ))}
              </div>
              {e.notes && <div className="muted experiment-notes">{e.notes}</div>}
              {(e.artifacts ?? []).map((a) => (
                <button key={a} className="link artifact-link" onClick={() => open(a)}>
                  {a}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}
