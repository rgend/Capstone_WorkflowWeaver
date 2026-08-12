"""LLM reasoning layer: turns a natural-language workflow description into a
structured, tool-routed execution plan.

Uses Claude tool-use (forced tool_choice) to get a guaranteed-structured plan
back from the model rather than parsing free-form JSON. Every call is wrapped
in a Langfuse generation span. When no LLM key is configured, falls back to a
deterministic keyword-based planner so the graph is still fully exercisable
without any API key.
"""

import re

from anthropic import AsyncAnthropic

from app.core.config import Settings
from app.core.errors import PlanningError
from app.core.models import PlannedStep, ToolName, WorkflowConfig, WorkflowPlan

PLAN_TOOL_SCHEMA = {
    "name": "submit_workflow_plan",
    "description": "Submit the structured, tool-routed execution plan for the requested workflow.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent_summary": {
                "type": "string",
                "description": "One or two sentence summary of what the user wants done.",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "enum": ["notion", "google_drive", "teams", "none"]},
                        "action": {"type": "string", "description": "short verb phrase, e.g. create_project_page"},
                        "description": {"type": "string", "description": "human-readable step description for logs"},
                        "input": {
                            "type": "object",
                            "description": (
                                "arguments needed to execute the step, e.g. title, sections, "
                                "action_items, content, message"
                            ),
                        },
                    },
                    "required": ["tool", "action", "description", "input"],
                },
            },
        },
        "required": ["intent_summary", "steps"],
    },
}

SYSTEM_PROMPT = """You are the planning brain of WorkflowWeaver, an autonomous workflow-execution \
agent. Given a plain-English business workflow description (and optional meeting notes / \
requirements text), decompose it into an ordered list of concrete tool actions. Available tools: \
notion (create_project_page), google_drive (create_document), teams (post_message). Only use tools \
the description implies. Keep step inputs self-contained (include actual titles/content/text derived \
from the description, not placeholders). Always call submit_workflow_plan exactly once."""


def _fallback_plan(description: str, meeting_notes: str | None, config: WorkflowConfig) -> WorkflowPlan:
    text = f"{description}\n{meeting_notes or ''}".lower()
    steps: list[PlannedStep] = []
    idx = 0

    notes_lines = [ln.strip("-*• ").strip() for ln in (meeting_notes or "").splitlines() if ln.strip()]
    action_items = (
        notes_lines[:8]
        if notes_lines
        else [
            "Review workflow description and confirm scope",
            "Assign owners to each action item",
        ]
    )

    wants_notion = "notion" in text or "page" in text or "task" in text or "backlog" in text
    wants_drive = "drive" in text or "document" in text or "doc " in text or "postmortem" in text or "report" in text
    wants_teams = "teams" in text or "notify" in text or "summary" in text or "announce" in text or "post" in text

    title_match = re.search(r"(?:create|generate)\s+(?:a\s+)?([\w\s]{4,60}?)(?:page|doc|document|backlog)", text)
    title = (title_match.group(1).strip().title() + " Page") if title_match else "WorkflowWeaver Project Page"

    if wants_notion or not (wants_drive or wants_teams):
        steps.append(
            PlannedStep(
                index=idx,
                tool=ToolName.NOTION,
                action="create_project_page",
                description=f"Create Notion page '{title}' with action items",
                input={
                    "title": title,
                    "sections": [
                        {"heading": "Summary", "lines": [description[:280]]},
                        {"heading": "Action Items", "lines": action_items, "as_todo": True},
                    ],
                    "parent_page_id": config.notion_page_id,
                },
            )
        )
        idx += 1

    if wants_drive:
        steps.append(
            PlannedStep(
                index=idx,
                tool=ToolName.GOOGLE_DRIVE,
                action="create_document",
                description="Save workflow summary document to Google Drive",
                input={
                    "name": f"{title} - Summary.txt",
                    "content": f"{description}\n\nAction items:\n" + "\n".join(f"- {a}" for a in action_items),
                    "folder_id": config.drive_folder_id,
                },
            )
        )
        idx += 1

    if wants_teams:
        steps.append(
            PlannedStep(
                index=idx,
                tool=ToolName.TEAMS,
                action="post_message",
                description="Post workflow summary notification to Microsoft Teams",
                input={
                    "title": f"WorkflowWeaver: {title}",
                    "text": description[:500],
                    "facts": {"Action items": str(len(action_items)), "Channel": config.teams_channel or "default"},
                },
            )
        )
        idx += 1

    return WorkflowPlan(intent_summary=description[:200], steps=steps)


async def generate_plan(
    description: str,
    meeting_notes: str | None,
    config: WorkflowConfig,
    settings: Settings,
    trace=None,
) -> WorkflowPlan:
    if not settings.llm_configured:
        return _fallback_plan(description, meeting_notes, config)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_content = f"Workflow description:\n{description}"
    if meeting_notes:
        user_content += f"\n\nMeeting notes / source text:\n{meeting_notes}"
    user_content += f"\n\nConfig context: {config.model_dump_json()}"

    generation = (
        trace.generation(
            name="generate_plan",
            model=settings.anthropic_model,
            input={"system": SYSTEM_PROMPT, "user": user_content},
        )
        if trace
        else None
    )

    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[PLAN_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_workflow_plan"},
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:
        if generation:
            generation.end(output=None, level="ERROR", status_message=str(exc))
        raise PlanningError(f"LLM planning call failed: {exc}") from exc

    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    if tool_use is None:
        if generation:
            generation.end(output=str(response.content), level="ERROR", status_message="no tool_use block")
        raise PlanningError("LLM did not return a structured plan")

    raw = tool_use.input
    if generation:
        generation.end(
            output=raw,
            usage={
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "unit": "TOKENS",
            },
        )

    steps = [
        PlannedStep(
            index=i,
            tool=ToolName(s["tool"]),
            action=s["action"],
            description=s["description"],
            input=s.get("input", {}),
        )
        for i, s in enumerate(raw.get("steps", []))
    ]
    return WorkflowPlan(intent_summary=raw.get("intent_summary", description[:200]), steps=steps)
