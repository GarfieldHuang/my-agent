"""Agent 主迴圈：使用 OpenAI Responses API 打 ChatGPT 訂閱後端。

chatgpt.com/backend-api/codex/responses 使用 Responses API 格式，
與 Chat Completions API 不同：
  - 系統提示用 "instructions" 參數（或 input 裡的 "system" role）
  - 工具呼叫結果用 {"type": "function_call_output", ...}
  - store=False（Codex 後端不儲存對話）
"""
import json
import os

from openai import AsyncOpenAI, NOT_GIVEN

from .files import FileUploader
from .mcp_manager import MCPManager

MAX_TOOL_ROUNDS = 10


class Agent:
    def __init__(
        self,
        client: AsyncOpenAI,
        mcp: MCPManager,
        model: str | None = None,
        system_prompt: str = "You are a helpful assistant.",
    ):
        self.client        = client
        self.mcp           = mcp
        self.model         = model or os.getenv("OPENAI_MODEL", "gpt-5.4")
        self.system_prompt = system_prompt
        self.files         = FileUploader(client)
        # history 存簡單的 user/assistant 字串對，送出時再組成 Responses API 格式
        self.history: list[dict] = []

    # ── Public API ────────────────────────────────

    async def chat(self, user_input: str, attachments: list[str] | None = None) -> str:
        content = await self._build_content(user_input, attachments or [])
        self.history.append({"role": "user", "content": content})

        reply = await self._run_loop()
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def clear_history(self) -> None:
        self.history.clear()

    # ── Core loop（Responses API）─────────────────

    async def _run_loop(self) -> str:
        """
        Responses API 的 tool-call 迴圈。
        每輪把完整 input（含 function_call_output）傳給模型，
        直到模型不再呼叫工具為止。
        """
        tools = self.mcp.openai_tools()

        # Codex 後端要求 instructions 用獨立參數，不能放在 input 陣列
        input_items: list = list(self.history)

        for _ in range(MAX_TOOL_ROUNDS):
            # Codex 後端強制要求串流（stream must be true）
            async with self.client.responses.stream(
                model=self.model,
                input=input_items,
                instructions=self.system_prompt,
                tools=tools if tools else NOT_GIVEN,
                store=False,
            ) as stream:
                response = await stream.get_final_response()

            # ── DEBUG：印出完整 response ──
            print(f"\n[DEBUG] response type: {type(response)}")
            print(f"[DEBUG] response fields: {[f for f in dir(response) if not f.startswith('_')]}")
            try:
                print(f"[DEBUG] response dict: {response.model_dump()}")
            except Exception as e:
                print(f"[DEBUG] model_dump error: {e}")
                print(f"[DEBUG] response repr: {response!r}")
            print(f"\n[DEBUG] response.output ({len(response.output)} items):")

            # 分類 output items
            text_blocks = []
            func_calls  = []
            for item in response.output:
                itype = getattr(item, "type", None)
                if itype == "message":
                    for block in getattr(item, "content", []):
                        btype = getattr(block, "type", None)
                        btext = getattr(block, "text", None)
                        print(f"  [DEBUG] message block type={btype!r} text={btext!r}")
                        if btype == "output_text" and btext:
                            text_blocks.append(btext)
                elif itype == "function_call":
                    func_calls.append(item)

            print(f"[DEBUG] text_blocks={text_blocks}  func_calls={len(func_calls)}\n")

            if not func_calls:
                return "".join(text_blocks)

            input_items.extend(response.output)

            for tc in func_calls:
                try:
                    args   = json.loads(tc.arguments)
                    result = await self.mcp.call(tc.name, args)
                except Exception as e:
                    result = f"[ERROR] {type(e).__name__}: {e}"

                input_items.append({
                    "type":    "function_call_output",
                    "call_id": tc.call_id,
                    "output":  result,
                })

        return "（已達工具呼叫上限）"

    # ── Helpers ───────────────────────────────────

    async def _build_content(self, text: str, attachments: list[str]) -> list | str:
        if not attachments:
            return text
        parts: list = [{"type": "input_text", "text": text}]
        for path in attachments:
            parts.append(await self.files.upload(path))
        return parts
