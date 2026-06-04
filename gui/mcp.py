"""MCP 工具頁面：顯示、新增、刪除 MCP server 設定。"""
from pathlib import Path

import yaml
import customtkinter as ctk

MCP_CONFIG = Path("mcp_config.yaml")


def _load_servers() -> dict:
    if MCP_CONFIG.exists():
        cfg = yaml.safe_load(MCP_CONFIG.read_text(encoding="utf-8")) or {}
        return {k: v for k, v in (cfg.get("servers") or {}).items() if v}
    return {}


def _save_servers(servers: dict):
    cfg = yaml.safe_load(MCP_CONFIG.read_text(encoding="utf-8")) if MCP_CONFIG.exists() else {}
    cfg = cfg or {}
    cfg["servers"] = servers
    MCP_CONFIG.write_text(
        yaml.dump(cfg, allow_unicode=True, default_flow_style=False),
        encoding="utf-8"
    )


class MCPView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build()

    def _build(self):
        # 標題 + 新增按鈕
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, padx=30, pady=(28, 0), sticky="ew")
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top, text="MCP 工具",
                     font=ctk.CTkFont(size=20, weight="bold")
                     ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(top, text="＋ 新增 Server",
                      command=self._open_add_dialog, width=140
                      ).grid(row=0, column=1)

        ctk.CTkLabel(
            self,
            text="重新啟動 agent 後 MCP 設定才會生效。",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).grid(row=1, column=0, padx=30, pady=(4, 0), sticky="w")

        # 列表
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.list_frame.grid(row=2, column=0, padx=30, pady=12, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._refresh()

    # ── 列表 ─────────────────────────────────────

    def _refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        servers = _load_servers()
        if not servers:
            ctk.CTkLabel(self.list_frame, text="尚未設定任何 MCP server。",
                         text_color="gray").pack(pady=20)
            return

        for name, spec in servers.items():
            self._server_row(name, spec)

    def _server_row(self, name: str, spec: dict):
        row = ctk.CTkFrame(self.list_frame)
        row.pack(fill="x", pady=4)
        row.grid_columnconfigure(1, weight=1)

        transport = spec.get("transport", "stdio")
        if transport == "stdio":
            cmd  = spec.get("command", "")
            args = " ".join(spec.get("args", []))
            detail = f"{cmd} {args}".strip()
        else:
            detail = spec.get("url", "")

        ctk.CTkLabel(row, text=f"  {name}",
                     font=ctk.CTkFont(weight="bold"), anchor="w"
                     ).grid(row=0, column=0, padx=10, pady=(10, 2), sticky="w")

        ctk.CTkLabel(row, text=f"[{transport}]  {detail}",
                     text_color="gray", font=ctk.CTkFont(size=12), anchor="w"
                     ).grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        ctk.CTkButton(
            row, text="刪除", width=70,
            fg_color=("gray60", "gray35"), hover_color=("gray50", "gray25"),
            command=lambda n=name: self._remove(n)
        ).grid(row=0, column=2, padx=10, pady=8)

    def _remove(self, name: str):
        servers = _load_servers()
        servers.pop(name, None)
        _save_servers(servers)
        self._refresh()

    # ── 新增對話框 ────────────────────────────────

    def _open_add_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("新增 MCP Server")
        dlg.geometry("420x320")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.grid_columnconfigure(1, weight=1)

        fields = {}

        def row(r, label, widget_cls, **kw):
            ctk.CTkLabel(dlg, text=label).grid(row=r, column=0, padx=16, pady=8, sticky="w")
            w = widget_cls(dlg, **kw)
            w.grid(row=r, column=1, padx=16, pady=8, sticky="ew")
            return w

        fields["name"]      = row(0, "名稱",    ctk.CTkEntry,      placeholder_text="例：filesystem")
        transport_var       = ctk.StringVar(value="stdio")
        fields["transport"] = row(1, "傳輸方式", ctk.CTkOptionMenu,
                                  values=["stdio", "sse"], variable=transport_var,
                                  command=lambda v: _toggle(v))
        fields["command"]   = row(2, "指令",     ctk.CTkEntry,      placeholder_text="例：npx")
        fields["args"]      = row(3, "參數",     ctk.CTkEntry,      placeholder_text="例：-y @mcp/server-fs /tmp")
        fields["url"]       = row(4, "SSE URL",  ctk.CTkEntry,      placeholder_text="http://localhost:3001/sse")
        fields["url"].grid_remove()

        def _toggle(v):
            if v == "sse":
                fields["command"].grid_remove()
                fields["args"].grid_remove()
                fields["url"].grid()
            else:
                fields["url"].grid_remove()
                fields["command"].grid()
                fields["args"].grid()

        def _save():
            name = fields["name"].get().strip()
            if not name:
                return
            t = transport_var.get()
            if t == "stdio":
                spec = {
                    "transport": "stdio",
                    "command":   fields["command"].get().strip(),
                    "args":      fields["args"].get().strip().split() or [],
                }
            else:
                spec = {"transport": "sse", "url": fields["url"].get().strip()}

            servers = _load_servers()
            servers[name] = spec
            _save_servers(servers)
            dlg.destroy()
            self._refresh()

        ctk.CTkButton(dlg, text="新增", command=_save
                      ).grid(row=5, column=0, columnspan=2, padx=16, pady=16, sticky="ew")

    def on_show(self):
        self._refresh()
