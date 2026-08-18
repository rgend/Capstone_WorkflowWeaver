import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_active_runs, get_settings, get_store
from app.core.config import Settings
from app.core.models import ExecutionReport, WorkflowRequest, WorkflowSummary, new_id
from app.core.store import WorkflowStore
from app.core.templates import get_template
from app.graph.runner import run_workflow

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

_QUEUE_SENTINEL = None


@router.post("")
async def start_workflow(
    request: WorkflowRequest,
    settings: Settings = Depends(get_settings),
    store: WorkflowStore = Depends(get_store),
    active_runs: dict = Depends(get_active_runs),
) -> dict:
    if request.template_id:
        template = get_template(request.template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Unknown template_id")
        if not request.description.strip():
            request.description = template.nl_description
        for field in ("workspace", "notion_page_id", "drive_folder_id", "slack_channel"):
            if getattr(request.config, field) is None:
                setattr(request.config, field, getattr(template.default_config, field))

    run_id = new_id("run")
    queue: asyncio.Queue = asyncio.Queue()
    active_runs[run_id] = queue

    async def emit_raw(event) -> None:
        await queue.put(event)

    async def _run_and_close() -> None:
        try:
            await run_workflow(request, settings, store, emit_raw, run_id=run_id)
        finally:
            await queue.put(_QUEUE_SENTINEL)

    asyncio.create_task(_run_and_close())
    return {"run_id": run_id}


@router.get("/{run_id}/stream")
async def stream_workflow(
    run_id: str,
    active_runs: dict = Depends(get_active_runs),
    store: WorkflowStore = Depends(get_store),
):
    queue = active_runs.get(run_id)

    if queue is None:
        report = await store.get_report(run_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Unknown run_id")

        async def replay_generator():
            yield {"event": "done", "data": report.model_dump_json()}

        return EventSourceResponse(replay_generator())

    async def generator():
        try:
            while True:
                event = await queue.get()
                if event is _QUEUE_SENTINEL:
                    report = await store.get_report(run_id)
                    if report:
                        yield {"event": "done", "data": report.model_dump_json()}
                    break
                yield {"event": "log", "data": event.model_dump_json()}
        finally:
            active_runs.pop(run_id, None)

    return EventSourceResponse(generator())


@router.get("/{run_id}/report", response_model=ExecutionReport)
async def get_report(run_id: str, store: WorkflowStore = Depends(get_store)) -> ExecutionReport:
    report = await store.get_report(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return report


@router.get("", response_model=list[WorkflowSummary])
async def list_workflows(store: WorkflowStore = Depends(get_store)) -> list[WorkflowSummary]:
    return await store.list_summaries()
