"""CLI 執行工具：讓模型能在本機執行指令（附使用者確認機制）。

安全設計：
- 預設每次執行前透過 confirm callback 詢問使用者（GUI 跳確認視窗）
- 逾時強制終止（預設 60 秒）
- 輸出截斷，避免灌爆 context
"""
import logging
import subprocess
import sys

log = logging.getLogger("my-agent")

MAX_OUTPUT = 8000

SHELL_TOOLS = [
    {
        "type": "function",
        "name": "run_command",
        "description": (
            "在使用者的電腦上執行 CLI 指令並回傳輸出。"
            "適合查看檔案、執行腳本、git 操作、安裝套件等。"
            "注意：Windows 環境用 cmd.exe 執行（此電腦的群組原則封鎖 "
            "PowerShell，請勿使用 PowerShell 語法）。"
            "危險或不可逆的操作（刪除、覆蓋、對外發送）請先向使用者說明再執行。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要執行的完整指令",
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目錄（省略時用程式目前目錄）",
                },
                "timeout_sec": {
                    "type": "integer",
                    "description": "逾時秒數（預設 60，最多 600）",
                },
            },
            "required": ["command"],
        },
    },
]


def is_shell_tool(name: str) -> bool:
    return name == "run_command"


def call_shell_tool(name: str, args: dict, confirm=None) -> str:
    """執行指令並回傳結果字串。confirm(command) 回傳 False 時拒絕執行。

    這是阻塞呼叫，core 端請用 asyncio.to_thread 包起來跑。
    """
    command = str(args.get("command", "")).strip()
    if not command:
        return "[ERROR] 沒有提供指令。"

    if confirm is not None:
        try:
            allowed = confirm(command)
        except Exception:
            log.exception("CLI confirm callback 失敗")
            allowed = False
        if not allowed:
            return "[使用者拒絕執行此指令，請改用其他方式或詢問使用者。]"

    try:
        timeout = min(int(args.get("timeout_sec") or 60), 600)
    except (TypeError, ValueError):
        timeout = 60

    # GUI 程式底下跑 console 指令不要閃出黑視窗
    creationflags = (
        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )

    log.info("CLI run: %s", command)

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=args.get("cwd") or None,
            timeout=timeout,
            capture_output=True,
            text=True,
            errors="replace",
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return f"[ERROR] 指令逾時（{timeout} 秒），已強制終止。"
    except Exception as e:
        return f"[ERROR] {e}"

    output = (proc.stdout or "")
    if proc.stderr:
        output += ("\n[stderr]\n" + proc.stderr)
    output = output.strip() or "(沒有輸出)"

    if len(output) > MAX_OUTPUT:
        output = output[:MAX_OUTPUT] + "\n…（輸出過長，已截斷）"

    return f"exit code: {proc.returncode}\n{output}"
