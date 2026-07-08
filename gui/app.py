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
        self.current_session_id: str | None = None

        self._build()
        self._init_agent()
        self._poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(7, weight=1)   # 對話紀錄區吃掉剩餘空間

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

        # ── 對話紀錄（Claude 風格：新對話 + 歷史列表）──
        ctk.CTkButton(
            sidebar, text="＋  新對話", anchor="w",
            fg_color="transparent", text_color=("gray10", "gray90"),
            hover_color=("gray70", "gray30"), height=34, corner_radius=8,
            command=self.new_chat,
        ).grid(row=5, column=0, padx=10, pady=(16, 2), sticky="ew")

        ctk.CTkLabel(
            sidebar, text="對話紀錄", anchor="w",
            font=ctk.CTkFont(size=11), text_color="gray",
        ).grid(row=6, column=0, padx=20, pady=(6, 0), sticky="ew")

        self._session_frame = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self._session_frame.grid(row=7, column=0, padx=4, pady=(2, 8), sticky="nsew")
        self._session_frame.grid_columnconfigure(0, weight=1)

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
        self.refresh_sessions()

    def show(self, key: str):
        for k, btn in self._nav_btns.items():
            btn.configure(fg_color=("gray75", "gray25") if k == key else "transparent")
        self._views[key].tkraise()
        if hasattr(self._views[key], "on_show"):
            self._views[key].on_show()

    # ── 對話 session 管理 ─────────────────────────

    def new_chat(self):
        if self.agent:
            self.agent.clear_history()
        self.current_session_id = None
        self._views["chat"].reset()
        self.refresh_sessions()
        self.show("chat")

    def load_chat(self, session_id: str):
        if not self.is_ready:
            return
        from agent import sessions
        data = sessions.load_session(session_id)
        if not data:
            self.refresh_sessions()
            return
        self.agent.clear_history()
        self.agent.history.extend(data.get("history", []))
        self.current_session_id = session_id
        self._views["chat"].render_history(self.agent.history)
        self.refresh_sessions()
        self.show("chat")

    def save_current_chat(self):
        """每輪對話後自動存檔（ChatView 呼叫）。"""
        from agent import sessions
        if not self.agent or not self.agent.history:
            return
        if not self.current_session_id:
            self.current_session_id = sessions.new_session_id()
        sessions.save_session(self.current_session_id, self.agent.history)
        self.refresh_sessions()

    def delete_chat(self, session_id: str):
        from agent import sessions
        sessions.delete_session(session_id)
        if session_id == self.current_session_id:
            self.new_chat()
        else:
            self.refresh_sessions()

    def refresh_sessions(self):
        from agent import sessions
        for w in self._session_frame.winfo_children():
            w.destroy()
        for meta in sessions.list_sessions():
            sid   = meta["id"]
            title = meta["title"]
            row = ctk.CTkFrame(self._session_frame, fg_color="transparent")
            row.grid(sticky="ew", pady=1)
            row.grid_columnconfigure(0, weight=1)

            active = sid == self.current_session_id
            ctk.CTkButton(
                row, text=title[:18] + ("…" if len(title) > 18 else ""),
                anchor="w", height=30, corner_radius=6,
                font=ctk.CTkFont(size=12),
                fg_color=("gray75", "gray25") if active else "transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray70", "gray30"),
                command=lambda s=sid: self.load_chat(s),
            ).grid(row=0, column=0, sticky="ew")
            ctk.CTkButton(
                row, text="✕", width=26, height=30, corner_radius=6,
                fg_color="transparent", text_color="gray",
                hover_color=("gray70", "gray30"),
                command=lambda s=sid: self.delete_chat(s),
            ).grid(row=0, column=1, padx=(2, 0))

    # ── Agent init ────────────────────────────────

    def _init_agent(self):
        from agent.auth import has_valid_token, get_openai_client, get_model, load_config
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
                cfg    = load_config()
                agent  = Agent(
                    client=client, mcp=mcp, model=get_model(),
                    reasoning_effort=cfg.get("reasoning_effort", "medium"),
                )
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
