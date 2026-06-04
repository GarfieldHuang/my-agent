"""Agent 主迴圈：使用 OpenAI Responses API 打 ChatGPT 訂閱後端。"""
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

    # ── Core loop ─────────────────────────────────

    async def _run_loop(self) -> str:
        tools = self.mcp.openai_tools()
        input_items: list = list(self.history)

        for _ in range(MAX_TOOL_ROUNDS):
            # 手動迭代 SSE events（get_final_response() 的 output 是空的）
            text_chunks: list[str] = []
            func_calls: dict = {}   # call_id → {name, arguments, call_id}

            stream = await self.client.responses.create(
                model=self.model,
                input=input_items,
                instructions=self.system_prompt,
                tools=tools if tools else NOT_GIVEN,
                store=False,
                stream=True,
            )

            async for event in stream:
                etype = getattr(event, "type", "")
                print(f"[DEBUG] {etype!r}  {event!r}")

                if etype == "response.output_text.delta":
                    text_chunks.append(getattr(event, "delta", ""))

                elif etype == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if item and getattr(item, "type", "") == "function_call":
                        cid = item.call_id
                        func_calls[cid] = {
                            "call_id": cid,
                            "name": item.name,
                            "arguments": "",
                        }

                elif etype == "response.function_call_arguments.delta":
                    cid = getattr(event, "call_id", None)
                    if cid and cid in func_calls:
                        func_calls[cid]["arguments"] += getattr(event, "delta", "")

            text    = "".join(text_chunks)
            fc_list = list(func_calls.values())
            print(f"[DEBUG] text={text!r}  func_calls={[f['name'] for f in fc_list]}\n")

            if not fc_list:
                return text

            # 執行工具，繼續下一輪
            for fc in fc_list:
                try:
                    args   = json.loads(fc["arguments"])
                    result = await self.mcp.call(fc["name"], args)
                except Exception as e:
                    result = f"[ERROR] {e}"

                input_items.append({
                    "type":    "function_call_output",
                    "call_id": fc["call_id"],
                    "output":  result,
                })
                input_items.append({
                    "type": "function_call",
                    "call_id": fc["call_id"],
                    "name": fc["name"],
                    "arguments": fc["arguments"],
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
