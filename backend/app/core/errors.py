class ToolExecutionError(Exception):
    """Raised when an MCP tool call or webhook call fails. Caught by the graph's retry node."""

    def __init__(self, tool: str, action: str, message: str, retriable: bool = True):
        self.tool = tool
        self.action = action
        self.retriable = retriable
        super().__init__(f"[{tool}:{action}] {message}")


class PlanningError(Exception):
    """Raised when the LLM fails to produce a usable structured plan."""
