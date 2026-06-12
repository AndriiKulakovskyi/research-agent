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


class ThreadInfo(BaseModel):
    id: str
    title: str
    created_at: float
    updated_at: float


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
