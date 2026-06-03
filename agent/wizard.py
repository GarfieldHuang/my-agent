"""互動式設定精靈 — python main.py setup"""
import getpass
from pathlib import Path

import httpx
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.text import Text

from .auth import (
    delete_api_key,
    get_model,
    load_api_key,
    load_config,
    save_api_key,
    save_config,
)

console = Console()

MODELS = [
    ("gpt-4o", "最強，適合複雜任務"),
    ("gpt-4o-mini", "快速省錢，適合日常對話"),
    ("gpt-4-turbo", "舊旗艦，支援長文"),
    ("o1-mini", "推理型，擅長數學/程式"),
]


def run_setup() -> None:
    console.print()
    console.print(Panel(
        Text("My Agent 設定精靈", justify="center", style="bold cyan"),
        subtitle="按 Ctrl+C 隨時離開",
        border_style="cyan",
    ))
    console.print()

    try:
        _step_api_key()
        _step_model()
        _step_mcp()
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消設定。[/yellow]")
        return

    console.print()
    console.print(Rule(style="green"))
    console.print("[bold green]✓ 設定完成！[/bold green]  執行 [cyan]python main.py[/cyan] 開始使用。")
    console.print()


# ── Step 1：API Key ───────────────────────────────

def _step_api_key() -> None:
    console.print(Rule("① OpenAI API Key"))
    console.print()

    existing = load_api_key()
    if existing:
        masked = existing[:8] + "..." + existing[-4:]
        console.print(f"[dim]目前已儲存的 Key：{masked}[/dim]")
        if not Confirm.ask("要換一個新的 Key 嗎？", default=False):
            return

    console.print(
        "取得 API Key：[link=https://platform.openai.com/api-keys]"
        "https://platform.openai.com/api-keys[/link]"
    )
    console.print()

    while True:
        api_key = getpass.getpass("請貼上 API Key（輸入時不顯示）：").strip()
        if not api_key.startswith("sk-"):
            console.print("[red]格式不對，OpenAI API Key 應以 sk- 開頭。[/red]")
            continue

        console.print("[dim]驗證中…[/dim]", end="")
        error = _validate_key(api_key)
        if error:
            console.print(f"\r[red]驗證失敗：{error}[/red]          ")
            if not Confirm.ask("重新輸入？", default=True):
                break
            continue

        save_api_key(api_key)
        console.print(f"\r[green]✓ 驗證成功，已存入 macOS Keychain。[/green]          ")
        break

    console.print()


def _validate_key(api_key: str) -> str | None:
    """回傳錯誤訊息；None 代表成功。"""
    try:
        resp = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return None
        data = resp.json()
        return data.get("error", {}).get("message", f"HTTP {resp.status_code}")
    except httpx.TimeoutException:
        return "連線逾時，請檢查網路"
    except Exception as e:
        return str(e)


# ── Step 2：模型 ──────────────────────────────────

def _step_model() -> None:
    console.print(Rule("② 預設模型"))
    console.print()

    current = get_model()
    console.print(f"[dim]目前：{current}[/dim]\n")

    for i, (name, desc) in enumerate(MODELS, 1):
        tag = " [green]← 目前[/green]" if name == current else ""
        console.print(f"  [cyan]{i}[/cyan]. [bold]{name}[/bold]  {desc}{tag}")
    console.print(f"  [cyan]{len(MODELS)+1}[/cyan]. 自訂")
    console.print()

    choice = Prompt.ask("選擇", choices=[str(i) for i in range(1, len(MODELS)+2)], default="1")
    idx = int(choice) - 1

    if idx < len(MODELS):
        model = MODELS[idx][0]
    else:
        model = Prompt.ask("輸入模型名稱").strip()

    cfg = load_config()
    cfg["model"] = model
    save_config(cfg)
    console.print(f"[green]✓ 已設定為 {model}[/green]\n")


# ── Step 3：MCP servers ───────────────────────────

def _step_mcp() -> None:
    console.print(Rule("③ MCP 工具（可選）"))
    console.print()
    console.print("[dim]MCP 讓 agent 可以呼叫外部工具，例如讀寫檔案、查網路等。[/dim]\n")

    mcp_path = Path("mcp_config.yaml")
    cfg = yaml.safe_load(mcp_path.read_text()) if mcp_path.exists() else {}
    servers: dict = cfg.get("servers") or {}

    active = [k for k, v in servers.items() if v is not None]
    if active:
        console.print(f"[dim]目前已設定：{', '.join(active)}[/dim]\n")

    if not Confirm.ask("要新增 MCP server 嗎？", default=False):
        console.print("[dim]跳過。[/dim]\n")
        return

    while True:
        name = Prompt.ask("Server 名稱（例如 filesystem）").strip()
        transport = Prompt.ask("傳輸方式", choices=["stdio", "sse"], default="stdio")

        if transport == "stdio":
            command = Prompt.ask("執行指令（例如 npx）").strip()
            args_raw = Prompt.ask("參數（空白分隔，可留空）", default="").strip()
            args = args_raw.split() if args_raw else []
            servers[name] = {"transport": "stdio", "command": command, "args": args}
        else:
            url = Prompt.ask("SSE URL（例如 http://localhost:3001/sse）").strip()
            servers[name] = {"transport": "sse", "url": url}

        console.print(f"[green]✓ 已新增 {name}[/green]")

        if not Confirm.ask("繼續新增？", default=False):
            break

    cfg["servers"] = servers
    mcp_path.write_text(yaml.dump(cfg, allow_unicode=True, default_flow_style=False))
    console.print(f"[green]✓ mcp_config.yaml 已更新[/green]\n")
