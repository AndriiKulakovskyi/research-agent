"""FastAPI application factory for the multi-user deep harness service."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from deep_harness.config import get_settings
from deep_harness.server.agents import AgentManager
from deep_harness.server.db import AppDB
from deep_harness.server.routes import (
    auth_router,
    files_router,
    settings_router,
    threads_router,
)

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app(model: str | BaseChatModel | None = None) -> FastAPI:
    """Build the app. `model` overrides the configured model (tests inject a fake)."""
    settings = get_settings()
    settings.ensure_workspace()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        checkpoint_path = settings.workspace_dir / "checkpoints.db"
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
            app.state.db = AppDB(settings.workspace_dir / "app.db")
            app.state.agents = AgentManager(checkpointer=saver, db=app.state.db, model=model)
            yield

    app = FastAPI(title="Deep Harness Agent", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(threads_router)
    app.include_router(files_router)
    app.include_router(settings_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "model": str(model or settings.model)}

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="ui")

    return app


def main() -> None:
    """Entrypoint for the `deep-harness-server` script."""
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
