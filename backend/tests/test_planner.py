import pytest

from app.core.config import Settings
from app.core.models import ToolName, WorkflowConfig
from app.graph.llm import generate_plan


@pytest.mark.asyncio
async def test_fallback_plan_always_runs_the_full_pipeline():
    settings = Settings(llm_api_key=None, mock_mode=True)
    plan = await generate_plan(
        description="Create a Notion project page and post a summary to Slack.",
        meeting_notes="- item one\n- item two",
        config=WorkflowConfig(),
        settings=settings,
    )
    assert [step.tool for step in plan.steps] == [ToolName.NOTION, ToolName.GOOGLE_DRIVE, ToolName.SLACK]


@pytest.mark.asyncio
async def test_fallback_plan_runs_full_pipeline_even_without_drive_or_slack_mentioned():
    settings = Settings(llm_api_key=None, mock_mode=True)
    plan = await generate_plan(
        description="Save the incident postmortem report as a document in our drive.",
        meeting_notes=None,
        config=WorkflowConfig(),
        settings=settings,
    )
    tools = {step.tool for step in plan.steps}
    assert tools == {ToolName.NOTION, ToolName.GOOGLE_DRIVE, ToolName.SLACK}
