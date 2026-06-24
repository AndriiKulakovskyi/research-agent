"""API routers: auth, threads (chat + SSE streaming), workspace files."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from langgraph.types import Command

from deep_harness.tools.experiments import read_registry

from deep_harness.server import auth as auth_mod
from deep_harness.server.auth import CurrentUser, get_current_user
from deep_harness.server.schemas import (
    ComputeSettings,
    ComputeSettingsUpdate,
    Credentials,
    FileEntry,
    InitiativeCreate,
    InitiativeInfo,
    InitiativeUpdate,
    MessageOut,
    MessageRequest,
    ResumeRequest,
    ThreadCreate,
    ThreadInfo,
    ThreadUpdate,
    TodoItem,
    TokenResponse,
    UserInfo,
)
from deep_harness.server.streaming import (
    pending_approvals,
    serialize_history,
    stream_agent_events,
)
from deep_harness.tools.planning import SCIENTIFIC_REVISION_GATES

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
threads_router = APIRouter(prefix="/api/threads", tags=["threads"])
files_router = APIRouter(prefix="/api/files", tags=["files"])
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])
experiments_router = APIRouter(prefix="/api/experiments", tags=["experiments"])
initiatives_router = APIRouter(prefix="/api/initiatives", tags=["initiatives"])

IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/gif", "image/svg+xml", "image/webp"}

MAX_FILE_BYTES = 512_000
MAX_IMAGE_BYTES = 8_000_000
RECURSION_LIMIT = 250


def _revision_directive(requests: list[dict], feedback: str) -> str:
    names = ", ".join(
        str(req.get("name"))
        for req in requests
        if req.get("name") in SCIENTIFIC_REVISION_GATES
    )
    return (
        "Researcher revision requested for checkpoint(s): "
        f"{names}.\n\n"
        f"Reviewer feedback:\n{feedback}\n\n"
        "This is not approval. Do not continue down the proposed trajectory yet. "
        "Revise the affected plan, report, or artifact state; call `write_todos` "
        "with the complete updated todo list reflecting the new trajectory; then "
        "re-submit the relevant scientific checkpoint for review before executing "
        "the changed direction."
    )


def _thread_config(
    thread_id: str,
    initiative_id: str | None = None,
    initiative_name: str | None = None,
) -> dict:
    configurable = {"thread_id": thread_id}
    if initiative_id is not None:
        configurable["initiative_id"] = initiative_id
        configurable["initiative_name"] = initiative_name
    return {"configurable": configurable, "recursion_limit": RECURSION_LIMIT}


# -- auth ----------------------------------------------------------------------


@auth_router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: Credentials, request: Request) -> TokenResponse:
    db = request.app.state.db
    auth_mod.register_user(db, body.username, body.password)
    token = auth_mod.issue_token(db, body.username, body.password)
    return TokenResponse(token=token, username=body.username.strip().lower())


@auth_router.post("/login", response_model=TokenResponse)
def login(body: Credentials, request: Request) -> TokenResponse:
    token = auth_mod.issue_token(request.app.state.db, body.username, body.password)
    return TokenResponse(token=token, username=body.username.strip().lower())


@auth_router.get("/me", response_model=UserInfo)
def me(user: CurrentUser = Depends(get_current_user)) -> UserInfo:
    return UserInfo(id=user.id, username=user.username)


@auth_router.post("/logout", status_code=204)
def logout(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Revoke the bearer token used for this request."""
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    request.app.state.db.delete_token(auth_mod.hash_token(token))


# -- threads -------------------------------------------------------------------


def _require_thread(request: Request, thread_id: str, user: CurrentUser):
    row = request.app.state.db.get_thread(thread_id, user.id)
    if row is None:
        raise HTTPException(404, "thread not found")
    return row


_THREAD_FIELDS = ("id", "title", "initiative_id", "created_at", "updated_at")


@threads_router.get("", response_model=list[ThreadInfo])
def list_threads(request: Request, user: CurrentUser = Depends(get_current_user)):
    return [
        ThreadInfo(**{k: row[k] for k in _THREAD_FIELDS})
        for row in request.app.state.db.list_threads(user.id)
    ]


@threads_router.post("", response_model=ThreadInfo, status_code=201)
def create_thread(
    body: ThreadCreate, request: Request, user: CurrentUser = Depends(get_current_user)
):
    db = request.app.state.db
    if body.initiative_id is not None and db.get_initiative(body.initiative_id, user.id) is None:
        raise HTTPException(404, "initiative not found")
    row = db.create_thread(user.id, body.title, body.initiative_id)
    return ThreadInfo(**{k: row[k] for k in _THREAD_FIELDS})


