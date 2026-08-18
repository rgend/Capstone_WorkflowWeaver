"""LLM reasoning layer: turns a natural-language workflow description into a
structured, tool-routed execution plan.

Supports two providers, both forced into a single structured tool/function
call so the model can't return free-form prose instead of a plan:
  - Anthropic (Claude tool-use, tool_choice forced to submit_workflow_plan)
  - Google Gemini (function-calling, FunctionCallingConfig mode="ANY")

Every call is wrapped in a Langfuse generation span. When no LLM key is
configured, falls back to a deterministic keyword-based planner so the graph
is still fully exercisable without any API key.
"""

import logging
import re

from app.core.config import Settings
from app.core.errors import PlanningError
from app.core.models import PlannedStep, ToolName, WorkflowConfig, WorkflowPlan

logger = logging.getLogger(__name__)

FUNCTION_NAME = "submit_workflow_plan"
FUNCTION_DESCRIPTION = "Submit the structured, tool-routed execution plan for the requested workflow."

# Shared by both providers: each planned step's `input` is one flat, richly
# described object rather than a schemaless dict. Concrete per-field
# descriptions matter a lot here — a generic `"input": {"type": "object"}`
# gets returned empty by Gemini's function-calling far more often than a
# schema with named properties (verified against models/gemini-3.5-flash).
STEP_INPUT_SCHEMA = {
    "type": "object",
    "description": (
        "Concrete arguments for this step. Populate only the fields relevant to the "
        "chosen tool/action, using real content derived from the description/notes "
        "(never placeholder text)."
    ),
    "properties": {
        "title": {"type": "string", "description": "Notion page title (notion.create_project_page)."},
        "sections": {
            "type": "array",
            "description": (
                "Structured content blocks, used by notion.create_project_page and "
                "google_drive.create_document so both destinations render the same "
                "well-formatted content: a heading followed by a styled list/paragraph."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string", "description": "Section heading text."},
                    "style": {
                        "type": "string",
                        "enum": ["paragraph", "bullet", "numbered", "todo"],
                        "description": (
                            "How to render each line: plain paragraph, bulleted list, "
                            "numbered list, or a checkbox to-do list."
                        ),
                    },
                    "lines": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "One entry per paragraph/list item. Supports **bold**, "
                            "*italic*, and `code` inline markdown."
                        ),
                    },
                },
                "required": ["heading", "lines"],
            },
        },
        "parent_page_id": {"type": "string", "description": "Optional Notion parent page override."},
        "name": {"type": "string", "description": "Google Drive document name (google_drive.create_document)."},
        "content": {
            "type": "string",
            "description": "Plain-text fallback body for google_drive.create_document when sections aren't used.",
        },
        "folder_id": {"type": "string", "description": "Optional Google Drive folder override."},
        "text": {
            "type": "string",
            "description": "Slack message body (slack.post_message). Supports **bold** and *italic*.",
        },
        "facts": {
            "type": "object",
            "description": "Optional key/value facts shown as fields in the Slack card, e.g. {'Owner': 'Priya'}.",
            "additionalProperties": {"type": "string"},
        },
        "channel": {"type": "string", "description": "Optional Slack channel/ID override."},
    },
}

PLAN_INPUT_SCHEMA = {
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
                    "tool": {"type": "string", "enum": ["notion", "google_drive", "slack", "none"]},
                    "action": {"type": "string", "description": "short verb phrase, e.g. create_project_page"},
                    "description": {"type": "string", "description": "human-readable step description for logs"},
                    "input": STEP_INPUT_SCHEMA,
                },
                "required": ["tool", "action", "description", "input"],
            },
        },
    },
    "required": ["intent_summary", "steps"],
}

PLAN_TOOL_SCHEMA = {
    "name": FUNCTION_NAME,
    "description": FUNCTION_DESCRIPTION,
    "input_schema": PLAN_INPUT_SCHEMA,
}

