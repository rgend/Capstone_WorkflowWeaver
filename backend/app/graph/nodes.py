import asyncio
import logging
import time

from app.core.errors import PlanningError, ToolExecutionError
from app.core.models import RunStatus, StepResult, StepStatus, ToolName, WorkflowConfig
from app.graph.context import RunContext
from app.graph.llm import generate_plan
from app.graph.state import GraphState

logger = logging.getLogger(__name__)


def _resource_links_from_steps(prior_steps: list[dict]) -> list[dict]:
    """Pull real, already-created Notion/Drive links out of earlier steps in
    this same run. The LLM plans all steps up front, before any tool has
    actually run, so it cannot know a Notion page's real URL when it writes
    the Slack step — only the orchestrator sees each step's actual output,
    so it (not the LLM) is responsible for wiring real links into the
    notification.
    """
    links: list[dict] = []
    for step in prior_steps:
        output = step.get("output") or {}
        url = output.get("url")
        if not url:
            continue
        if step.get("tool") == ToolName.NOTION.value:
            links.append({"label": f"{output.get('title') or 'Notion Page'} (Notion)", "url": url})
        elif step.get("tool") == ToolName.GOOGLE_DRIVE.value:
            links.append({"label": f"{output.get('name') or 'Document'} (Google Drive)", "url": url})
    return links


TOOL_HANDLERS = {
    ToolName.NOTION: {
        # .get() with a fallback rather than direct indexing: an LLM-planned
        # step's `input` isn't schema-guaranteed to have every field filled in
        # (verified in practice — Gemini has omitted `title` on a live run),
        # so a missing field should degrade gracefully, not crash the step.
        "create_project_page": lambda ctx, inp, prior_steps: ctx.notion.create_project_page(
            title=inp.get("title") or "Untitled",
            sections=inp.get("sections", []),
            parent_page_id=inp.get("parent_page_id"),
        ),
    },
    ToolName.GOOGLE_DRIVE: {
        "create_document": lambda ctx, inp, prior_steps: ctx.gdrive.create_document(
            name=inp.get("name") or "Untitled Document",
            content=inp.get("content", ""),
            folder_id=inp.get("folder_id"),
            sections=inp.get("sections"),
        ),
    },
    ToolName.SLACK: {
        "post_message": lambda ctx, inp, prior_steps: ctx.slack.post_message(
            title=inp.get("title") or "WorkflowWeaver update",
            text=inp.get("text", ""),
            facts=inp.get("facts"),
            channel=inp.get("channel"),
            resource_links=_resource_links_from_steps(prior_steps),
        ),
    },
}

ROLLBACK_HANDLERS = {
    ToolName.NOTION: lambda ctx, ref: ctx.notion.delete_report(ref["block_id"]),
    ToolName.GOOGLE_DRIVE: lambda ctx, ref: ctx.gdrive.delete_file(ref["file_id"]),
}


async def parse_intent_node(ctx: RunContext, state: GraphState) -> dict:
    await ctx.emit("parse_intent", StepStatus.RUNNING, "Reading the workflow description...")
    await asyncio.sleep(0)  # yield control; real work happens in plan_actions to keep one LLM call
    await ctx.emit("parse_intent", StepStatus.SUCCESS, "Parsed workflow description and context.")
    return {"status": RunStatus.RUNNING.value}


