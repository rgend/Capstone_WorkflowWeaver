import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.core.models import RunStatus, SSEEvent, StepStatus
from app.integrations.slack_client import SlackClient
from app.mcp.gdrive_adapter import GoogleDriveAdapter
from app.mcp.notion_adapter import NotionAdapter

EmitFn = Callable[[SSEEvent], Awaitable[None]]


@dataclass
class RunContext:
    run_id: str
    settings: Settings
    emit_raw: EmitFn
    notion: NotionAdapter
    gdrive: GoogleDriveAdapter
    slack: SlackClient
    langfuse_trace: Any = None
    rollback_stack: list[dict[str, Any]] = field(default_factory=list)
    _seq: int = 0

    async def emit(
        self,
        node: str,
        status: StepStatus | RunStatus,
        message: str,
        step_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._seq += 1
        await self.emit_raw(
            SSEEvent(
                run_id=self.run_id,
                seq=self._seq,
                node=node,
                status=status,
                message=message,
                step_id=step_id,
                detail=detail,
                timestamp=time.time(),
            )
        )

    async def aclose(self) -> None:
        await self.notion.close()
        await self.gdrive.close()
