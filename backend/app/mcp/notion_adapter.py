"""Notion MCP adapter.

Real mode launches the official `@notionhq/notion-mcp-server` over stdio and
calls its Notion-API-shaped tools (its tool names mirror Notion's OpenAPI
operationIds, e.g. "API-post-page"). Since third-party MCP servers can rename
or version their tools, we try the known name first and fall back to
heuristic keyword discovery via MCPStdioClient.find_tool so this keeps working
across server versions. Falls back to a mock response when Notion isn't
configured or MOCK_MODE is enabled.
"""

from app.core.config import Settings
from app.core.errors import ToolExecutionError
from app.mcp.client import MCPStdioClient, MCPUnavailableError
from app.mcp.mock import mock_notion_page


class NotionAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def use_mock(self) -> bool:
        return self.settings.mock_mode or not self.settings.notion_configured

    async def _new_client(self) -> MCPStdioClient:
        # A fresh connection per call, entered and closed within the same
        # coroutine/task: LangGraph runs each node in its own asyncio task,
        # and anyio's cancel scopes (used internally by the stdio transport)
        # must be entered and exited in the same task, so a client cached
        # across node invocations breaks on close.
        args = [a.strip() for a in self.settings.notion_mcp_args.split(",") if a.strip()]
        client = MCPStdioClient(
            command=self.settings.notion_mcp_command,
            args=args,
            env={"NOTION_TOKEN": self.settings.notion_token or ""},
        )
        await client.connect()
        return client

    async def create_project_page(self, title: str, sections: list[dict], parent_page_id: str | None = None) -> dict:
        if self.use_mock:
            return mock_notion_page(title)

        parent_id = parent_page_id or self.settings.notion_page_id
        children = []
        for section in sections:
            children.append(
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": section["heading"]}}]},
                }
            )
            for line in section.get("lines", []):
                children.append(
                    {
                        "object": "block",
                        "type": "to_do" if section.get("as_todo") else "paragraph",
                        **(
                            {"to_do": {"rich_text": [{"type": "text", "text": {"content": line}}], "checked": False}}
                            if section.get("as_todo")
                            else {"paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}}
                        ),
                    }
                )

        body = {
            "parent": {"page_id": parent_id},
            "properties": {"title": {"title": [{"text": {"content": title}}]}},
            "children": children,
        }

        client = None
        try:
            client = await self._new_client()
            tool_name = await client.find_tool(["post", "page"]) or "API-post-page"
            result = await client.call_tool(tool_name, body)
            if result["is_error"]:
                raise ToolExecutionError("notion", "create_project_page", result["text"])
            return {"mock": False, "raw_response": result["text"], "title": title}
        except MCPUnavailableError as exc:
            raise ToolExecutionError("notion", "create_project_page", str(exc), retriable=False) from exc
        finally:
            if client:
                await client.close()

    async def archive_page(self, page_id: str) -> dict:
        if self.use_mock or page_id.startswith("mock-notion-page"):
            return {"mock": True, "page_id": page_id, "archived": True}
        client = None
        try:
            client = await self._new_client()
            tool_name = await client.find_tool(["patch", "page"]) or "API-patch-page"
            result = await client.call_tool(tool_name, {"page_id": page_id, "archived": True})
            return {"mock": False, "page_id": page_id, "archived": not result["is_error"]}
        except MCPUnavailableError as exc:
            raise ToolExecutionError("notion", "archive_page", str(exc), retriable=False) from exc
        finally:
            if client:
                await client.close()

    async def close(self) -> None:
        """No persistent connection to close — kept for RunContext.aclose() symmetry."""
