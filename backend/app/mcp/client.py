"""Generic Model Context Protocol (MCP) stdio client.

Launches an MCP server as a local subprocess over stdio (the same transport
Claude Desktop/Code uses to run MCP servers) and exposes tool discovery +
invocation. This is transport-agnostic to which server binary is launched —
Notion and Google Drive adapters build on top of this.
"""

import shutil
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPUnavailableError(Exception):
    pass


class MCPStdioClient:
    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None):
        self.command = command
        self.args = args
        self.env = env or {}
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None
        self._tools_cache: list[Any] | None = None

    @staticmethod
    def is_launchable(command: str) -> bool:
        return shutil.which(command) is not None

    async def connect(self) -> None:
        if not self.is_launchable(self.command):
            raise MCPUnavailableError(f"MCP server command '{self.command}' not found on PATH.")
        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=self.command, args=self.args, env=self.env or None)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def list_tools(self) -> list[Any]:
        if self.session is None:
            raise MCPUnavailableError("MCP session not connected")
        if self._tools_cache is None:
            result = await self.session.list_tools()
            self._tools_cache = result.tools
        return self._tools_cache

    async def find_tool(self, keywords: list[str]) -> str | None:
        """Heuristically pick the best-matching tool name for a set of keywords."""
        tools = await self.list_tools()
        best_name, best_score = None, 0
        for tool in tools:
            name = tool.name.lower()
            desc = (tool.description or "").lower()
            score = sum(1 for kw in keywords if kw in name) * 2
            score += sum(1 for kw in keywords if kw in desc)
            if score > best_score:
                best_name, best_score = tool.name, score
        return best_name

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.session is None:
            raise MCPUnavailableError("MCP session not connected")
        result = await self.session.call_tool(name, arguments)
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return {"is_error": bool(result.isError), "text": "\n".join(parts), "raw": result}

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self.session = None
