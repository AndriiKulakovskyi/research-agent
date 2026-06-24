"""Human-in-the-loop approval gates at the build_agent level (no API calls)."""

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from deep_harness.agent import build_agent
from deep_harness.server.streaming import pending_approvals
from tests.conftest import ScriptedModel, tool_call_message

CFG = {"configurable": {"thread_id": "t"}, "recursion_limit": 100}


def _agent(settings, replies, gates):
    return build_agent(
        settings,
        model=ScriptedModel(replies=replies),
        checkpointer=InMemorySaver(),
        interrupt_on=gates,
    )


def test_gated_training_job_pauses_then_approves(settings):
    agent = _agent(
        settings,
        [
            tool_call_message("run_training_job", {"script_path": "train.py"}),
            AIMessage(content="Training complete."),
        ],
        {"run_training_job": True},
    )
    # First turn pauses at the gate
    agent.invoke({"messages": [{"role": "user", "content": "train it"}]}, config=CFG)
    state = agent.get_state(CFG)
    assert state.next, "run should be paused"
    requests = pending_approvals(state)
    assert requests and requests[0]["name"] == "run_training_job"
    assert requests[0]["args"]["script_path"] == "train.py"
    assert requests[0]["allowed_decisions"]
    assert requests[0]["revision_supported"] is False

    # Approve → the tool runs, run completes
    agent.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=CFG)
    final = agent.get_state(CFG)
    assert not final.next
    tool_msgs = [m for m in final.values["messages"] if getattr(m, "type", "") == "tool"]
    assert any("train.py" in str(m.content) for m in tool_msgs)


def test_gated_tool_reject_skips_execution(settings):
    agent = _agent(
        settings,
        [
            tool_call_message("run_training_job", {"script_path": "train.py"}),
            AIMessage(content="Okay, not running it."),
        ],
        {"run_training_job": True},
    )
    agent.invoke({"messages": [{"role": "user", "content": "train"}]}, config=CFG)
    agent.invoke(Command(resume={"decisions": [{"type": "reject"}]}), config=CFG)
    final = agent.get_state(CFG)
    tool_msgs = [m for m in final.values["messages"] if getattr(m, "type", "") == "tool"]
    # the tool's own success string never appears — it was not executed
    assert not any("trained" in str(m.content).lower() for m in tool_msgs)
    assert any("reject" in str(m.content).lower() for m in tool_msgs)


def test_plan_gate_request_changes_feeds_feedback(settings):
    agent = _agent(
        settings,
        [
            tool_call_message("submit_plan", {"summary": "ARIMA vs LSTM", "plan_path": "research/PLAN.md"}),
            AIMessage(content="Revised the plan to add a baseline."),
        ],
        {"submit_plan": True},
    )
    agent.invoke({"messages": [{"role": "user", "content": "plan it"}]}, config=CFG)
    state = agent.get_state(CFG)
    assert pending_approvals(state)[0]["name"] == "submit_plan"

    # Request changes → the feedback is injected verbatim for the agent to revise
    agent.invoke(
        Command(resume={"decisions": [{"type": "respond", "message": "Add a baseline and 5-fold CV."}]}),
        config=CFG,
    )
    final = agent.get_state(CFG)
    tool_msgs = [m for m in final.values["messages"] if getattr(m, "type", "") == "tool"]
    assert any("5-fold CV" in str(m.content) for m in tool_msgs)


def test_researcher_checkpoint_gate_accepts_steering_feedback(settings):
    agent = _agent(
        settings,
        [
            tool_call_message(
                "researcher_checkpoint",
                {
                    "summary": "Endpoint candidates are MADRS change and remission.",
                    "decision_needed": "Choose the primary endpoint.",
                    "options": ["MADRS change", "remission"],
                },
            ),
            AIMessage(content="Proceeding with MADRS change as primary endpoint."),
        ],
        {"researcher_checkpoint": True},
    )
    agent.invoke({"messages": [{"role": "user", "content": "choose endpoint"}]}, config=CFG)
    request = pending_approvals(agent.get_state(CFG))[0]
    assert request["name"] == "researcher_checkpoint"
    assert "respond" in request["allowed_decisions"]
    assert request["revision_supported"] is True
    agent.invoke(
        Command(resume={"decisions": [{"type": "respond", "message": "Use MADRS change."}]}),
        config=CFG,
    )
    tool_msgs = [
        m for m in agent.get_state(CFG).values["messages"] if getattr(m, "type", "") == "tool"
    ]
    assert any("Use MADRS change" in str(m.content) for m in tool_msgs)


def test_cohort_export_gate_pauses_before_export(settings):
    agent = _agent(
        settings,
        [
            tool_call_message(
                "face_export_analysis_dataset",
                {"subcohort": "BP", "variables": ["age"], "output_name": "gated_export"},
            ),
            AIMessage(content="Export skipped."),
        ],
        {"face_export_analysis_dataset": True},
    )
    agent.invoke({"messages": [{"role": "user", "content": "export BP age"}]}, config=CFG)
    state = agent.get_state(CFG)
    request = pending_approvals(state)[0]
    assert request["name"] == "face_export_analysis_dataset"
    assert request["args"]["subcohort"] == "BP"
    agent.invoke(Command(resume={"decisions": [{"type": "reject"}]}), config=CFG)
    assert not (settings.workspace_dir / "cohorts" / "face" / "bp" / "gated_export.csv").exists()


def test_shell_gate_pauses_before_execute(settings):
    agent = _agent(
        settings,
        [
            tool_call_message("execute", {"cmd": "echo should-not-run"}),
            AIMessage(content="Shell command skipped."),
        ],
        {"execute": True},
    )
    agent.invoke({"messages": [{"role": "user", "content": "run shell"}]}, config=CFG)
    request = pending_approvals(agent.get_state(CFG))[0]
    assert request["name"] == "execute"
    agent.invoke(Command(resume={"decisions": [{"type": "reject"}]}), config=CFG)
    assert not agent.get_state(CFG).next


def test_final_report_gate_pauses(settings):
    agent = _agent(
        settings,
        [
            tool_call_message(
                "submit_final_report",
                {"summary": "FACE feasibility report is ready.", "report_path": "research/report.md"},
            ),
            AIMessage(content="Report release deferred."),
        ],
        {"submit_final_report": True},
    )
    agent.invoke({"messages": [{"role": "user", "content": "release report"}]}, config=CFG)
    request = pending_approvals(agent.get_state(CFG))[0]
    assert request["name"] == "submit_final_report"


def test_pending_approvals_marks_scientific_gate_revision_supported_without_review_config():
    interrupt = type(
        "Interrupt",
        (),
        {
            "value": {
                "action_requests": [
                    {
                        "name": "researcher_checkpoint",
                        "args": {"summary": "Need steering."},
                        "description": "",
                    }
                ]
            }
        },
    )()
    task = type("Task", (), {"interrupts": (interrupt,)})()
    state = type("State", (), {"tasks": (task,)})()

    request = pending_approvals(state)[0]
    assert request["name"] == "researcher_checkpoint"
    assert request["allowed_decisions"] == []
    assert request["revision_supported"] is True


def test_no_gates_runs_without_pause(settings):
    agent = _agent(settings, [AIMessage(content="Done.")], {})
    agent.invoke({"messages": [{"role": "user", "content": "hi"}]}, config=CFG)
    assert not agent.get_state(CFG).next
