import { useEffect, useState } from "react";
import { Check, FileCheck2, Play, RotateCcw, X } from "lucide-react";
import { readFile } from "../api";
import type { ActionRequest, Decision } from "../types";

interface Props {
  request: ActionRequest;
  busy: boolean;
  onDecide: (decision: Decision, message: string | null) => void;
}

const SCIENTIFIC_REVISION_GATES = new Set([
  "submit_plan",
  "researcher_checkpoint",
  "submit_final_report",
]);

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function canDecide(request: ActionRequest, decision: Decision) {
  if (decision === "respond" && SCIENTIFIC_REVISION_GATES.has(request.name)) return true;
  return request.allowed_decisions?.includes(decision) ?? true;
}

function supportsRevision(request: ActionRequest) {
  return request.revision_supported === true || SCIENTIFIC_REVISION_GATES.has(request.name);
}

function RevisionTextarea({
  feedback,
  busy,
  onChange,
}: {
  feedback: string;
  busy: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <textarea
      className="feedback"
      rows={2}
      placeholder="Required: describe the revision the agent should make"
      value={feedback}
      onChange={(e) => onChange(e.target.value)}
      disabled={busy}
    />
  );
}

/** Plan-review card: shows the agent's plan summary + the written PLAN.md, with
 * Approve / Request revision (feedback) controls. */
function PlanCard({ request, busy, onDecide }: Props) {
  const summary = String(request.args.summary ?? "");
  const planPath = String(request.args.plan_path ?? "research/PLAN.md");
  const [plan, setPlan] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const canRevise = supportsRevision(request) && canDecide(request, "respond");

  useEffect(() => {
    readFile(planPath)
      .then((c) => setPlan(c.text ?? "(plan file is empty)"))
      .catch(() => setPlan("(could not load the plan file)"));
  }, [planPath]);

  return (
    <div className="approval-card plan">
      <div className="approval-title">Research plan — review required</div>
      {summary && <p className="approval-summary">{summary}</p>}
      <details open>
        <summary className="muted">{planPath}</summary>
        <pre className="plan-body">{plan ?? "loading…"}</pre>
      </details>
      {canRevise && (
        <RevisionTextarea feedback={feedback} busy={busy} onChange={setFeedback} />
      )}
      <div className="approval-actions">
        {canDecide(request, "reject") && (
          <button className="ghost action-button" disabled={busy} onClick={() => onDecide("reject", null)}>
            <X size={15} />
            Reject
          </button>
        )}
        {canRevise && (
          <button
            className="ghost action-button"
            disabled={busy || !feedback.trim()}
            onClick={() => onDecide("respond", feedback.trim())}
          >
            <RotateCcw size={15} />
            Request revision
          </button>
        )}
        <button
          className="primary action-button"
          disabled={busy || !canDecide(request, "approve")}
          onClick={() => onDecide("approve", null)}
        >
          <FileCheck2 size={16} />
          Approve &amp; proceed
        </button>
      </div>
    </div>
  );
}

function ScientificCheckpointCard({ request, busy, onDecide }: Props) {
  const [feedback, setFeedback] = useState("");
  const summary = String(request.args.summary ?? "");
  const decisionNeeded = String(request.args.decision_needed ?? "");
  const options = stringList(request.args.options);
  const artifactPaths = stringList(request.args.artifact_paths);
  const reportPath = request.args.report_path ? String(request.args.report_path) : "";
  const title =
    request.name === "submit_final_report" ? "Final report release" : "Researcher checkpoint";

  return (
    <div className="approval-card">
      <div className="approval-title">
        {title} <code>{request.name}</code>
      </div>
      {summary && (
        <div className="approval-field">
          <span>Summary</span>
          <p>{summary}</p>
        </div>
      )}
      {decisionNeeded && (
        <div className="approval-field">
          <span>Decision needed</span>
          <p>{decisionNeeded}</p>
        </div>
      )}
      {options.length > 0 && (
        <div className="approval-field">
          <span>Options</span>
          <ul className="approval-list">
            {options.map((option) => (
              <li key={option}>{option}</li>
            ))}
          </ul>
        </div>
      )}
      {(artifactPaths.length > 0 || reportPath) && (
        <div className="approval-field">
          <span>Artifacts</span>
          <ul className="approval-list">
            {reportPath && <li>{reportPath}</li>}
            {artifactPaths.map((path) => (
              <li key={path}>{path}</li>
            ))}
          </ul>
        </div>
      )}
      <RevisionTextarea feedback={feedback} busy={busy} onChange={setFeedback} />
      <div className="approval-actions">
        {canDecide(request, "reject") && (
          <button className="ghost action-button" disabled={busy} onClick={() => onDecide("reject", null)}>
            <X size={15} />
            Reject
          </button>
        )}
        <button
          className="ghost action-button"
          disabled={busy || !feedback.trim() || !canDecide(request, "respond")}
          onClick={() => onDecide("respond", feedback.trim())}
        >
          <RotateCcw size={15} />
          Request revision
        </button>
        <button
          className="primary action-button"
          disabled={busy || !canDecide(request, "approve")}
          onClick={() => onDecide("approve", null)}
        >
          <Check size={16} />
          Approve &amp; proceed
        </button>
      </div>
    </div>
  );
}

/** Tool-approval card: confirm a gated tool call (e.g. a training job). */
function ToolCard({ request, busy, onDecide }: Props) {
  const title =
    request.name === "researcher_checkpoint"
      ? "Researcher checkpoint"
      : request.name === "face_export_analysis_dataset"
        ? "FACE export"
        : request.name === "submit_final_report"
          ? "Final report release"
          : `Approve ${request.name}?`;

  return (
    <div className="approval-card">
      <div className="approval-title">
        {title} <code>{request.name}</code>
      </div>
      <pre className="approval-args">{JSON.stringify(request.args, null, 2)}</pre>
      <div className="approval-actions">
        {canDecide(request, "reject") && (
          <button className="ghost action-button" disabled={busy} onClick={() => onDecide("reject", null)}>
            <X size={15} />
            Reject
          </button>
        )}
        <button
          className="primary action-button"
          disabled={busy || !canDecide(request, "approve")}
          onClick={() => onDecide("approve", null)}
        >
          {request.name === "execute" ? <Play size={16} /> : <Check size={16} />}
          Approve &amp; run
        </button>
      </div>
    </div>
  );
}

export function ApprovalCard(props: Props) {
  if (props.request.name === "submit_plan") return <PlanCard {...props} />;
  if (supportsRevision(props.request)) return <ScientificCheckpointCard {...props} />;
  return <ToolCard {...props} />;
}
