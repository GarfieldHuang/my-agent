"""管理多個 MCP server 連線，並把所有 tools 合併成 OpenAI function calling 格式。"""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import yaml
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

try:
    from mcp.client.sse import sse_client
    HAS_SSE = True
except ImportError:
    HAS_SSE = False


@dataclass
class ToolEntry:
    name: str
    server_name: str
    session: ClientSession
    schema: dict  # OpenAI function definition


class MCPManager:
    """載入 mcp_config.yaml，建立所有 server 連線，提供統一工具查詢與執行介面。"""

    def __init__(self, config_path: str = "mcp_config.yaml"):
        self.config_path = config_path
        self._tools: dict[str, ToolEntry] = {}
        self._sessions: list[ClientSession] = []
        self._exit_stack_closers: list[Any] = []

    # ── Lifecycle ─────────────────────────────────

    async def start(self) -> None:
        """啟動所有設定的 MCP server 並收集 tools。"""
        config = self._load_config()
        servers = config.get("servers") or {}
        for name, spec in servers.items():
            if spec is None:
                continue
            try:
                session = await self._connect(name, spec)
                self._sessions.append(session)
                await self._register_tools(name, session)
            except Exception as e:
                print(f"[MCP] ⚠ 無法連線 {name!r}: {e}")

    async def stop(self) -> None:
        for closer in reversed(self._exit_stack_closers):
            try:
                await closer()
            except Exception:
                pass

    # ── Tool access ───────────────────────────────

    def openai_tools(self) -> list[dict]:
        """回傳可直接傳給 OpenAI API 的 tools 陣列。"""
        return [entry.schema for entry in self._tools.values()]

    async def call(self, tool_name: str, arguments: dict) -> str:
        """執行指定工具，回傳純文字結果。"""
        entry = self._tools.get(tool_name)
        if entry is None:
            raise KeyError(f"找不到工具 {tool_name!r}，可用：{list(self._tools)}")

        result = await entry.session.call_tool(tool_name, arguments)

        # 把 MCP content 塊轉成純文字
        parts = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    # ── Internal ──────────────────────────────────

    def _load_config(self) -> dict:
        try:
            with open(self.config_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    async def _connect(self, name: str, spec: dict) -> ClientSession:
        transport = spec.get("transport", "stdio")

        if transport == "stdio":
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env=spec.get("env"),
            )
            read, write, closer = await self._enter(stdio_client(params))
        elif transport == "sse":
            if not HAS_SSE:
                raise ImportError("需要安裝 mcp[sse] 才能使用 SSE transport")
            read, write, closer = await self._enter(sse_client(spec["url"]))
        else:
            raise ValueError(f"未知 transport: {transport!r}")

        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        self._exit_stack_closers.append(session.__aexit__)
        return session

    async def _enter(self, cm):
        """手動進入 async context manager，回傳 (read, write, closer)。"""
        result = await cm.__aenter__()
        self._exit_stack_closers.append(cm.__aexit__)
        return *result, cm.__aexit__

    async def _register_tools(self, server_name: str, session: ClientSession) -> None:
        response = await session.list_tools()
        for tool in response.tools:
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                },
            }
            self._tools[tool.name] = ToolEntry(
                name=tool.name,
                server_name=server_name,
                session=session,
                schema=schema,
            )
