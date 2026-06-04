#!/usr/bin/env python3
"""My Agent — GUI（預設）或 CLI（--cli）模式"""
import sys

# Windows asyncio fix（uvicorn OAuth callback server 需要 SelectorEventLoop）
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncio
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


# ── GUI 模式 ──────────────────────────────────────

def launch_gui():
    from gui.app import App
    app = App()
    app.mainloop()


# ── CLI 模式 ──────────────────────────────────────

async def _run_cli(system_prompt: str):
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    from agent.auth import get_model, get_openai_client
    from agent.core import Agent
    from agent.mcp_manager import MCPManager

    console = Console()
    try:
        client = get_openai_client()
    except EnvironmentError as e:
        console.print(f"[red]{e}[/red]")
        return

    mcp = MCPManager(config_path="mcp_config.yaml")
    console.print("[dim]啟動 MCP servers...[/dim]")
    await mcp.start()

    tools = mcp.list_tools()
    if tools:
        console.print(f"[green]✓ 已載入 {len(tools)} 個工具：{', '.join(tools)}[/green]")

    model = get_model()
    agent = Agent(client=client, mcp=mcp, model=model, system_prompt=system_prompt)

    console.print(Panel(
        f"[bold]My Agent[/bold]（{model}）\n"
        "/file <路徑>  附加檔案    /clear  清除對話    /logout  登出    /quit  離開",
        border_style="blue",
    ))

    pending_files: list[str] = []
    try:
        while True:
            try:
                raw = Prompt.ask("[bold cyan]You[/bold cyan]")
            except (EOFError, KeyboardInterrupt):
                break

            if not raw.strip():
                continue
            match raw.strip():
                case "/quit":  break
                case "/clear": agent.clear_history(); console.print("[dim]✓ 清除[/dim]"); continue
                case "/logout":
                    from agent.auth import logout
                    logout(); break

            if raw.startswith("/file "):
                p = raw[6:].strip()
                if Path(p).exists():
                    pending_files.append(p)
                    console.print(f"[dim]✓ 已附加：{p}[/dim]")
                else:
                    console.print(f"[red]找不到：{p}[/red]")
                continue

            atts, pending_files = pending_files, []
            with console.status("[dim]思考中...[/dim]", spinner="dots"):
                try:
                    thinking, reply = await agent.chat(raw, attachments=atts)
                except Exception as e:
                    console.print(f"[red]{e}[/red]"); continue
            if thinking:
                console.print(f"[dim italic]💭 {thinking[:200]}{'…' if len(thinking)>200 else ''}[/dim italic]")

            from rich.console import Console
            console.print()
            console.print(Panel(Markdown(reply), title="[bold green]Agent[/bold green]", border_style="green"))
            console.print()
    finally:
        await mcp.stop()
        await agent.files.delete_cached()


# ── Entry point ───────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--cli",    is_flag=True, help="終端機模式（不開 GUI）")
@click.option("--system", default="You are a helpful assistant.", help="System prompt（CLI 模式用）")
def main(ctx, cli, system):
    """My Agent — 用 OpenAI 帳號登入，不需要 API Key"""
    if ctx.invoked_subcommand is None:
        if cli:
            asyncio.run(_run_cli(system))
        else:
            launch_gui()


@main.command()
def setup():
    """互動式設定精靈（CLI）"""
    from agent.wizard import run_setup
    run_setup()


@main.command()
def logout():
    """登出（清除本機 token）"""
    from agent.auth import logout as _lo
    _lo()


if __name__ == "__main__":
    main()
