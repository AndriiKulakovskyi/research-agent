import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Chat } from "./Chat";

const cohortTable = `Configured FACE cohorts are visit-level by default; unique-patient counts are reported explicitly.

| Sub-cohort | Visit-level rows | Unique patients | Flat-file columns | Canonical table family | Metadata warnings |
|---|---:|---:|---:|---|---|
| BP - Bipolar | 21,343 | 6,252 | 2,223 | \`reactor_gold_bp_test_ea\` | BP contains duplicate table-family variants. |
| DR - Depression | 980 | 324 | 2,374 | \`reactor_gold_dr_test_ea\` | None reported. |`;

describe("Chat markdown rendering", () => {
  it("renders assistant markdown tables and inline code as structured content", () => {
    const { container } = render(
      <Chat
        items={[{ kind: "assistant", content: cohortTable, source: "agent" }]}
        streamingText=""
        busy={false}
        onSend={vi.fn()}
        pendingApproval={null}
        onDecide={vi.fn()}
        initiative={null}
        todos={[]}
        sidebarOpen={false}
        inspectorOpen={false}
        activeInspectorTab="plan"
        onToggleSidebar={vi.fn()}
        onOpenInspector={vi.fn()}
      />,
    );

    expect(screen.getByText(/Configured FACE cohorts/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Sub-cohort" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "BP - Bipolar" })).toBeInTheDocument();
    expect(screen.getByText("reactor_gold_bp_test_ea").tagName).toBe("CODE");
    expect(container.querySelector(".markdown-content table")).toBeInTheDocument();
    expect(screen.queryByText(/\| Sub-cohort \| Visit-level rows \|/)).not.toBeInTheDocument();
  });

  it("groups consecutive tool activity into one collapsible block", () => {
    const { container } = render(
      <Chat
        items={[
          { kind: "user", content: "Check FACE feasibility" },
          {
            kind: "activity",
            label: "→ face_feasibility",
            detail: '{"subcohort":"SZ","variables":["madrs01"]}',
            source: "tools",
          },
          {
            kind: "activity",
            label: "✓ face_feasibility",
            detail: '{"eligible_rows":5933}',
            source: "tools",
          },
          {
            kind: "activity",
            label: "→ face_profile_variables",
            detail: '{"subcohort":"SZ","variables":["madrs01","madrs02"]}',
            source: "tools",
          },
          { kind: "assistant", content: "Done.", source: "agent" },
        ]}
        streamingText=""
        busy={false}
        onSend={vi.fn()}
        pendingApproval={null}
        onDecide={vi.fn()}
        initiative={null}
        todos={[]}
        sidebarOpen={false}
        inspectorOpen={false}
        activeInspectorTab="plan"
        onToggleSidebar={vi.fn()}
        onOpenInspector={vi.fn()}
      />,
    );

    expect(container.querySelectorAll(".activity-group")).toHaveLength(1);
    expect(container.querySelectorAll(".messages > .activity")).toHaveLength(0);
    expect(screen.getByText("Agent used tools")).toBeInTheDocument();
    expect(screen.getByText("3 events")).toBeInTheDocument();
    expect(screen.getByText("face_feasibility, face_profile_variables")).toBeInTheDocument();
    expect(screen.getByText("Done.")).toBeInTheDocument();
  });
});
