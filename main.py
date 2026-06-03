#!/usr/bin/env python3
"""My Agent CLI — OpenAI + MCP + 檔案上傳"""
import asyncio
import os
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

load_dotenv()

console = Console()


# ── Chat ─────────────────────────────────────────

async def _run_agent(system_prompt: str):
    from agent.auth import get_model, get_openai_client
    from agent.core import Agent
    from agent.mcp_manager import MCPManager

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
    else:
        console.print("[yellow]△ 沒有載入任何 MCP tool（執行 python main.py setup 可新增）[/yellow]")

    agent = Agent(
        client=client,
        mcp=mcp,
        model=get_model(),
        system_prompt=system_prompt,
    )

    console.print(Panel(
        f"[bold]My Agent[/bold]（{get_model()}）已就緒\n"
        "輸入 [cyan]/file <路徑>[/cyan] 附加檔案，[cyan]/clear[/cyan] 清除對話，[cyan]/quit[/cyan] 離開",
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

            if raw.strip() == "/quit":
                break
            if raw.strip() == "/clear":
                agent.clear_history()
                console.print("[dim]✓ 對話已清除[/dim]")
                continue
            if raw.startswith("/file "):
                fpath = raw[6:].strip()
                if Path(fpath).exists():
                    pending_files.append(fpath)
                    console.print(f"[dim]✓ 已附加：{fpath}[/dim]")
                else:
                    console.print(f"[red]找不到檔案：{fpath}[/red]")
                continue

            attachments, pending_files = pending_files, []
            with console.status("[dim]思考中...[/dim]", spinner="dots"):
                try:
                    reply = await agent.chat(raw, attachments=attachments)
                except Exception as e:
                    console.print(f"[red]錯誤：{e}[/red]")
                    continue

            console.print()
            console.print(Panel(Markdown(reply), title="[bold green]Agent[/bold green]", border_style="green"))
            console.print()
    finally:
        await mcp.stop()
        await agent.files.delete_cached()


# ── CLI commands ──────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--system", default="You are a helpful assistant.", help="System prompt")
def cli(ctx, system):
    """My Agent — 你的私人 AI agent"""
    if ctx.invoked_subcommand is None:
        asyncio.run(_run_agent(system))


@cli.command()
def setup():
    """互動式設定精靈（API Key、模型、MCP 工具）"""
    from agent.wizard import run_setup
    run_setup()


@cli.command()
def reset():
    """清除所有設定（API Key、config）"""
    from agent.auth import delete_api_key, CONFIG_PATH
    from rich.prompt import Confirm

    if Confirm.ask("[red]確定要清除所有設定？[/red]", default=False):
        delete_api_key()
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        console.print("[green]✓ 已清除。[/green]")


if __name__ == "__main__":
    cli()
