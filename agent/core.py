"""Agent 主迴圈：把 OpenAI、MCP tools、檔案上傳串在一起。"""
import json
import os

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .files import FileUploader
from .mcp_manager import MCPManager

MAX_TOOL_ROUNDS = 10  # 防止無限 tool-call 迴圈


class Agent:
    def __init__(
        self,
        client: AsyncOpenAI,
        mcp: MCPManager,
        model: str | None = None,
        system_prompt: str = "You are a helpful assistant.",
    ):
        self.client = client
        self.mcp = mcp
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.system_prompt = system_prompt
        self.files = FileUploader(client)
        self.history: list[ChatCompletionMessageParam] = []

    # ── Public API ────────────────────────────────

    async def chat(self, user_input: str, attachments: list[str] | None = None) -> str:
        """送出一輪對話，回傳 assistant 最終文字回覆。"""
        content = await self._build_content(user_input, attachments or [])
        self.history.append({"role": "user", "content": content})

        reply = await self._run_loop()
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def clear_history(self) -> None:
        self.history.clear()

    # ── Core loop ─────────────────────────────────

    async def _run_loop(self) -> str:
        """呼叫 OpenAI，處理 tool calls，直到模型給出純文字回覆。"""
        tools = self.mcp.openai_tools()

        for round_num in range(MAX_TOOL_ROUNDS):
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=self._system_messages(),
                tools=tools if tools else None,
            )

            message = response.choices[0].message

            # 模型直接回覆文字，結束迴圈
            if not message.tool_calls:
                return message.content or ""

            # 把 assistant 的 tool_call 意圖加入 history
            self.history.append(message)

            # 執行所有 tool calls（失敗時 _execute_tool_calls 會回傳錯誤字串給模型）
            tool_results = await self._execute_tool_calls(message.tool_calls)
            self.history.extend(tool_results)

        # 達到上限，要求模型根據目前資訊直接作答
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                *self._system_messages(),
                {
                    "role": "user",
                    "content": "（已達工具呼叫上限，請根據目前資訊直接回覆）",
                },
            ],
        )
        return response.choices[0].message.content or ""

    # ── Helpers ───────────────────────────────────

    def _system_messages(self) -> list[ChatCompletionMessageParam]:
        return [{"role": "system", "content": self.system_prompt}, *self.history]

    async def _build_content(self, text: str, attachments: list[str]) -> list | str:
        if not attachments:
            return text
        parts: list = [{"type": "text", "text": text}]
        for path in attachments:
            parts.append(await self.files.upload(path))
        return parts

    async def _execute_tool_calls(self, tool_calls) -> list[ChatCompletionMessageParam]:
        """執行一批 tool calls，回傳 tool result messages。"""
        results = []
        for tc in tool_calls:
            fn = tc.function
            try:
                args = json.loads(fn.arguments)
                output = await self.mcp.call(fn.name, args)
            except Exception as e:
                output = f"[ERROR] {type(e).__name__}: {e}"

            results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": output,
            })
        return results