async def plan_actions_node(ctx: RunContext, state: GraphState) -> dict:
    await ctx.emit("plan_actions", StepStatus.RUNNING, "Asking the LLM to build a tool-routed execution plan...")
    config = WorkflowConfig.model_validate(state["config"])
    try:
        plan = await generate_plan(
            description=state["description"],
            meeting_notes=state.get("meeting_notes"),
            config=config,
            settings=ctx.settings,
            trace=ctx.langfuse_trace,
        )
    except PlanningError as exc:
        await ctx.emit("plan_actions", StepStatus.FAILED, f"Planning failed: {exc}")
        return {"status": RunStatus.FAILED.value, "error": str(exc)}

    steps = [
        StepResult(
            step_id=s.step_id,
            index=s.index,
            tool=s.tool,
            action=s.action,
            description=s.description,
            status=StepStatus.PENDING,
        ).model_dump(mode="json")
        for s in plan.steps
    ]
    tool_list = ", ".join(s.tool.value for s in plan.steps) or "no tool steps"
    message = f"Plan ready: {len(plan.steps)} step(s) -> {tool_list}"
    if plan.planning_note:
        message = f"{plan.planning_note} {message}"
    await ctx.emit(
        "plan_actions",
        StepStatus.SUCCESS,
        message,
        detail={
            "intent_summary": plan.intent_summary,
            "step_count": len(plan.steps),
            "planning_note": plan.planning_note,
        },
    )
    return {
        "intent_summary": plan.intent_summary,
        "plan": plan.model_dump(mode="json"),
        "steps": steps,
        "current_step_index": 0,
        "status": RunStatus.RUNNING.value,
    }


async def execute_step_node(ctx: RunContext, state: GraphState) -> dict:
    idx = state["current_step_index"]
    steps = state["steps"]
    plan = state["plan"] or {"steps": []}
    planned = plan["steps"][idx]
    tool = ToolName(planned["tool"])
    action = planned["action"]
    step = steps[idx]
    step["status"] = StepStatus.RUNNING.value
    step["started_at"] = time.time()

    handler = TOOL_HANDLERS.get(tool, {}).get(action)
    max_attempts = ctx.settings.max_step_retries
    attempt = 0
    last_error: str | None = None

    if tool == ToolName.NONE or handler is None:
        step["status"] = StepStatus.SKIPPED.value
        step["finished_at"] = time.time()
        await ctx.emit(
            "execute_step",
            StepStatus.SKIPPED,
            f"No handler for {tool.value}:{action}, skipping.",
            step_id=step["step_id"],
        )
        steps[idx] = step
        return {"steps": steps, "current_step_index": idx + 1}

    await ctx.emit(
        "execute_step",
        StepStatus.RUNNING,
        f"Executing step {idx + 1}/{len(steps)}: {planned['description']}",
        step_id=step["step_id"],
    )

    while attempt < max_attempts:
        attempt += 1
        step["attempts"] = attempt
        span = (
            ctx.langfuse_trace.span(
                name=f"{tool.value}:{action}",
                input=planned["input"],
                metadata={"attempt": attempt, "step_id": step["step_id"]},
            )
            if ctx.langfuse_trace
            else None
        )
        try:
            output = await handler(ctx, planned["input"], steps[:idx])
            if span:
                span.end(output=output)
            step["status"] = StepStatus.SUCCESS.value
            step["output"] = output
            step["finished_at"] = time.time()
            if not output.get("mock") and tool in ROLLBACK_HANDLERS:
                ref_key = "block_id" if tool == ToolName.NOTION else "file_id"
                ref_val = output.get(ref_key)
                if ref_val:
                    ctx.rollback_stack.append(
                        {"tool": tool.value, "ref": {ref_key: ref_val}, "step_id": step["step_id"]}
                    )
            elif output.get("mock") and tool in ROLLBACK_HANDLERS:
                ref_key = "block_id" if tool == ToolName.NOTION else "file_id"
                ctx.rollback_stack.append(
                    {"tool": tool.value, "ref": {ref_key: output[ref_key]}, "step_id": step["step_id"]}
                )
            await ctx.emit(
                "execute_step",
                StepStatus.SUCCESS,
                f"Step {idx + 1} succeeded: {planned['description']}",
                step_id=step["step_id"],
                detail={"output": output, "attempts": attempt},
            )
            steps[idx] = step
            return {"steps": steps, "current_step_index": idx + 1}
        except Exception as exc:  # noqa: BLE001 - any handler failure must still route to rollback, not crash the run
            if isinstance(exc, ToolExecutionError):
                last_error = str(exc)
                retriable = exc.retriable
            else:
                # An unexpected error (e.g. a malformed LLM-planned input)
                # isn't retriable — the same bad input would just fail again.
                logger.exception("Unexpected error executing step %d (%s:%s)", idx + 1, tool.value, action)
                last_error = f"Unexpected error: {exc!r}"
                retriable = False
            if span:
                span.end(level="ERROR", status_message=last_error, output={"retriable": retriable})
            if attempt < max_attempts and retriable:
                backoff = ctx.settings.retry_backoff_base_seconds * (2 ** (attempt - 1))
                step["status"] = StepStatus.RETRYING.value
                retry_msg = (
                    f"Step {idx + 1} failed (attempt {attempt}/{max_attempts}): {last_error}. "
                    f"Retrying in {backoff:.1f}s..."
                )
                await ctx.emit(
                    "execute_step",
                    StepStatus.RETRYING,
                    retry_msg,
                    step_id=step["step_id"],
                )
                await asyncio.sleep(backoff)
                continue
            break

    step["status"] = StepStatus.FAILED.value
    step["error"] = last_error
    step["finished_at"] = time.time()
    await ctx.emit(
        "execute_step",
        StepStatus.FAILED,
        f"Step {idx + 1} failed after {attempt} attempt(s): {last_error}",
        step_id=step["step_id"],
    )
    steps[idx] = step
    return {"steps": steps, "current_step_index": idx + 1, "status": RunStatus.FAILED.value, "error": last_error}


