"""帳號頁面：登入狀態、OAuth 登入/登出。"""
import logging
import threading
import customtkinter as ctk

from pathlib import Path
from PIL import Image

log = logging.getLogger("my-agent")


class AccountView(ctk.CTkFrame):
    
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        ctk.CTkLabel(
            self, text="帳號",
            font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, padx=30, pady=(28, 6), sticky="w")

        # 狀態卡片
        card = ctk.CTkFrame(self)
        card.grid(row=1, column=0, padx=30, pady=10, sticky="ew")

        self.status_icon  = ctk.CTkLabel(card, text="", font=ctk.CTkFont(size=32))
        self.status_icon.grid(row=0, column=0, padx=20, pady=(20, 4))

        self.status_label = ctk.CTkLabel(card, text="檢查中…", font=ctk.CTkFont(size=14))
        self.status_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # 按鈕列
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=30, pady=6, sticky="w")

        self.login_btn = ctk.CTkButton(
            btn_row, text="登入 OpenAI 帳號",
            command=self._login, width=190, height=40
        )
        self.login_btn.grid(row=0, column=0, padx=(0, 10))

        self.logout_btn = ctk.CTkButton(
            btn_row, text="登出", command=self._logout,
            fg_color=("gray60", "gray35"), hover_color=("gray50", "gray25"),
            width=90, height=40
        )
        self.logout_btn.grid(row=0, column=1)

        # 說明
        ctk.CTkLabel(
            self,
            text="需要 ChatGPT Plus 或 Pro 訂閱才能使用。\n"
                 "登入後 token 會安全存放在本機，重啟不需要再次登入。",
            text_color="gray", font=ctk.CTkFont(size=12),
            justify="left"
        ).grid(row=3, column=0, padx=30, pady=(10, 0), sticky="w")

        self._refresh()

    # ── 狀態顯示 ─────────────────────────────────

    def _refresh(self):
        
        assets_dir = Path(__file__).resolve().parent / "assets"
        
        self.logged_in_image = ctk.CTkImage(
            light_image=Image.open(assets_dir / "chatgpt_logo.png"),
            dark_image=Image.open(assets_dir / "chatgpt_logo.png"),
            size=(42, 42),
        )
        
        self.logged_out_image = ctk.CTkImage(
            light_image=Image.open(assets_dir / "log_out.png"),
            dark_image=Image.open(assets_dir / "log_out.png"),
            size=(64, 64),
        )
        
        from agent.auth import has_valid_token, get_user_info
        
        if has_valid_token():
            info = get_user_info()
            email = info.get("email", "")
            plan = info.get("plan", "")
        
            self.status_icon.configure(
                image=self.logged_in_image,
                text=""
            )
        
            self.status_label.configure(
                text=f"已登入\n{email}"
                + (f"\nChatGPT {plan.capitalize()}" if plan else ""),
                text_color=("gray10", "gray90")
            )
        
            self.login_btn.configure(text="重新登入")
        
        else:
            self.status_icon.configure(
                image=self.logged_out_image,
                text=""
            )
        
            self.status_label.configure(
                text="尚未登入",
                text_color="gray"
            )
        
            self.login_btn.configure(text="登入 OpenAI 帳號")

    def on_show(self):
        self._refresh()

    # ── 登入 ─────────────────────────────────────

    def _login(self):
        self.login_btn.configure(state="disabled", text="登入中…")
        self.status_icon.configure(text="⏳")
        # 這裡還沒真的開瀏覽器——實際結果由 on_auth_url 回報後才更新。
        # 先寫死「瀏覽器已開啟」的話，開不起來時使用者只會看到一句
        # 與事實不符的提示，也拿不到可以自己貼的網址。
        self.status_label.configure(
            text="正在開啟瀏覽器…",
            text_color="gray",
        )

        def _on_auth_url(url: str, opened: bool):
            self.app.after(0, lambda: self._show_auth_url(url, opened))

        def _do():
            try:
                from agent.auth import get_access_token
                get_access_token(on_auth_url=_on_auth_url)
                self.app.after(0, self._on_login_ok)
            except Exception as e:
                self.app.after(0, lambda: self.show_error(str(e)))

        threading.Thread(target=_do, daemon=True).start()

    def _show_auth_url(self, url: str, opened: bool):
        """瀏覽器開啟成功與否都告知，失敗時把網址交給使用者。"""
        if opened:
            self.status_label.configure(
                text="瀏覽器已開啟，請完成授權後回到此視窗…",
                text_color="gray",
            )
            return

        self.status_icon.configure(text="⚠")
        self.status_label.configure(
            text=(
                "無法自動開啟瀏覽器。\n"
                "已複製授權網址到剪貼簿，請貼到瀏覽器完成登入："
                f"\n{url}"
            ),
            text_color="orange",
        )
        try:
            self.clipboard_clear()
            self.clipboard_append(url)
        except Exception:
            log.exception("複製授權網址到剪貼簿失敗")

    def _on_login_ok(self):
        self._refresh()
        self.login_btn.configure(state="normal")
        self.app.reinit()

    def show_error(self, msg: str):
        self.login_btn.configure(state="normal", text="重新登入")
        self.status_icon.configure(text="❌")
        self.status_label.configure(text=f"登入失敗：\n{msg}", text_color="red")

    # ── 登出 ─────────────────────────────────────

    def _logout(self):
        from agent.auth import logout
        logout()
        self.app.agent    = None
        self.app.mcp      = None
        self.app.is_ready = False
        self._refresh()
