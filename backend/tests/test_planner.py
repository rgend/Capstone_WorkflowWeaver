import pytest

from app.core.config import Settings
from app.core.models import ToolName, WorkflowConfig
from app.graph.llm import generate_plan


@pytest.mark.asyncio
async def test_fallback_plan_routes_notion_and_teams():
    settings = Settings(llm_api_key=None, mock_mode=True)
    plan = await generate_plan(
        description="Create a Notion project page and post a summary to Microsoft Teams.",
        meeting_notes="- item one\n- item two",
        config=WorkflowConfig(),
        settings=settings,
    )
    tools = {step.tool for step in plan.steps}
    assert ToolName.NOTION in tools
    assert ToolName.TEAMS in tools
    assert ToolName.GOOGLE_DRIVE not in tools


@pytest.mark.asyncio
async def test_fallback_plan_routes_drive_when_mentioned():
    settings = Settings(llm_api_key=None, mock_mode=True)
    plan = await generate_plan(
        description="Save the incident postmortem report as a document in our drive.",
        meeting_notes=None,
        config=WorkflowConfig(),
        settings=settings,
    )
    tools = {step.tool for step in plan.steps}
    assert ToolName.GOOGLE_DRIVE in tools
