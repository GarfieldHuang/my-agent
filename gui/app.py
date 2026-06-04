"""主視窗：導覽列 + 背景 asyncio loop + 共用 agent 狀態。"""
import asyncio
import queue
import threading

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("My Agent")
        self.geometry("980x660")
        self.minsize(720, 480)

        # ── 背景 asyncio loop（給 agent / MCP 用）──
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True).start()
        self._queue: queue.Queue = queue.Queue()

        # ── 共用資源 ──
        self.mcp   = None
        self.agent = None
        self.is_ready = False

        self._build()
        self._init_agent()
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        sidebar = ctk.CTkFrame(self, width=180, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(10, weight=1)

        ctk.CTkLabel(
            sidebar, text="🤖 My Agent",
            font=ctk.CTkFont(size=17, weight="bold")
        ).grid(row=0, column=0, padx=20, pady=(24, 20))

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        for i, (label, key) in enumerate([
            ("💬  Chat",     "chat"),
            ("🔌  MCP 工具", "mcp"),
            ("⚙   設定",     "settings"),
            ("👤  帳號",     "account"),
        ], 1):
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                height=38, corner_radius=8,
                command=lambda k=key: self.show(k),
            )
            btn.grid(row=i, column=0, padx=10, pady=3, sticky="ew")
            self._nav_btns[key] = btn

        # Content
        content = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray96", "gray11"))
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        from gui.chat     import ChatView
        from gui.mcp      import MCPView
        from gui.settings import SettingsView
        from gui.account  import AccountView

        self._views: dict[str, ctk.CTkFrame] = {
            "chat":     ChatView(content, self),
            "mcp":      MCPView(content, self),
            "settings": SettingsView(content, self),
            "account":  AccountView(content, self),
        }
        for v in self._views.values():
            v.grid(row=0, column=0, sticky="nsew")

        self.show("chat")

    def show(self, key: str):
        for k, btn in self._nav_btns.items():
            btn.configure(fg_color=("gray75", "gray25") if k == key else "transparent")
        self._views[key].tkraise()
        if hasattr(self._views[key], "on_show"):
            self._views[key].on_show()

    # ── Agent init ────────────────────────────────

    def _init_agent(self):
        from agent.auth import has_valid_token, get_openai_client, get_model
        if not has_valid_token():
            self._queue.put(("need_login", None))
            return

        async def _init():
            try:
                from agent.core import Agent
                from agent.mcp_manager import MCPManager
                client = get_openai_client()
                mcp    = MCPManager("mcp_config.yaml")
                await mcp.start()
                agent  = Agent(client=client, mcp=mcp, model=get_model())
                self._queue.put(("ready", (mcp, agent)))
            except Exception as e:
                self._queue.put(("error", str(e)))

        asyncio.run_coroutine_threadsafe(_init(), self._loop)

    def reinit(self):
        """登入後重新初始化 agent。"""
        self._init_agent()

    # ── Queue 輪詢 ────────────────────────────────

    def _poll(self):
        try:
            while True:
                kind, data = self._queue.get_nowait()
                if kind == "ready":
                    self.mcp, self.agent = data
                    self.is_ready = True
                    for v in self._views.values():
                        if hasattr(v, "on_agent_ready"):
                            v.on_agent_ready()
                elif kind in ("error", "need_login"):
                    self.show("account")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ── Async helper ──────────────────────────────

    def run_async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ── Cleanup ───────────────────────────────────

    def _on_close(self):
        if self.mcp:
            asyncio.run_coroutine_threadsafe(self.mcp.stop(), self._loop)
        self.destroy()
