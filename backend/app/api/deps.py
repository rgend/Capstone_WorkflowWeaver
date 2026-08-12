import asyncio

from fastapi import Request

from app.core.config import Settings
from app.core.store import WorkflowStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> WorkflowStore:
    return request.app.state.store


def get_active_runs(request: Request) -> dict[str, asyncio.Queue]:
    return request.app.state.active_runs
