from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    username: str


class UserInfo(BaseModel):
    id: str
    username: str


class ThreadCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=200)
    initiative_id: str | None = None


class ThreadInfo(BaseModel):
    id: str
    title: str
    initiative_id: str | None = None
    created_at: float
    updated_at: float


class ThreadUpdate(BaseModel):
    """Move a thread into an initiative, or out of one (initiative_id = null)."""

    initiative_id: str | None = None


class InitiativeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal: str = Field(default="", max_length=2000)


class InitiativeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None, pattern="^(active|completed|archived)$")


class InitiativeInfo(BaseModel):
    id: str
    name: str
    goal: str
    status: str
    created_at: float
    updated_at: float
    thread_count: int = 0
    experiment_count: int = 0


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50_000)


class MessageOut(BaseModel):
    role: str
    content: str
    tool_calls: list[dict[str, Any]] = []
    tool_name: str | None = None


class TodoItem(BaseModel):
    content: str
    status: str


class FileEntry(BaseModel):
    path: str
    size: int


class ComputeSettings(BaseModel):
    """Read shape: the Modal token secret is never echoed, only its presence."""

    compute_backend: str = "local"
    gpu_type: str = "A10G"
    modal_token_id: str = ""
    modal_token_secret_set: bool = False


class ComputeSettingsUpdate(BaseModel):
    """Write shape: omit a token field (None) to keep the stored value."""

    compute_backend: str = Field(pattern="^(local|modal)$")
    gpu_type: str = Field(default="A10G", pattern="^(T4|L4|A10G|A100|H100)$")
    modal_token_id: str | None = None
    modal_token_secret: str | None = None
