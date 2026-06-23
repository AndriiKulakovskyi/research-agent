import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Circle,
  FileText,
  FlaskConical,
  Folder,
  ListChecks,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { listExperiments, listFiles, readFile, type FileContent } from "../api";
import type { ExperimentRecord, FileEntry, Initiative, InspectorTab, TodoItem } from "../types";

const STATUS_ICON: Record<string, LucideIcon> = {
  pending: Circle,
  in_progress: ListChecks,
  completed: CheckCircle2,
};

const RUN_COLORS = ["#0f766e", "#2563eb", "#9333ea", "#ea580c", "#dc2626", "#4b5563"];

function asNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function runLabel(e: ExperimentRecord): string {
  return `${e.name} · ${e.id}`;
}

export function SidePanel({
  todos,
  refreshKey,
  initiative,
  open,
  activeTab,
  onTabChange,
  onClose,
}: {
  todos: TodoItem[];
  refreshKey: number;
  initiative: Initiative | null;
  open: boolean;
  activeTab: InspectorTab;
  onTabChange: (tab: InspectorTab) => void;
  onClose: () => void;
}) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [openFile, setOpenFile] = useState<({ path: string } & FileContent) | null>(null);
  const [compare, setCompare] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!open) return;
    if (activeTab === "files") listFiles().then(setFiles).catch(() => setFiles([]));
    if (activeTab === "experiments")
      listExperiments(initiative?.id).then(setExperiments).catch(() => setExperiments([]));
  }, [activeTab, open, refreshKey, initiative?.id]);

  // Reset comparison selection whenever the visible run set changes.
  useEffect(() => {
    setSelected(new Set());
    setCompare(false);
  }, [initiative?.id, refreshKey]);

  async function openWorkspaceFile(path: string) {
    const content = await readFile(path);
    setOpenFile({ path, ...content });
    onTabChange("files");
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const selectedRuns = useMemo(
    () => experiments.filter((e) => selected.has(e.id)),
    [experiments, selected],
  );

  // Per-metric chart data: one chart per numeric metric, one bar per selected run.
  const metricCharts = useMemo(() => {
    const keys = new Set<string>();
    for (const e of selectedRuns)
      for (const [k, v] of Object.entries(e.metrics ?? {}))
        if (asNumber(v) !== null) keys.add(k);
    return [...keys].map((key) => ({
      key,
      data: selectedRuns.map((e, i) => ({
        run: runLabel(e),
        value: asNumber((e.metrics ?? {})[key]),
        color: RUN_COLORS[i % RUN_COLORS.length],
      })),
    }));
  }, [selectedRuns]);

  // Param keys that actually differ across the selected runs (the interesting ones).
  const paramRows = useMemo(() => {
    const keys = new Set<string>();
    for (const e of selectedRuns) for (const k of Object.keys(e.params ?? {})) keys.add(k);
    return [...keys].map((key) => {
      const values = selectedRuns.map((e) => (e.params ?? {})[key]);
      const differs = new Set(values.map((v) => JSON.stringify(v ?? null))).size > 1;
      return { key, values, differs };
    });
  }, [selectedRuns]);

  return (
    <aside className={`side-panel ${open ? "open" : ""}`} aria-hidden={!open}>
      <div className="inspector-header">
        <div>
          <div className="inspector-title">Inspector</div>
          {initiative && (
            <div className="inspector-context">
              {initiative.name} · {initiative.thread_count} thread
              {initiative.thread_count === 1 ? "" : "s"} · {initiative.experiment_count} run
              {initiative.experiment_count === 1 ? "" : "s"}
            </div>
          )}
        </div>
        <button className="icon-button" onClick={onClose} title="Close inspector" aria-label="Close inspector">
          <X size={18} />
        </button>
      </div>

      <div className="tabs">
        <button
          className={activeTab === "plan" ? "tab active" : "tab"}
          onClick={() => onTabChange("plan")}
        >
          <ListChecks size={16} />
          Plan
        </button>
        <button
          className={activeTab === "files" ? "tab active" : "tab"}
          onClick={() => onTabChange("files")}
        >
          <Folder size={16} />
          Workspace
        </button>
        <button
          className={activeTab === "experiments" ? "tab active" : "tab"}
          onClick={() => onTabChange("experiments")}
        >
          <FlaskConical size={16} />
          Experiments
        </button>
      </div>

      {activeTab === "plan" && (
        <div className="panel-body">
          {todos.length === 0 && <div className="muted pad">No plan yet</div>}
          {todos.map((t, i) => (
            <div key={i} className={`todo ${t.status}`}>
              <span className="todo-icon">
                {(() => {
                  const Icon = STATUS_ICON[t.status] ?? Circle;
                  return <Icon size={16} />;
                })()}
              </span>
              {t.content}
            </div>
          ))}
        </div>
      )}

      {activeTab === "files" && !openFile && (
        <div className="panel-body">
          {files.length === 0 && <div className="muted pad">Workspace is empty</div>}
          {files.map((f) => (
            <div key={f.path} className="file-row" onClick={() => openWorkspaceFile(f.path)}>
              <span className="file-path">
                <FileText size={15} />
                {f.path}
              </span>
              <span className="muted">{(f.size / 1024).toFixed(1)} kB</span>
            </div>
          ))}
        </div>
      )}

      {activeTab === "files" && openFile && (
        <div className="panel-body file-view">
          <div className="file-view-header">
            <button className="ghost small" onClick={() => setOpenFile(null)}>
              <ArrowLeft size={15} />
              back
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

      {activeTab === "experiments" && (
        <div className="panel-body">
          {experiments.length === 0 && (
            <div className="muted pad">
              No experiments logged yet{initiative ? " for this initiative" : ""}.
            </div>
          )}

          {experiments.length > 0 && (
            <div className="compare-bar">
              {!compare ? (
                <button
                  className="primary small"
                  disabled={selected.size < 2}
                  onClick={() => setCompare(true)}
                  title={selected.size < 2 ? "Select at least two runs" : "Compare selected runs"}
                >
                  <BarChart3 size={14} />
                  Compare ({selected.size})
                </button>
              ) : (
                <button className="ghost small" onClick={() => setCompare(false)}>
                  <ArrowLeft size={14} />
                  back to list
                </button>
              )}
            </div>
          )}

          {!compare &&
            experiments.map((e) => (
              <div key={e.id} className="experiment">
                <div className="experiment-head">
                  <label className="experiment-select" onClick={(ev) => ev.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(e.id)}
                      onChange={() => toggleSelected(e.id)}
                    />
                    <span className="experiment-name">{e.name}</span>
                  </label>
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
                  <button key={a} className="link artifact-link" onClick={() => openWorkspaceFile(a)}>
                    {a}
                  </button>
                ))}
              </div>
            ))}

          {compare && (
            <div className="compare-view">
              <div className="compare-legend">
                {selectedRuns.map((e, i) => (
                  <span key={e.id} className="legend-item">
                    <span
                      className="legend-swatch"
                      style={{ background: RUN_COLORS[i % RUN_COLORS.length] }}
                    />
                    {runLabel(e)}
                  </span>
                ))}
              </div>

              {metricCharts.length === 0 && (
                <div className="muted pad">No numeric metrics to chart for these runs.</div>
              )}
              {metricCharts.map((chart) => (
                <div key={chart.key} className="compare-chart">
                  <div className="compare-chart-title">{chart.key}</div>
                  <ResponsiveContainer width="100%" height={150}>
                    <BarChart data={chart.data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
                      <XAxis dataKey="run" tick={{ fill: "#6b7280", fontSize: 10 }} hide />
                      <YAxis tick={{ fill: "#6b7280", fontSize: 10 }} width={40} />
                      <Tooltip
                        cursor={{ fill: "rgba(15,23,42,0.04)" }}
                        contentStyle={{
                          background: "#ffffff",
                          border: "1px solid #d9dde5",
                          borderRadius: 6,
                          fontSize: 12,
                        }}
                        labelStyle={{ color: "#111827" }}
                      />
                      <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                        {chart.data.map((d, i) => (
                          <Cell key={i} fill={d.color} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ))}

              {paramRows.length > 0 && (
                <div className="params-diff">
                  <div className="compare-chart-title">Parameters</div>
                  <table>
                    <thead>
                      <tr>
                        <th>param</th>
                        {selectedRuns.map((e) => (
                          <th key={e.id}>{e.id}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {paramRows.map((row) => (
                        <tr key={row.key} className={row.differs ? "differs" : ""}>
                          <td>{row.key}</td>
                          {row.values.map((v, i) => (
                            <td key={i}>{v === undefined ? "—" : String(v)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