SYSTEM_PROMPT = """You are the planning brain of WorkflowWeaver, an autonomous workflow-execution \
agent. Given a plain-English business workflow description (and optional meeting notes / \
requirements text), decompose it into an ordered list of concrete tool actions. WorkflowWeaver's \
standard pipeline always runs all three tools, in this order, for every workflow: notion \
(create_project_page), google_drive (create_document), slack (post_message) — only skip a tool if \
the user explicitly says not to use it (e.g. "don't post to Slack"). Keep step inputs \
self-contained (include actual titles/content/text derived from the description, not \
placeholders). For notion and google_drive steps, always populate `sections` with the *same* real \
headings and lines (using the `bullet`/`numbered`/`todo` styles where they fit) so both \
destinations render the same well-structured report, not a single wall of text. The slack step's \
`text` should be a short, high-level summary of what was done — links to the Notion page and \
Drive document are added automatically afterward, so never invent placeholder links yourself. \
Always call submit_workflow_plan exactly once."""


def _fallback_plan(description: str, meeting_notes: str | None, config: WorkflowConfig) -> WorkflowPlan:
    notes_lines = [ln.strip("-*• ").strip() for ln in (meeting_notes or "").splitlines() if ln.strip()]
    action_items = (
        notes_lines[:8]
        if notes_lines
        else [
            "Review workflow description and confirm scope",
            "Assign owners to each action item",
        ]
    )

    text = f"{description}\n{meeting_notes or ''}".lower()
    title_match = re.search(r"(?:create|generate)\s+(?:a\s+)?([\w\s]{4,60}?)(?:page|doc|document|backlog)", text)
    title = (title_match.group(1).strip().title() + " Page") if title_match else "WorkflowWeaver Project Page"

    sections = [
        {"heading": "Summary", "lines": [description[:280]], "style": "paragraph"},
        {"heading": "Action Items", "lines": action_items, "style": "todo"},
    ]

    # The standard pipeline always runs all three tools, in this fixed order —
    # matching the LLM-driven planner's default behavior above, so the
    # offline fallback (used when no LLM key is set, or a live call fails)
    # produces the same complete flow rather than a partial one.
    steps = [
        PlannedStep(
            index=0,
            tool=ToolName.NOTION,
            action="create_project_page",
            description=f"Create Notion page '{title}' with action items",
            input={
                "title": title,
                "sections": sections,
                "parent_page_id": config.notion_page_id,
            },
        ),
        PlannedStep(
            index=1,
            tool=ToolName.GOOGLE_DRIVE,
            action="create_document",
            description="Save workflow summary document to Google Drive",
            input={
                "name": f"{title} - Summary",
                "sections": sections,
                "folder_id": config.drive_folder_id,
            },
        ),
        PlannedStep(
            index=2,
            tool=ToolName.SLACK,
            action="post_message",
            description="Post workflow summary notification to Slack",
            input={
                "title": f"WorkflowWeaver: {title}",
                "text": description[:500],
                "facts": {"Action items": str(len(action_items)), "Channel": config.slack_channel or "default"},
                "channel": config.slack_channel,
            },
        ),
    ]

    return WorkflowPlan(intent_summary=description[:200], steps=steps)


def _short_planning_failure_reason(exc: Exception) -> str:
    """A short, professional-sounding reason for the SSE log/UI — the full
    provider error (still useful for debugging) stays in the app log and the
    Langfuse generation span rather than surfacing as a raw JSON dump.
    """
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
        return "the LLM provider's request quota is exhausted"
    if "UNAVAILABLE" in text or "503" in text:
        return "the LLM provider is temporarily overloaded"
    if "rate limit" in text.lower() or "429" in text:
        return "the LLM provider is rate-limiting requests"
    return f"an LLM error occurred ({text.splitlines()[0][:160]})"


def _is_gemini_provider(provider: str) -> bool:
    p = provider.lower()
    return "gemini" in p or "google" in p


def _is_anthropic_provider(provider: str) -> bool:
    p = provider.lower()
    return "anthropic" in p or "claude" in p


