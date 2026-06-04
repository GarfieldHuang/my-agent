"""MCP 工具頁面：顯示、新增、刪除、編輯 inject 參數。"""
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


def _inject_to_str(inject: dict) -> str:
    """inject dict → 'key=value, key2=value2' 字串。"""
    return ", ".join(f"{k}={v}" for k, v in inject.items())


def _str_to_inject(s: str) -> dict:
    """'key=value, key2=value2' → dict。"""
    result = {}
    for pair in s.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            k, v = k.strip(), v.strip()
            if k:
                result[k] = v
    return result


class MCPView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build()

    def _build(self):
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

        self.list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.list_frame.grid(row=2, column=0, padx=30, pady=12, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

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
        card = ctk.CTkFrame(self.list_frame)
        card.pack(fill="x", pady=4)
        card.grid_columnconfigure(0, weight=1)

        transport = spec.get("transport", "stdio")
        detail = (f"{spec.get('command','')} {' '.join(spec.get('args',[]))}"
                  if transport == "stdio" else spec.get("url", ""))
        inject = spec.get("inject") or {}

        # 名稱 + 刪除按鈕
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(10, 2))
        top_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(top_row, text=name,
                     font=ctk.CTkFont(weight="bold"), anchor="w"
                     ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            top_row, text="刪除", width=60,
            fg_color=("gray60", "gray35"), hover_color=("gray50", "gray25"),
            command=lambda n=name: self._remove(n)
        ).grid(row=0, column=1, padx=(4, 0))

        # 連線資訊
        ctk.CTkLabel(card, text=f"[{transport}]  {detail}",
                     text_color="gray", font=ctk.CTkFont(size=12), anchor="w"
                     ).pack(fill="x", padx=12, pady=(0, 4))

        # ── Inject 區段 ──────────────────────────
        inj_frame = ctk.CTkFrame(card, fg_color=("gray88", "gray20"), corner_radius=8)
        inj_frame.pack(fill="x", padx=10, pady=(0, 10))
        inj_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(inj_frame, text="inject",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray", anchor="w"
                     ).grid(row=0, column=0, padx=10, pady=6, sticky="w")

        inject_var = ctk.StringVar(value=_inject_to_str(inject))
        inject_entry = ctk.CTkEntry(
            inj_frame, textvariable=inject_var,
            placeholder_text="key=value, key2=value2",
            font=ctk.CTkFont(size=11),
        )
        inject_entry.grid(row=0, column=1, padx=(0, 6), pady=6, sticky="ew")

        def _save_inject(n=name, var=inject_var):
            servers = _load_servers()
            if n in servers:
                new_inject = _str_to_inject(var.get())
                if new_inject:
                    servers[n]["inject"] = new_inject
                elif "inject" in servers[n]:
                    del servers[n]["inject"]
                _save_servers(servers)

        ctk.CTkButton(
            inj_frame, text="儲存", width=50,
            font=ctk.CTkFont(size=11),
            command=_save_inject
        ).grid(row=0, column=2, padx=(0, 8), pady=6)

    def _remove(self, name: str):
        servers = _load_servers()
        servers.pop(name, None)
        _save_servers(servers)
        self._refresh()

    # ── 新增對話框 ────────────────────────────────

    def _open_add_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("新增 MCP Server")
        dlg.geometry("460x360")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.grid_columnconfigure(1, weight=1)

        fields = {}

        def row(r, label, widget_cls, **kw):
            ctk.CTkLabel(dlg, text=label).grid(row=r, column=0, padx=16, pady=7, sticky="w")
            w = widget_cls(dlg, **kw)
            w.grid(row=r, column=1, padx=16, pady=7, sticky="ew")
            return w

        fields["name"]      = row(0, "名稱",     ctk.CTkEntry, placeholder_text="例：mssql")
        transport_var       = ctk.StringVar(value="stdio")
        fields["transport"] = row(1, "傳輸方式",  ctk.CTkOptionMenu,
                                  values=["stdio", "sse"], variable=transport_var,
                                  command=lambda v: _toggle(v))
        fields["command"]   = row(2, "指令",      ctk.CTkEntry, placeholder_text="例：python")
        fields["args"]      = row(3, "參數",      ctk.CTkEntry, placeholder_text="例：server.py")
        fields["url"]       = row(4, "SSE URL",   ctk.CTkEntry, placeholder_text="http://localhost:3001/sse")
        fields["url"].grid_remove()
        fields["inject"]    = row(5, "inject",    ctk.CTkEntry,
                                  placeholder_text="api_key=xxx, token=yyy（可留空）")

        ctk.CTkLabel(dlg, text="inject 參數會自動帶入工具呼叫，模型不會看到",
                     text_color="gray", font=ctk.CTkFont(size=10)
                     ).grid(row=6, column=1, padx=16, sticky="w")

        def _toggle(v):
            if v == "sse":
                fields["command"].grid_remove(); fields["args"].grid_remove()
                fields["url"].grid()
            else:
                fields["url"].grid_remove()
                fields["command"].grid(); fields["args"].grid()

        def _save():
            name = fields["name"].get().strip()
            if not name:
                return
            t = transport_var.get()
            if t == "stdio":
                spec: dict = {
                    "transport": "stdio",
                    "command":   fields["command"].get().strip(),
                    "args":      fields["args"].get().strip().split() or [],
                }
            else:
                spec = {"transport": "sse", "url": fields["url"].get().strip()}

            inject = _str_to_inject(fields["inject"].get())
            if inject:
                spec["inject"] = inject

            servers = _load_servers()
            servers[name] = spec
            _save_servers(servers)
            dlg.destroy()
            self._refresh()

        ctk.CTkButton(dlg, text="新增", command=_save
                      ).grid(row=7, column=0, columnspan=2, padx=16, pady=16, sticky="ew")

    def on_show(self):
        self._refresh()
