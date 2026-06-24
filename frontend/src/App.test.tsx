import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { StreamEvent } from "./types";

const { persistedTodos, streamedTodos } = vi.hoisted(() => ({
  persistedTodos: [
    { content: "Ground FACE BP metadata", status: "completed" },
    { content: "Check variable feasibility", status: "in_progress" },
  ],
  streamedTodos: [
    { content: "Build cohort plan", status: "in_progress" },
    { content: "Run FACE feasibility", status: "pending" },
  ],
}));

vi.mock("./api", () => ({
  getToken: vi.fn(() => "token"),
  getUsername: vi.fn(() => "alice"),
  listThreads: vi.fn(async () => [
    {
      id: "thread-1",
      title: "FACE BP thread",
      initiative_id: null,
      created_at: 1,
      updated_at: 1,
    },
  ]),
  listInitiatives: vi.fn(async () => []),
  getHistory: vi.fn(async () => []),
  getTodos: vi.fn(async (id: string) => (id === "thread-stream" ? streamedTodos : persistedTodos)),
  createThread: vi.fn(async () => ({
    id: "thread-stream",
    title: "New conversation",
    initiative_id: null,
    created_at: 2,
    updated_at: 2,
  })),
  deleteThread: vi.fn(async () => undefined),
  logout: vi.fn(async () => undefined),
  resumeMessage: vi.fn(async () => undefined),
  setThreadInitiative: vi.fn(async () => ({
    id: "thread-1",
    title: "FACE BP thread",
    initiative_id: null,
    created_at: 1,
    updated_at: 1,
  })),
  streamMessage: vi.fn(
    async (_threadId: string, _content: string, onEvent: (event: StreamEvent) => void) => {
      onEvent({
        type: "todos",
        items: streamedTodos,
      });
      onEvent({ type: "message", role: "assistant", content: "Plan started.", source: "agent" });
      onEvent({ type: "done" });
    },
  ),
  updateInitiative: vi.fn(async () => undefined),
  createInitiative: vi.fn(async () => ({
    id: "i1",
    name: "Initiative",
    goal: "",
    status: "active",
    created_at: 1,
    updated_at: 1,
    thread_count: 0,
    experiment_count: 0,
  })),
  deleteInitiative: vi.fn(async () => undefined),
  listFiles: vi.fn(async () => []),
  listExperiments: vi.fn(async () => []),
  readFile: vi.fn(async () => ({ kind: "text", text: "" })),
  getComputeSettings: vi.fn(async () => ({
    compute_backend: "local",
    gpu_type: "A10G",
    modal_token_id: "",
    modal_token_secret_set: false,
    gate_plan: true,
    gate_researcher_checkpoint: true,
    gate_cohort_export: true,
    gate_training_jobs: true,
    gate_shell: true,
    gate_report_release: true,
  })),
  updateComputeSettings: vi.fn(async (body: unknown) => body),
}));

describe("App todo plan behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders persisted todos when reopening a thread", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByText("FACE BP thread"));

    await waitFor(() => expect(screen.getAllByText("1/2").length).toBeGreaterThan(0));
    expect(screen.getByText(/Active 2: Check variable feasibility/)).toBeInTheDocument();
    expect(screen.getByText("Ground FACE BP metadata")).toBeInTheDocument();
  });

  it("updates and reopens the Plan tab from streamed todos events", async () => {
    const user = userEvent.setup();
    const { container } = render(<App />);

    await screen.findByText("FACE BP thread");
    const closeButtons = screen.getAllByLabelText("Close inspector");
    await user.click(closeButtons[closeButtons.length - 1]);
    expect(container.querySelector(".side-panel")).not.toHaveClass("open");

    await user.type(screen.getByPlaceholderText("Enter your question"), "Check FACE BP feasibility");
    await user.click(screen.getByRole("button", { name: "Send message" }));

    await waitFor(() => expect(screen.getAllByText("0/2").length).toBeGreaterThan(0));
    expect(container.querySelector(".side-panel")).toHaveClass("open");
    expect(screen.getByText(/Active 1: Build cohort plan/)).toBeInTheDocument();
    expect(screen.getByText("Run FACE feasibility")).toBeInTheDocument();
  });
});
