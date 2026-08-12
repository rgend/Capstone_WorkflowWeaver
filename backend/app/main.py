from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, templates, workflows
from app.core.config import get_settings
from app.core.store import WorkflowStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.store = WorkflowStore(settings.workflow_store_path)
    app.state.active_runs = {}
    yield


app = FastAPI(
    title="WorkflowWeaver API",
    description="AI agent that executes natural-language business workflows across Notion, Google Drive, and Teams.",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(templates.router)
app.include_router(workflows.router)


@app.get("/")
async def root() -> dict:
    return {"name": "WorkflowWeaver API", "docs": "/docs"}
