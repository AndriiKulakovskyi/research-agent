import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { listExperiments, listFiles, readFile, type FileContent } from "../api";
import type { ExperimentRecord, FileEntry, Initiative, TodoItem } from "../types";

const STATUS_ICON: Record<string, string> = {
  pending: "○",
  in_progress: "◐",
  completed: "●",
};

// Distinct, dark-theme-friendly colors for the compared runs.
const RUN_COLORS = ["#e0a458", "#5aa9e6", "#7bd88f", "#d98ad9", "#e0635a", "#b0b85a"];

type Tab = "tasks" | "files" | "experiments";

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
}: {
  todos: TodoItem[];
  refreshKey: number;
  initiative: Initiative | null;
}) {
  const [tab, setTab] = useState<Tab>("tasks");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [experiments, setExperiments] = useState<ExperimentRecord[]>([]);
  const [openFile, setOpenFile] = useState<({ path: string } & FileContent) | null>(null);
  const [compare, setCompare] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (tab === "files") listFiles().then(setFiles).catch(() => setFiles([]));
    if (tab === "experiments")
      listExperiments(initiative?.id).then(setExperiments).catch(() => setExperiments([]));
  }, [tab, refreshKey, initiative?.id]);

  // Reset comparison selection whenever the visible run set changes.
  useEffect(() => {
    setSelected(new Set());
    setCompare(false);
  }, [initiative?.id, refreshKey]);

  async function open(path: string) {
    const content = await readFile(path);
    setOpenFile({ path, ...content });
    setTab("files");
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
    <aside className="side-panel">
      {initiative && (
        <div className="initiative-overview">
          <div className="initiative-overview-head">
            <span className="initiative-overview-name">{initiative.name}</span>
            <span className={`status-pill status-${initiative.status}`}>{initiative.status}</span>
          </div>
          {initiative.goal && <div className="muted initiative-goal">{initiative.goal}</div>}
          <div className="muted initiative-counts">
            {initiative.thread_count} thread{initiative.thread_count === 1 ? "" : "s"} ·{" "}
            {initiative.experiment_count} run{initiative.experiment_count === 1 ? "" : "s"}
          </div>
        </div>
      )}

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
              evaluation run here{initiative ? " for this initiative" : ""}.
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
                  Compare ({selected.size})
                </button>
              ) : (
                <button className="ghost small" onClick={() => setCompare(false)}>
                  ← back to list
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
                  <button key={a} className="link artifact-link" onClick={() => open(a)}>
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
                      <XAxis dataKey="run" tick={{ fill: "#8494a8", fontSize: 10 }} hide />
                      <YAxis tick={{ fill: "#8494a8", fontSize: 10 }} width={40} />
                      <Tooltip
                        cursor={{ fill: "rgba(255,255,255,0.04)" }}
                        contentStyle={{
                          background: "#1a212c",
                          border: "1px solid #2c3645",
                          borderRadius: 6,
                          fontSize: 12,
                        }}
                        labelStyle={{ color: "#dfe6ef" }}
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
