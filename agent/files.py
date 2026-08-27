"""附件轉換：全部在本地擷取文字/編碼，嵌入 messages（不經任何遠端上傳 API）。

這裡的模型 client 指向 ChatGPT 的 codex 後端（chatgpt.com/backend-api/codex），
不是標準 OpenAI Platform API，並不保證支援 Files API；過去曾經呼叫
client.files.create() 上傳大檔，若後端不支援該端點，這個沒有 timeout
的呼叫可能整個卡住、且 Stop 鍵按了也沒用（cancel_requested 不會在這裡被檢查）。
改成本地處理後就不再有任何會卡住的網路呼叫。
"""
import asyncio
import logging
import mimetypes
from pathlib import Path

from openai import AsyncOpenAI

log = logging.getLogger("my-agent")

# 支援 vision 的圖片類型
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# 走純文字讀取的文件類型（PDF 另外用專門的解析器，見下方）
TEXT_DOCUMENT_TYPES = {
    ".txt", ".md", ".csv", ".json",
    ".py", ".js", ".ts", ".html", ".css",
    ".c", ".cpp", ".h", ".java", ".rb", ".go", ".rs",
}

# 嵌入內容的字數上限（含說明文字），避免單一附件灌爆 context
MAX_DOC_CHARS = 60_000


class FileUploader:
    def __init__(self, client: AsyncOpenAI):
        self.client = client

    async def upload(self, path: str) -> dict:
        """
        轉換附件，回傳可放入 messages content 的字典。
        單一附件處理失敗不拋例外——回傳說明性文字，讓對話能繼續進行。
        """
        try:
            return await self._convert(path)
        except Exception as e:
            log.exception("附件處理失敗：%s", path)
            name = Path(path).name
            return {
                "type": "input_text",
                "text": f"[附件「{name}」處理失敗，已略過：{e}]",
            }

    async def _convert(self, path: str) -> dict:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"找不到檔案：{p}")

        ext = p.suffix.lower()

        if ext in IMAGE_TYPES:
            return await self._read_image(p)
        elif ext == ".pdf":
            # 逐頁解析可能較慢，丟到 thread 避免卡住共用的 asyncio event loop
            return await asyncio.to_thread(self._read_pdf, p)
        else:
            # TEXT_DOCUMENT_TYPES 或未知副檔名，都嘗試當文字讀（容錯路徑）
            return await asyncio.to_thread(self._read_text_file, p)

    async def _read_image(self, p: Path) -> dict:
        """圖片轉 base64 data URL，直接嵌入 message。"""
        import base64
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        return {
            "type": "input_image",
            "image_url": f"data:{mime};base64,{b64}",
        }

    @staticmethod
    def _truncate(text: str) -> tuple[str, bool]:
        if len(text) <= MAX_DOC_CHARS:
            return text, False
        return text[:MAX_DOC_CHARS], True

    def _read_pdf(self, p: Path) -> dict:
        """用 pypdf 逐頁擷取文字（PDF 是二進位格式，不能當純文字讀）。"""
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        page_count = len(reader.pages)

        pages_text = []
        for page in reader.pages:
            pages_text.append(page.extract_text() or "")
        text = "\n\n".join(pages_text).strip()

        if not text:
            text = "（此 PDF 擷取不到文字，可能是掃描影像檔，需要 OCR。）"

        text, truncated = self._truncate(text)
        note = f"[{p.name}]（PDF，共 {page_count} 頁"
        note += "，內容過長已截斷）" if truncated else "）"
        return {"type": "input_text", "text": f"{note}\n{text}"}

    def _read_text_file(self, p: Path) -> dict:
        text = p.read_text(errors="replace")
        text, truncated = self._truncate(text)
        suffix_note = "\n…（內容過長已截斷）" if truncated else ""
        return {"type": "input_text", "text": f"[{p.name}]\n```\n{text}{suffix_note}\n```"}