async def _plan_with_anthropic(user_content: str, settings: Settings, trace) -> dict:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.llm_api_key)
    model = settings.llm_model or settings.anthropic_model

    generation = (
        trace.generation(name="generate_plan", model=model, input={"system": SYSTEM_PROMPT, "user": user_content})
        if trace
        else None
    )

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=settings.llm_max_output_tokens,
            system=SYSTEM_PROMPT,
            tools=[PLAN_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": FUNCTION_NAME},
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
    return raw


async def _plan_with_gemini(user_content: str, settings: Settings, trace) -> dict:
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=settings.llm_api_key)
    model = settings.llm_model or "models/gemini-2.5-flash"

    function_decl = genai_types.FunctionDeclaration(
        name=FUNCTION_NAME,
        description=FUNCTION_DESCRIPTION,
        parameters_json_schema=PLAN_INPUT_SCHEMA,
    )
    generate_config = genai_types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[genai_types.Tool(function_declarations=[function_decl])],
        tool_config=genai_types.ToolConfig(
            function_calling_config=genai_types.FunctionCallingConfig(
                mode="ANY", allowed_function_names=[FUNCTION_NAME]
            )
        ),
        max_output_tokens=settings.llm_max_output_tokens,
    )

    generation = (
        trace.generation(name="generate_plan", model=model, input={"system": SYSTEM_PROMPT, "user": user_content})
        if trace
        else None
    )

    try:
        response = await client.aio.models.generate_content(model=model, contents=user_content, config=generate_config)
    except Exception as exc:
        if generation:
            generation.end(output=None, level="ERROR", status_message=str(exc))
        raise PlanningError(f"LLM planning call failed: {exc}") from exc

    function_call = None
    for candidate in response.candidates or []:
        for part in getattr(candidate.content, "parts", None) or []:
            if getattr(part, "function_call", None):
                function_call = part.function_call
                break
        if function_call:
            break

    if function_call is None:
        if generation:
            generation.end(output=str(response), level="ERROR", status_message="no function_call part")
        raise PlanningError("LLM did not return a structured plan")

    raw = dict(function_call.args)
    if generation:
        usage = response.usage_metadata
        generation.end(
            output=raw,
            usage={
                "input": getattr(usage, "prompt_token_count", None),
                "output": getattr(usage, "candidates_token_count", None),
                "unit": "TOKENS",
            },
        )
    return raw


async def generate_plan(
    description: str,
    meeting_notes: str | None,
    config: WorkflowConfig,
    settings: Settings,
    trace=None,
) -> WorkflowPlan:
    if not settings.llm_configured:
        return _fallback_plan(description, meeting_notes, config)

    user_content = f"Workflow description:\n{description}"
    if meeting_notes:
        user_content += f"\n\nMeeting notes / source text:\n{meeting_notes}"
    user_content += f"\n\nConfig context: {config.model_dump_json()}"

    provider = settings.llm_provider or ""
    try:
        if _is_gemini_provider(provider):
            raw = await _plan_with_gemini(user_content, settings, trace)
        elif _is_anthropic_provider(provider):
            raw = await _plan_with_anthropic(user_content, settings, trace)
        else:
            raise PlanningError(
                f"Unsupported LLM_PROVIDER '{settings.llm_provider}' (expected 'anthropic' or 'google-gemini-ai')."
            )
    except PlanningError as exc:
        # A live LLM outage (rate limit, quota exhaustion, transient 5xx)
        # shouldn't take down the whole run — degrade to the same offline
        # planner used when no key is configured at all, so the workflow
        # still completes end-to-end. The Langfuse generation span already
        # recorded the real failure (see _plan_with_gemini/_plan_with_anthropic).
        logger.warning("LLM planning failed (%s); falling back to the offline planner.", exc)
        plan = _fallback_plan(description, meeting_notes, config)
        plan.planning_note = (
            f"LLM planning skipped: {_short_planning_failure_reason(exc)} — used the built-in offline planner instead."
        )
        return plan

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
