"""上傳本地檔案到 OpenAI Files API，回傳可嵌入 messages 的引用。"""
import mimetypes
from pathlib import Path

from openai import AsyncOpenAI

# 支援 vision 的圖片類型
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# OpenAI Files API 支援的文件類型
DOCUMENT_TYPES = {
    ".pdf", ".txt", ".md", ".csv", ".json",
    ".py", ".js", ".ts", ".html", ".css",
    ".c", ".cpp", ".h", ".java", ".rb", ".go", ".rs",
}


class FileUploader:
    def __init__(self, client: AsyncOpenAI):
        self.client = client
        self._cache: dict[str, str] = {}  # path → file_id

    async def upload(self, path: str) -> dict:
        """
        上傳檔案，回傳可放入 messages content 的字典。

        圖片 → {"type": "image_url", "image_url": {"url": "..."}}
        文件 → {"type": "text", "text": "<file content>"}  (小檔)
             或 file_id 引用（大檔）
        """
        p = Path(path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"找不到檔案：{p}")

        ext = p.suffix.lower()

        if ext in IMAGE_TYPES:
            return await self._upload_image(p)
        elif ext in DOCUMENT_TYPES:
            return await self._upload_document(p)
        else:
            # 嘗試當文字讀
            try:
                text = p.read_text(errors="replace")
                return {"type": "text", "text": f"[{p.name}]\n{text}"}
            except Exception:
                raise ValueError(f"不支援的檔案類型：{ext}")

    async def _upload_image(self, p: Path) -> dict:
        """圖片轉 base64 data URL，直接嵌入 message（不用 Files API）。"""
        import base64
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode()
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        }

    async def _upload_document(self, p: Path) -> dict:
        """小於 512KB 直接貼文字；大於則上傳到 Files API。"""
        size = p.stat().st_size

        if size < 512 * 1024:
            text = p.read_text(errors="replace")
            return {"type": "text", "text": f"[{p.name}]\n```\n{text}\n```"}

        # 大檔：上傳到 Files API
        if str(p) in self._cache:
            file_id = self._cache[str(p)]
        else:
            with open(p, "rb") as f:
                resp = await self.client.files.create(file=f, purpose="assistants")
            file_id = resp.id
            self._cache[str(p)] = file_id
            print(f"[Files] 已上傳 {p.name} → {file_id}")

        return {
            "type": "text",
            "text": f"[已上傳檔案 {p.name}，file_id: {file_id}]",
        }

    async def delete_cached(self) -> None:
        """刪除本次上傳的所有 Files API 檔案。"""
        for file_id in self._cache.values():
            try:
                await self.client.files.delete(file_id)
            except Exception:
                pass
        self._cache.clear()
