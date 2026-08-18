"""Google Drive MCP adapter.

Real mode launches a Google Drive MCP server over stdio and calls its
file-creation tool (discovered heuristically since community server tool
names vary by package/version). Content is uploaded as HTML and converted to
a native Google Doc by Drive's import conversion (see gdrive_server.py) so
headings/bold/lists survive, rather than landing as a flat .txt file. Falls
back to a mock response when Google Drive isn't configured or MOCK_MODE is
enabled.
"""

import json

from app.core.config import Settings
from app.core.errors import ToolExecutionError
from app.core.formatting import plain_content_to_html, sections_to_html, timestamp_suffix
from app.mcp.client import MCPStdioClient, MCPUnavailableError
from app.mcp.mock import mock_drive_file


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}


def _doc_title(name: str) -> str:
    # The uploaded file becomes a native Google Doc regardless of the name's
    # extension, so drop a trailing ".txt"/".md" that would otherwise be a
    # misleading leftover from the plain-text-document mental model.
    for ext in (".txt", ".md"):
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return name


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

    async def create_document(
        self,
        name: str,
        content: str = "",
        folder_id: str | None = None,
        sections: list[dict] | None = None,
    ) -> dict:
        # Stamp the title with the generation time — same convention as
        # Notion pages — so the most recently created report is identifiable
        # at a glance in a Drive folder listing full of similarly-named docs.
        # Title-only: the doc body stays focused on the actual content.
        if self.use_mock:
            return mock_drive_file(f"{_doc_title(name)} — {timestamp_suffix()}")

        client = None
        try:
            title = f"{_doc_title(name)} — {timestamp_suffix()}"
            html = sections_to_html(title, sections) if sections else plain_content_to_html(title, content)
            target_folder = folder_id or self.settings.google_drive_folder_id

            client = await self._new_client()
            tool_name = await client.find_tool(["create", "file"]) or await client.find_tool(["upload"])
            if not tool_name:
                raise ToolExecutionError(
                    "google_drive", "create_document", "no create/upload tool exposed by MCP server"
                )
            result = await client.call_tool(
                tool_name,
                {
                    "name": title,
                    "mimeType": "text/html",
                    "content": html,
                    "parents": [target_folder] if target_folder else [],
                },
            )
            if result["is_error"]:
                raise ToolExecutionError("google_drive", "create_document", result["text"])
            parsed = _parse_json(result["text"])
            return {
                "mock": False,
                "file_id": parsed.get("id"),
                "url": parsed.get("webViewLink"),
                "name": title,
                "raw_response": result["text"],
            }
        except MCPUnavailableError as exc:
            raise ToolExecutionError("google_drive", "create_document", str(exc), retriable=False) from exc
        except ToolExecutionError:
            raise
        except Exception as exc:
            # A malformed LLM-planned `sections`/`content` shape (or any other
            # formatting surprise) must still come back as a classified,
            # non-retriable step failure rather than an unhandled crash that
            # bypasses the graph's retry/rollback accounting.
            raise ToolExecutionError("google_drive", "create_document", repr(exc), retriable=False) from exc
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
