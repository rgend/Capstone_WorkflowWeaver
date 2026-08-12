import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ToolName(str, Enum):
    NOTION = "notion"
    GOOGLE_DRIVE = "google_drive"
    TEAMS = "teams"
    NONE = "none"


class WorkflowConfig(BaseModel):
    workspace: str | None = None
    notion_page_id: str | None = None
    drive_folder_id: str | None = None
    teams_channel: str | None = None


class WorkflowRequest(BaseModel):
    description: str = Field(min_length=1, max_length=8000)
    template_id: str | None = None
    meeting_notes: str | None = None
    config: WorkflowConfig = Field(default_factory=WorkflowConfig)


class PlannedStep(BaseModel):
    step_id: str = Field(default_factory=lambda: new_id("step"))
    index: int
    tool: ToolName
    action: str
    description: str
    input: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class WorkflowPlan(BaseModel):
    intent_summary: str
    steps: list[PlannedStep]


class StepResult(BaseModel):
    step_id: str
    index: int
    tool: ToolName
    action: str
    description: str
    status: StepStatus
    attempts: int = 0
    output: dict[str, Any] | None = None
    error: str | None = None
    rollback_action: dict[str, Any] | None = None
    started_at: float | None = None
    finished_at: float | None = None
    langfuse_observation_id: str | None = None


class ExecutionReport(BaseModel):
    run_id: str
    description: str
    status: RunStatus
    intent_summary: str | None = None
    steps: list[StepResult] = Field(default_factory=list)
    created_outputs: dict[str, Any] = Field(default_factory=dict)
    started_at: float
    finished_at: float | None = None
    error: str | None = None
    langfuse_trace_url: str | None = None
    mock_mode: bool = True


class WorkflowSummary(BaseModel):
    run_id: str
    description: str
    status: RunStatus
    started_at: float
    finished_at: float | None = None
    template_id: str | None = None


class WorkflowTemplate(BaseModel):
    id: str
    name: str
    category: str
    icon: str
    description: str
    nl_description: str
    default_config: WorkflowConfig = Field(default_factory=WorkflowConfig)


class SSEEvent(BaseModel):
    run_id: str
    seq: int
    node: str
    status: StepStatus | RunStatus
    message: str
    step_id: str | None = None
    detail: dict[str, Any] | None = None
    timestamp: float = 0.0
