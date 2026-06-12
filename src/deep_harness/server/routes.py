"""API routers: auth, threads (chat + SSE streaming), workspace files."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from deep_harness.server import auth as auth_mod
from deep_harness.server.auth import CurrentUser, get_current_user
from deep_harness.server.schemas import (
    Credentials,
    FileEntry,
    MessageOut,
    MessageRequest,
    ThreadCreate,
    ThreadInfo,
    TodoItem,
    TokenResponse,
    UserInfo,
)
from deep_harness.server.streaming import serialize_history, stream_agent_events

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
threads_router = APIRouter(prefix="/api/threads", tags=["threads"])
files_router = APIRouter(prefix="/api/files", tags=["files"])

MAX_FILE_BYTES = 512_000
RECURSION_LIMIT = 250


def _thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}


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


@threads_router.get("", response_model=list[ThreadInfo])
def list_threads(request: Request, user: CurrentUser = Depends(get_current_user)):
    return [ThreadInfo(**dict(row)) for row in request.app.state.db.list_threads(user.id)]


@threads_router.post("", response_model=ThreadInfo, status_code=201)
def create_thread(
    body: ThreadCreate, request: Request, user: CurrentUser = Depends(get_current_user)
):
    row = request.app.state.db.create_thread(user.id, body.title)
    return ThreadInfo(**{k: row[k] for k in ("id", "title", "created_at", "updated_at")})


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

    agent = request.app.state.agents.get_agent(user.id)
    state = {"messages": [{"role": "user", "content": body.content}]}
    return StreamingResponse(
        stream_agent_events(agent, state, _thread_config(thread_id)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- workspace files -------------------------------------------------------------


@files_router.get("", response_model=list[FileEntry])
def list_files(request: Request, user: CurrentUser = Depends(get_current_user)):
    root = request.app.state.agents.user_workspace(user.id)
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            entries.append(
                FileEntry(path=str(path.relative_to(root)), size=path.stat().st_size)
            )
        if len(entries) >= 500:
            break
    return entries


@files_router.get("/{file_path:path}", response_class=PlainTextResponse)
def read_file(file_path: str, request: Request, user: CurrentUser = Depends(get_current_user)):
    root = request.app.state.agents.user_workspace(user.id)
    target = (root / file_path).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(403, "path escapes workspace")
    if not target.is_file():
        raise HTTPException(404, "file not found")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(413, "file too large to preview")
    try:
        return target.read_text(errors="replace")
    except OSError as exc:
        raise HTTPException(500, f"cannot read file: {exc}") from exc
