"""Google Drive MCP adapter.

Real mode launches a Google Drive MCP server over stdio and calls its
file-creation tool (discovered heuristically since community server tool
names vary by package/version). Falls back to a mock response when Google
Drive isn't configured or MOCK_MODE is enabled.
"""

from app.core.config import Settings
from app.core.errors import ToolExecutionError
from app.mcp.client import MCPStdioClient, MCPUnavailableError
from app.mcp.mock import mock_drive_file


class GoogleDriveAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def use_mock(self) -> bool:
        return self.settings.mock_mode or not self.settings.gdrive_configured

    async def _new_client(self) -> MCPStdioClient:
        # A fresh connection per call, entered and closed within the same
        # coroutine/task: LangGraph runs each node in its own asyncio task,
        # and anyio's cancel scopes (used internally by the stdio transport)
        # must be entered and exited in the same task, so a client cached
        # across node invocations breaks on close.
        args = [a.strip() for a in self.settings.gdrive_mcp_args.split(",") if a.strip()]
        client = MCPStdioClient(
            command=self.settings.gdrive_mcp_command,
            args=args,
            env={
                "GOOGLE_CREDENTIALS_PATH": self.settings.google_credentials_path,
                "GDRIVE_TOKEN_PATH": self.settings.gdrive_token_path,
            },
        )
        await client.connect()
        return client

    async def create_document(self, name: str, content: str, folder_id: str | None = None) -> dict:
        if self.use_mock:
            return mock_drive_file(name)

        target_folder = folder_id or self.settings.google_drive_folder_id
        client = None
        try:
            client = await self._new_client()
            tool_name = await client.find_tool(["create", "file"]) or await client.find_tool(["upload"])
            if not tool_name:
                raise ToolExecutionError(
                    "google_drive", "create_document", "no create/upload tool exposed by MCP server"
                )
            result = await client.call_tool(
                tool_name,
                {
                    "name": name,
                    "mimeType": "text/plain",
                    "content": content,
                    "parents": [target_folder] if target_folder else [],
                },
            )
            if result["is_error"]:
                raise ToolExecutionError("google_drive", "create_document", result["text"])
            return {"mock": False, "raw_response": result["text"], "name": name}
        except MCPUnavailableError as exc:
            raise ToolExecutionError("google_drive", "create_document", str(exc), retriable=False) from exc
        finally:
            if client:
                await client.close()

    async def delete_file(self, file_id: str) -> dict:
        if self.use_mock or file_id.startswith("mock-drive-file"):
            return {"mock": True, "file_id": file_id, "deleted": True}
        client = None
        try:
            client = await self._new_client()
            tool_name = await client.find_tool(["delete", "file"])
            if not tool_name:
                return {"mock": False, "file_id": file_id, "deleted": False, "reason": "no delete tool exposed"}
            result = await client.call_tool(tool_name, {"fileId": file_id})
            return {"mock": False, "file_id": file_id, "deleted": not result["is_error"]}
        except MCPUnavailableError as exc:
            raise ToolExecutionError("google_drive", "delete_file", str(exc), retriable=False) from exc
        finally:
            if client:
                await client.close()

    async def close(self) -> None:
        """No persistent connection to close — kept for RunContext.aclose() symmetry."""
