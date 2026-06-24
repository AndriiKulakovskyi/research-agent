import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApprovalCard } from "./ApprovalCard";

describe("ApprovalCard checkpoint revision", () => {
  it("renders scientific checkpoint context and sends revision feedback", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn();

    render(
      <ApprovalCard
        request={{
          name: "researcher_checkpoint",
          args: {
            summary: "Endpoint candidates are MADRS change and remission.",
            decision_needed: "Choose the primary endpoint.",
            options: ["MADRS change", "remission"],
            artifact_paths: ["research/PLAN.md"],
          },
          description: "",
          allowed_decisions: ["approve", "reject", "respond"],
          revision_supported: true,
        }}
        busy={false}
        onDecide={onDecide}
      />,
    );

    expect(screen.getByText("Endpoint candidates are MADRS change and remission.")).toBeInTheDocument();
    expect(screen.getByText("Choose the primary endpoint.")).toBeInTheDocument();
    expect(screen.getByText("MADRS change")).toBeInTheDocument();
    expect(screen.getByText("research/PLAN.md")).toBeInTheDocument();

    const revise = screen.getByRole("button", { name: /request revision/i });
    expect(revise).toBeDisabled();
    await user.type(
      screen.getByPlaceholderText(/describe the revision/i),
      "Use MADRS change and update validation todos.",
    );
    await user.click(revise);

    expect(onDecide).toHaveBeenCalledWith(
      "respond",
      "Use MADRS change and update validation todos.",
    );
  });

  it("keeps execution gates approve/reject only", () => {
    render(
      <ApprovalCard
        request={{
          name: "run_training_job",
          args: { script_path: "train.py" },
          description: "",
          allowed_decisions: ["approve", "reject"],
          revision_supported: false,
        }}
        busy={false}
        onDecide={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /request revision/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/describe the revision/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve & run/i })).toBeInTheDocument();
  });

  it("shows revision controls for scientific checkpoints even when metadata is stale", async () => {
    const user = userEvent.setup();
    const onDecide = vi.fn();

    render(
      <ApprovalCard
        request={{
          name: "researcher_checkpoint",
          args: {
            summary: "Need endpoint steering.",
            decision_needed: "Choose endpoint.",
          },
          description: "",
          allowed_decisions: ["approve", "reject"],
          revision_supported: false,
        }}
        busy={false}
        onDecide={onDecide}
      />,
    );

    expect(screen.queryByRole("button", { name: /approve & run/i })).not.toBeInTheDocument();
    await user.type(screen.getByPlaceholderText(/describe the revision/i), "Change endpoint.");
    await user.click(screen.getByRole("button", { name: /request revision/i }));

    expect(onDecide).toHaveBeenCalledWith("respond", "Change endpoint.");
  });
});
