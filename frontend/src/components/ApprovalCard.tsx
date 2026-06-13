import { useEffect, useState } from "react";
import { readFile } from "../api";
import type { ActionRequest, Decision } from "../types";

interface Props {
  request: ActionRequest;
  busy: boolean;
  onDecide: (decision: Decision, message: string | null) => void;
}

/** Plan-review card: shows the agent's plan summary + the written PLAN.md, with
 * Approve / Request-changes (feedback) controls. */
function PlanCard({ request, busy, onDecide }: Props) {
  const summary = String(request.args.summary ?? "");
  const planPath = String(request.args.plan_path ?? "research/PLAN.md");
  const [plan, setPlan] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");

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
      <textarea
        className="feedback"
        rows={2}
        placeholder="Optional: request changes (e.g. add a baseline, use 5-fold CV)"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        disabled={busy}
      />
      <div className="approval-actions">
        <button
          className="ghost"
          disabled={busy || !feedback.trim()}
          onClick={() => onDecide("respond", feedback.trim())}
        >
          Request changes
        </button>
        <button className="primary" disabled={busy} onClick={() => onDecide("approve", null)}>
          Approve &amp; proceed
        </button>
      </div>
    </div>
  );
}

/** Tool-approval card: confirm a gated tool call (e.g. a training job). */
function ToolCard({ request, busy, onDecide }: Props) {
  return (
    <div className="approval-card">
      <div className="approval-title">
        Approve <code>{request.name}</code>?
      </div>
      <pre className="approval-args">{JSON.stringify(request.args, null, 2)}</pre>
      <div className="approval-actions">
        <button className="ghost" disabled={busy} onClick={() => onDecide("reject", null)}>
          Reject
        </button>
        <button className="primary" disabled={busy} onClick={() => onDecide("approve", null)}>
          Approve &amp; run
        </button>
      </div>
    </div>
  );
}

export function ApprovalCard(props: Props) {
  return props.request.name === "submit_plan" ? <PlanCard {...props} /> : <ToolCard {...props} />;
}