@threads_router.patch("/{thread_id}", response_model=ThreadInfo)
def update_thread(
    thread_id: str,
    body: ThreadUpdate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Move a thread into an initiative, or out of one (initiative_id = null)."""
    db = request.app.state.db
    _require_thread(request, thread_id, user)
    if body.initiative_id is not None and db.get_initiative(body.initiative_id, user.id) is None:
        raise HTTPException(404, "initiative not found")
    db.set_thread_initiative(thread_id, user.id, body.initiative_id)
    row = db.get_thread(thread_id, user.id)
    return ThreadInfo(**{k: row[k] for k in _THREAD_FIELDS})


@threads_router.delete("/{thread_id}", status_code=204)
def delete_thread(
    thread_id: str, request: Request, user: CurrentUser = Depends(get_current_user)
):
    if not request.app.state.db.delete_thread(thread_id, user.id):
        raise HTTPException(404, "thread not found")


@threads_router.get("/{thread_id}/messages", response_model=list[MessageOut])
async def get_messages(
    thread_id: str, request: Request, user: CurrentUser = Depends(get_current_user)
):
    _require_thread(request, thread_id, user)
    agent = request.app.state.agents.get_agent(user.id)
    state = await agent.aget_state(_thread_config(thread_id))
    return serialize_history(state.values.get("messages", []))


@threads_router.get("/{thread_id}/todos", response_model=list[TodoItem])
async def get_todos(
    thread_id: str, request: Request, user: CurrentUser = Depends(get_current_user)
):
    _require_thread(request, thread_id, user)
    agent = request.app.state.agents.get_agent(user.id)
    state = await agent.aget_state(_thread_config(thread_id))
    todos = state.values.get("todos") or []
    return [
        TodoItem(content=t.get("content", ""), status=t.get("status", "pending"))
        for t in todos
        if isinstance(t, dict)
    ]


@threads_router.post("/{thread_id}/messages")
async def post_message(
    thread_id: str,
    body: MessageRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Send a user message and stream the agent's run back as SSE."""
    row = _require_thread(request, thread_id, user)
    db = request.app.state.db
    # First message titles the thread.
    title = body.content[:60] if row["title"] == "New conversation" else None
    db.touch_thread(thread_id, title)

    # The thread's initiative rides along in the run config so experiments logged
    # during this run (by the agent or its subagents) auto-file under it.
    initiative_id = row["initiative_id"]
    initiative_name = None
    if initiative_id is not None:
        initiative = db.get_initiative(initiative_id, user.id)
        initiative_name = initiative["name"] if initiative is not None else None

    agent = request.app.state.agents.get_agent(user.id)
    state = {"messages": [{"role": "user", "content": body.content}]}
    return StreamingResponse(
        stream_agent_events(
            agent, state, _thread_config(thread_id, initiative_id, initiative_name)
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@threads_router.post("/{thread_id}/resume")
async def resume_run(
    thread_id: str,
    body: ResumeRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """Resolve a pending approval gate and stream the continuation as SSE.
    `approve` runs the gated tool; `reject` skips it; `respond` (or `reject`
    with a message) feeds the message back to the agent — used to request plan
    changes. One decision applies to every pending action request in the turn."""
    _require_thread(request, thread_id, user)
    agent = request.app.state.agents.get_agent(user.id)
    config = _thread_config(thread_id)

    state = await agent.aget_state(config)
    if not getattr(state, "next", None):
        raise HTTPException(409, "this run is not waiting for approval")
    approvals = pending_approvals(state)
    count = max(1, len(approvals))

    decision: dict = {"type": body.decision}
    message = body.message.strip() if body.message else ""
    if body.decision == "respond":
        if not message:
            raise HTTPException(400, "revision feedback is required")
        if not approvals or not all(
            req.get("name") in SCIENTIFIC_REVISION_GATES for req in approvals
        ):
            raise HTTPException(
                400,
                "revision feedback is only supported for scientific checkpoints",
            )
        decision["message"] = _revision_directive(approvals, message)
    elif message:
        decision["message"] = message
    command = Command(resume={"decisions": [decision] * count})

    return StreamingResponse(
        stream_agent_events(agent, command, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- compute settings -------------------------------------------------------------


@settings_router.get("", response_model=ComputeSettings)
def get_settings_route(request: Request, user: CurrentUser = Depends(get_current_user)):
    row = request.app.state.db.get_user_settings(user.id)
    if row is None:
        return ComputeSettings()
    return ComputeSettings(
        compute_backend=row["compute_backend"],
        gpu_type=row["gpu_type"],
        modal_token_id=row["modal_token_id"],
        modal_token_secret_set=bool(row["modal_token_secret"]),
        gate_plan=bool(row["gate_plan"]),
        gate_researcher_checkpoint=bool(row["gate_researcher_checkpoint"]),
        gate_cohort_export=bool(row["gate_cohort_export"]),
        gate_training_jobs=bool(row["gate_training_jobs"]),
        gate_shell=bool(row["gate_shell"]),
        gate_report_release=bool(row["gate_report_release"]),
    )


@settings_router.put("", response_model=ComputeSettings)
def update_settings_route(
    body: ComputeSettingsUpdate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    db = request.app.state.db
    db.upsert_user_settings(
        user.id,
        compute_backend=body.compute_backend,
        gpu_type=body.gpu_type,
        modal_token_id=body.modal_token_id,
        modal_token_secret=body.modal_token_secret,
        gate_plan=body.gate_plan,
        gate_researcher_checkpoint=body.gate_researcher_checkpoint,
        gate_cohort_export=body.gate_cohort_export,
        gate_training_jobs=body.gate_training_jobs,
        gate_shell=body.gate_shell,
        gate_report_release=body.gate_report_release,
    )
    # Gating is fixed at agent-build time — drop the cached agent so the change applies.
    request.app.state.agents.invalidate(user.id)
    return get_settings_route(request, user)


# -- workspace files -------------------------------------------------------------


@files_router.get("", response_model=list[FileEntry])
def list_files(request: Request, user: CurrentUser = Depends(get_current_user)):
    root = request.app.state.agents.user_workspace(user.id)
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = str(path.relative_to(root))
        # skills/ holds read-only harness docs synced from the package — noise
        # in a user's artifact browser. memory/ stays visible: the agent's notes.
        if rel.startswith("skills/"):
            continue
        entries.append(FileEntry(path=rel, size=path.stat().st_size))
        if len(entries) >= 500:
            break
    return entries


@files_router.get("/{file_path:path}")
def read_file(file_path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    """Serve a workspace file: images as bytes (so the UI can render figures),
    everything else as text."""
    root = request.app.state.agents.user_workspace(user.id)
    target = (root / file_path).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(403, "path escapes workspace")
    if not target.is_file():
        raise HTTPException(404, "file not found")
    media_type = mimetypes.guess_type(target.name)[0] or ""
    if media_type in IMAGE_MEDIA_TYPES:
        if target.stat().st_size > MAX_IMAGE_BYTES:
            raise HTTPException(413, "image too large to preview")
        return FileResponse(target, media_type=media_type)
    if target.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(413, "file too large to preview")
    try:
        return PlainTextResponse(target.read_text(errors="replace"))
    except OSError as exc:
        raise HTTPException(500, f"cannot read file: {exc}") from exc


# -- experiments -------------------------------------------------------------


@experiments_router.get("")
def list_experiments_route(
    request: Request,
    initiative_id: str | None = None,
    user: CurrentUser = Depends(get_current_user),
):
    """The user's experiment registry (newest first) for the UI Experiments tab.
    Pass `initiative_id` to scope to one research initiative."""
    workspace = request.app.state.agents.user_workspace(user.id)
    records = read_registry(workspace, initiative_id=initiative_id)
    return sorted(records, key=lambda r: r.get("timestamp", 0), reverse=True)


# -- initiatives -------------------------------------------------------------


def _initiative_info(db, workspace, row, thread_counts: dict[str, int]) -> InitiativeInfo:
    experiment_count = len(read_registry(workspace, initiative_id=row["id"]))
    return InitiativeInfo(
        id=row["id"],
        name=row["name"],
        goal=row["goal"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        thread_count=thread_counts.get(row["id"], 0),
        experiment_count=experiment_count,
    )


@initiatives_router.get("", response_model=list[InitiativeInfo])
def list_initiatives(request: Request, user: CurrentUser = Depends(get_current_user)):
    db = request.app.state.db
    workspace = request.app.state.agents.user_workspace(user.id)
    thread_counts = db.count_threads_by_initiative(user.id)
    return [
        _initiative_info(db, workspace, row, thread_counts)
        for row in db.list_initiatives(user.id)
    ]


@initiatives_router.post("", response_model=InitiativeInfo, status_code=201)
def create_initiative(
    body: InitiativeCreate, request: Request, user: CurrentUser = Depends(get_current_user)
):
    db = request.app.state.db
    workspace = request.app.state.agents.user_workspace(user.id)
    row = db.create_initiative(user.id, body.name, body.goal)
    return _initiative_info(db, workspace, row, {})


@initiatives_router.patch("/{initiative_id}", response_model=InitiativeInfo)
def update_initiative(
    initiative_id: str,
    body: InitiativeUpdate,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    db = request.app.state.db
    workspace = request.app.state.agents.user_workspace(user.id)
    row = db.update_initiative(initiative_id, user.id, body.name, body.goal, body.status)
    if row is None:
        raise HTTPException(404, "initiative not found")
    thread_counts = db.count_threads_by_initiative(user.id)
    return _initiative_info(db, workspace, row, thread_counts)


@initiatives_router.delete("/{initiative_id}", status_code=204)
def delete_initiative(
    initiative_id: str, request: Request, user: CurrentUser = Depends(get_current_user)
):
    if not request.app.state.db.delete_initiative(initiative_id, user.id):
        raise HTTPException(404, "initiative not found")
