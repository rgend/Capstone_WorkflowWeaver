from typing import Any, TypedDict


class GraphState(TypedDict):
    run_id: str
    description: str
    meeting_notes: str | None
    config: dict[str, Any]
    intent_summary: str | None
    plan: dict[str, Any] | None
    steps: list[dict[str, Any]]
    current_step_index: int
    status: str
    error: str | None
