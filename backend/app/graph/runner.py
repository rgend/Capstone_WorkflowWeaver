import logging
import time
from collections.abc import Awaitable, Callable

from app.core.config import Settings
from app.core.models import (
    ExecutionReport,
    RunStatus,
    SSEEvent,
    StepResult,
    WorkflowRequest,
    new_id,
)
from app.core.store import WorkflowStore
from app.graph.build import build_graph
from app.graph.context import RunContext
from app.integrations.slack_client import SlackClient
from app.mcp.gdrive_adapter import GoogleDriveAdapter
from app.mcp.notion_adapter import NotionAdapter

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover
    Langfuse = None

logger = logging.getLogger(__name__)


def _build_langfuse_client(settings: Settings):
    if not settings.langfuse_configured or Langfuse is None:
        return None
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


async def run_workflow(
    request: WorkflowRequest,
    settings: Settings,
    store: WorkflowStore,
    emit_raw: Callable[[SSEEvent], Awaitable[None]],
    run_id: str | None = None,
) -> ExecutionReport:
    run_id = run_id or new_id("run")
    started_at = time.time()

    langfuse_client = _build_langfuse_client(settings)
    trace = None
    if langfuse_client:
        trace = langfuse_client.trace(
            id=run_id,
            name="workflowweaver-run",
            input={"description": request.description, "config": request.config.model_dump()},
            metadata={"mock_mode": settings.mock_mode, "template_id": request.template_id},
        )

    ctx = RunContext(
        run_id=run_id,
        settings=settings,
        emit_raw=emit_raw,
        notion=NotionAdapter(settings),
        gdrive=GoogleDriveAdapter(settings),
        slack=SlackClient(settings),
        langfuse_trace=trace,
    )

    initial_state = {
        "run_id": run_id,
        "description": request.description,
        "meeting_notes": request.meeting_notes,
        "config": request.config.model_dump(),
        "intent_summary": None,
        "plan": None,
        "steps": [],
        "current_step_index": 0,
        "status": RunStatus.PENDING.value,
        "error": None,
    }

    await ctx.emit("run", RunStatus.RUNNING, f"Starting workflow run {run_id}")

    error: str | None = None
    final_state = initial_state
    try:
        graph = build_graph(ctx)
        final_state = await graph.ainvoke(initial_state, config={"recursion_limit": 100})
    except Exception as exc:  # noqa: BLE001 - surface any unexpected node error into the report
        logger.exception("Workflow run %s crashed", run_id)
        error = repr(exc)
        final_state["status"] = RunStatus.FAILED.value
        await ctx.emit("run", RunStatus.FAILED, f"Workflow run crashed: {error}")
    finally:
        await ctx.aclose()

    report = ExecutionReport(
        run_id=run_id,
        description=request.description,
        status=RunStatus(final_state.get("status") or RunStatus.FAILED.value),
        intent_summary=final_state.get("intent_summary"),
        steps=[StepResult.model_validate(s) for s in final_state.get("steps", [])],
        created_outputs=_collect_outputs(final_state.get("steps", [])),
        started_at=started_at,
        finished_at=time.time(),
        error=error or final_state.get("error"),
        langfuse_trace_url=(langfuse_client.get_trace_url() if langfuse_client else None),
        mock_mode=settings.mock_mode,
    )

    if trace:
        trace.update(output=report.model_dump(mode="json"), metadata={"status": report.status.value})
        langfuse_client.flush()

    await store.save_report(report)
    await ctx.emit(
        "done",
        report.status,
        f"Run finished: {report.status.value}",
        detail={"run_id": run_id},
    )
    return report


def _collect_outputs(steps: list[dict]) -> dict:
    outputs: dict[str, list] = {}
    for step in steps:
        if step.get("output"):
            outputs.setdefault(step["tool"], []).append(step["output"])
    return outputs