async def rollback_node(ctx: RunContext, state: GraphState) -> dict:
    if not ctx.rollback_stack:
        await ctx.emit("rollback", RunStatus.FAILED, "No prior actions to roll back.")
        return {"status": RunStatus.FAILED.value}

    await ctx.emit(
        "rollback",
        StepStatus.RUNNING,
        f"Critical failure detected. Rolling back {len(ctx.rollback_stack)} action(s)...",
    )
    steps = state["steps"]
    for entry in reversed(ctx.rollback_stack):
        tool = ToolName(entry["tool"])
        handler = ROLLBACK_HANDLERS.get(tool)
        span = (
            ctx.langfuse_trace.span(name=f"rollback:{tool.value}", input=entry["ref"]) if ctx.langfuse_trace else None
        )
        try:
            if handler:
                await handler(ctx, entry["ref"])
            if span:
                span.end(output={"rolled_back": True})
            for step in steps:
                if step["step_id"] == entry["step_id"]:
                    step["status"] = StepStatus.ROLLED_BACK.value
            await ctx.emit(
                "rollback",
                StepStatus.ROLLED_BACK,
                f"Rolled back {tool.value} action from step {entry['step_id']}.",
                step_id=entry["step_id"],
            )
        except ToolExecutionError as exc:
            if span:
                span.end(level="ERROR", status_message=str(exc))
            await ctx.emit(
                "rollback", StepStatus.FAILED, f"Rollback failed for {tool.value}: {exc}", step_id=entry["step_id"]
            )

    return {"steps": steps, "status": RunStatus.ROLLED_BACK.value}


async def report_node(ctx: RunContext, state: GraphState) -> dict:
    final_status = state.get("status") or RunStatus.SUCCESS.value
    if final_status == RunStatus.RUNNING.value:
        final_status = RunStatus.SUCCESS.value
    await ctx.emit(
        "report",
        RunStatus(final_status),
        f"Workflow run finished with status: {final_status}",
        detail={"created_outputs": _collect_outputs(state["steps"])},
    )
    return {"status": final_status}


def _collect_outputs(steps: list[dict]) -> dict:
    outputs: dict[str, list] = {}
    for step in steps:
        if step.get("output"):
            outputs.setdefault(step["tool"], []).append(step["output"])
    return outputs


def route_after_execute(state: GraphState) -> str:
    if state.get("status") == RunStatus.FAILED.value:
        return "rollback"
    if state["current_step_index"] < len(state["steps"]):
        return "execute_step"
    return "report"


def route_after_plan(state: GraphState) -> str:
    if state.get("status") == RunStatus.FAILED.value:
        return "report"
    if not state["steps"]:
        return "report"
    return "execute_step"
