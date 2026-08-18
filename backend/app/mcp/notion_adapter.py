"""Notion MCP adapter.

Real mode launches the official `@notionhq/notion-mcp-server` over stdio and
calls its Notion-API-shaped tools (its tool names mirror Notion's OpenAPI
operationIds, e.g. "API-post-page"). Since third-party MCP servers can rename
or version their tools, we try the known name first and fall back to
heuristic keyword discovery via MCPStdioClient.find_tool so this keeps working
across server versions. Falls back to a mock response when Notion isn't
configured or MOCK_MODE is enabled.

Each report is embedded as a single collapsible `toggle` block directly in
the configured parent ("hub") page, rather than as a separate Notion page.
Two earlier designs were tried and rejected:
  - A plain child page under the hub: Notion auto-renders a native
    `child_page` block for *any* page created with that parent, so each
    report showed up twice — once as our own index entry, once as Notion's
    own listing.
  - Filing reports under a hidden "archive" container page (to dodge the
    above): if that one container page is ever deleted/trashed (by a user
    poking around, or anything else), every report nested under it is
    orphaned along with it — this actually happened during testing and lost
    real report content.
A toggle block has neither problem: it's owned directly by the hub page (so
there's no separate object to delete out from under it), and it's the only
representation of the report — nothing else auto-renders alongside it.
Ordering is still "newest first" via the same anchor-and-`after` mechanism,
since Notion's public API has no block-reorder/move endpoint.
"""

import json
import logging

from app.core.config import Settings
from app.core.errors import ToolExecutionError
from app.core.formatting import notion_blocks_from_sections, timestamp_suffix
from app.mcp.client import MCPStdioClient, MCPUnavailableError
from app.mcp.mock import mock_notion_page

logger = logging.getLogger(__name__)

# Marker heading for the report list kept at the top of the parent page.
# Every new report's toggle block is inserted directly `after` this same
# anchor block, so each insert lands above whatever was inserted last time.
_INDEX_ANCHOR_TEXT = "\U0001f4da Workflow Reports"


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}


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
        # Stamp the title with the generation time so the most recently
        # uploaded report is identifiable at a glance among a history of
        # similarly-named reports — applied uniformly in mock and live mode
        # so dry-run demos match real behavior. The timestamp lives in the
        # title only; the report body stays focused on the actual content.
        if self.use_mock:
            return mock_notion_page(f"{title} — {timestamp_suffix()}")

        client = None
        try:
            stamped_title = f"{title} — {timestamp_suffix()}"
            hub_id = parent_page_id or self.settings.notion_page_id
            client = await self._new_client()

            anchor_id = await self._ensure_index_anchor(client, hub_id)
            toggle_block = {
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"type": "text", "text": {"content": f"\U0001f4c4 {stamped_title}"}}],
                    "children": notion_blocks_from_sections(sections),
                },
            }
            insert_args = {"block_id": hub_id, "children": [toggle_block]}
            if anchor_id:
                insert_args["after"] = anchor_id

            insert_tool = await client.find_tool(["patch", "block", "children"]) or "API-patch-block-children"
            result = await client.call_tool(insert_tool, insert_args)
            if result["is_error"]:
                raise ToolExecutionError("notion", "create_project_page", result["text"])
            results = _parse_json(result["text"]).get("results", [])
            block_id = results[0]["id"] if results else None
            if not block_id:
                raise ToolExecutionError("notion", "create_project_page", "no block id returned for new report")

            return {
                "mock": False,
                "block_id": block_id,
                "url": await self._deep_link(client, hub_id, block_id),
                "title": stamped_title,
            }
        except MCPUnavailableError as exc:
            raise ToolExecutionError("notion", "create_project_page", str(exc), retriable=False) from exc
        except ToolExecutionError:
            raise
        except Exception as exc:
            # A malformed LLM-planned `sections`/`title` shape (or any other
            # formatting surprise) must still come back as a classified,
            # non-retriable step failure rather than an unhandled crash that
            # bypasses the graph's retry/rollback accounting.
            raise ToolExecutionError("notion", "create_project_page", repr(exc), retriable=False) from exc
        finally:
            if client:
                await client.close()

    async def _ensure_index_anchor(self, client: MCPStdioClient, hub_id: str) -> str | None:
        """Find the report-list anchor heading in the hub page's children,
        creating it if this is the first report filed there. Best-effort:
        returns None on failure, in which case the new report's toggle is
        just appended at the end instead of inserted at the top — never
        blocks report creation over this.
        """
        try:
            list_tool = await client.find_tool(["get", "block", "children"]) or "API-get-block-children"
            result = await client.call_tool(list_tool, {"block_id": hub_id})
            if not result["is_error"]:
                data = _parse_json(result["text"])
                for block in data.get("results", []):
                    block_type = block.get("type")
                    rich_text = (block.get(block_type) or {}).get("rich_text") or []
                    text = "".join(rt.get("plain_text", "") for rt in rich_text)
                    if text.strip() == _INDEX_ANCHOR_TEXT:
                        return block["id"]

            append_tool = await client.find_tool(["patch", "block", "children"]) or "API-patch-block-children"
            result = await client.call_tool(
                append_tool,
                {
                    "block_id": hub_id,
                    "children": [
                        {
                            "object": "block",
                            "type": "heading_2",
                            "heading_2": {"rich_text": [{"type": "text", "text": {"content": _INDEX_ANCHOR_TEXT}}]},
                        }
                    ],
                },
            )
            if result["is_error"]:
                return None
            results = _parse_json(result["text"]).get("results", [])
            return results[0]["id"] if results else None
        except Exception:
            logger.warning("Failed to set up the report list anchor under %s.", hub_id)
            return None

    async def _deep_link(self, client: MCPStdioClient, hub_id: str, block_id: str) -> str | None:
        """A direct link to the new report's toggle within the hub page
        (Notion's block-anchor URL fragment). Best-effort: a missing link
        here doesn't affect the report itself, only how nicely a step's
        output links back to it (e.g. from the Slack notification).
        """
        try:
            tool = await client.find_tool(["retrieve", "a", "page"]) or "API-retrieve-a-page"
            result = await client.call_tool(tool, {"page_id": hub_id})
            if result["is_error"]:
                return None
            hub_url = _parse_json(result["text"]).get("url")
            if not hub_url:
                return None
            return f"{hub_url}#{block_id.replace('-', '')}"
        except Exception:
            logger.warning("Failed to build a deep link for report block %s.", block_id)
            return None

    async def delete_report(self, block_id: str) -> dict:
        """Rollback for a failed run: delete the report's toggle block.
        Notion's `in_trash` delete is recoverable from the workspace's trash,
        same safety margin `archived: true` gave the old page-based design.
        """
        if self.use_mock or block_id.startswith("mock-notion-page"):
            return {"mock": True, "block_id": block_id, "archived": True}
        client = None
        try:
            client = await self._new_client()
            tool_name = await client.find_tool(["delete", "a", "block"]) or "API-delete-a-block"
            result = await client.call_tool(tool_name, {"block_id": block_id})
            return {"mock": False, "block_id": block_id, "archived": not result["is_error"]}
        except MCPUnavailableError as exc:
            raise ToolExecutionError("notion", "delete_report", str(exc), retriable=False) from exc
        finally:
            if client:
                await client.close()

    async def close(self) -> None:
        """No persistent connection to close — kept for RunContext.aclose() symmetry."""
