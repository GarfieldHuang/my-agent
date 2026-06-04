"""Agent 主迴圈：Responses API + 反思推理能力。"""
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
        reasoning_effort: str = "medium",   # none/low/medium/high/xhigh
    ):
        self.client           = client
        self.mcp              = mcp
        self.model            = model or os.getenv("OPENAI_MODEL", "gpt-5.4")
        self.system_prompt    = system_prompt
        self.reasoning_effort = reasoning_effort
        self.files            = FileUploader(client)
        self.history: list[dict] = []

    # ── Public API ────────────────────────────────

    async def chat(
        self,
        user_input: str,
        attachments: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        回傳 (thinking, answer)。
        thinking：模型的推理過程（可能為空字串）
        answer：最終回覆
        """
        content = await self._build_content(user_input, attachments or [])
        self.history.append({"role": "user", "content": content})

        thinking, reply = await self._run_loop()
        self.history.append({"role": "assistant", "content": reply})
        return thinking, reply

    def clear_history(self) -> None:
        self.history.clear()

    # ── Core loop ─────────────────────────────────

    async def _run_loop(self) -> tuple[str, str]:
        tools = self.mcp.openai_tools()
        input_items: list = list(self.history)

        # reasoning 參數：effort 為 "none" 時不送推理
        reasoning_param = NOT_GIVEN
        if self.reasoning_effort and self.reasoning_effort != "none":
            reasoning_param = {
                "effort":  self.reasoning_effort,
                "summary": "auto",
            }

        for _ in range(MAX_TOOL_ROUNDS):
            thinking_chunks: list[str] = []
            text_chunks:     list[str] = []
            func_calls: dict[str, dict] = {}

            stream = await self.client.responses.create(
                model=self.model,
                input=input_items,
                instructions=self.system_prompt,
                tools=tools if tools else NOT_GIVEN,
                store=False,
                stream=True,
                reasoning=reasoning_param,
            )

            async for event in stream:
                etype = getattr(event, "type", "")

                # ── 推理摘要（思考過程）────────────────
                if etype == "response.reasoning_summary_text.delta":
                    thinking_chunks.append(getattr(event, "delta", ""))

                # ── 最終回覆文字 ──────────────────────
                elif etype == "response.output_text.delta":
                    text_chunks.append(getattr(event, "delta", ""))

                # ── 工具呼叫：開始 ────────────────────
                elif etype == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if item and getattr(item, "type", "") == "function_call":
                        cid = item.call_id
                        func_calls[cid] = {
                            "call_id":   cid,
                            "name":      item.name,
                            "arguments": "",
                        }

                # ── 工具呼叫：參數串流 ─────────────────
                elif etype == "response.function_call_arguments.delta":
                    cid = getattr(event, "call_id", None)
                    if cid and cid in func_calls:
                        func_calls[cid]["arguments"] += getattr(event, "delta", "")

            thinking = "".join(thinking_chunks)
            text     = "".join(text_chunks)
            fc_list  = list(func_calls.values())

            if not fc_list:
                return thinking, text

            # 執行工具，下一輪繼續
            for fc in fc_list:
                try:
                    raw  = fc["arguments"].strip()
                    args = json.loads(raw) if raw else {}
                    result = await self.mcp.call(fc["name"], args)
                except Exception as e:
                    result = f"[ERROR] {e}"

                input_items.append({
                    "type":      "function_call",
                    "call_id":   fc["call_id"],
                    "name":      fc["name"],
                    "arguments": fc["arguments"],
                })
                input_items.append({
                    "type":    "function_call_output",
                    "call_id": fc["call_id"],
                    "output":  result,
                })

        return "", "（已達工具呼叫上限）"

    # ── Helpers ───────────────────────────────────

    async def _build_content(self, text: str, attachments: list[str]) -> list | str:
        if not attachments:
            return text
        parts: list = [{"type": "input_text", "text": text}]
        for path in attachments:
            parts.append(await self.files.upload(path))
        return parts
