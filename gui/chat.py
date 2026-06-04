"""聊天介面：訊息泡泡、輸入欄、附加檔案。"""
import threading
import tkinter as tk
from pathlib import Path

import customtkinter as ctk


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._pending_files: list[str] = []
        self._build()

    def _build(self):
        # 訊息列表
        self.msg_frame = ctk.CTkScrollableFrame(self, fg_color=("gray95", "gray12"))
        self.msg_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.msg_frame.grid_columnconfigure(0, weight=1)

        # 附加檔案提示列
        self.attach_bar = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11),
            text_color="gray", anchor="w"
        )
        self.attach_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 0))

        # 輸入區
        input_frame = ctk.CTkFrame(self, height=70)
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        input_frame.grid_columnconfigure(0, weight=1)

        self.input = ctk.CTkTextbox(input_frame, height=52, wrap="word")
        self.input.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="ew")
        self.input.bind("<Return>",       lambda e: self._on_enter(e))
        self.input.bind("<Shift-Return>", lambda e: None)

        file_btn = ctk.CTkButton(
            input_frame, text="📎", width=40,
            fg_color="transparent", hover_color=("gray70", "gray30"),
            command=self._attach_file
        )
        file_btn.grid(row=0, column=1, padx=2, pady=8)

        self.send_btn = ctk.CTkButton(
            input_frame, text="送出", width=72, command=self._send
        )
        self.send_btn.grid(row=0, column=2, padx=(2, 8), pady=8)

        # 歡迎訊息
        self._add_system("登入後即可開始對話。輸入訊息，按 Enter 送出（Shift+Enter 換行）。")

    # ── 送出訊息 ──────────────────────────────────

    def _on_enter(self, event):
        self._send()
        return "break"

    def _send(self):
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        if not self.app.is_ready:
            self._add_system("⚠ 尚未登入，請先到「帳號」頁面登入。")
            return

        self.input.delete("1.0", "end")
        files, self._pending_files = self._pending_files, []
        self.attach_bar.configure(text="")

        self._add_bubble(text, "user")
        thinking = self._add_thinking()
        self.send_btn.configure(state="disabled")

        future = self.app.run_async(
            self.app.agent.chat(text, attachments=files)
        )
        self.after(100, lambda: self._poll_reply(future, thinking))

    def _poll_reply(self, future, thinking_widget):
        if future.done():
            thinking_widget.destroy()
            self.send_btn.configure(state="normal")
            try:
                self._add_bubble(future.result(), "assistant")
            except Exception as e:
                self._add_bubble(f"錯誤：{e}", "error")
        else:
            self.after(100, lambda: self._poll_reply(future, thinking_widget))

    # ── 附加檔案 ──────────────────────────────────

    def _attach_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="選擇要附加的檔案",
            filetypes=[("所有檔案", "*.*"), ("圖片", "*.png *.jpg *.jpeg *.gif *.webp"),
                       ("文件", "*.pdf *.txt *.md *.csv")]
        )
        if path:
            self._pending_files.append(path)
            names = ", ".join(Path(p).name for p in self._pending_files)
            self.attach_bar.configure(text=f"📎 {names}")

    # ── 訊息泡泡 ──────────────────────────────────

    def _add_bubble(self, text: str, role: str):
        row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=3)

        colors = {
            "user":      ("#1a56db", "#1a56db"),
            "assistant": ("gray82",  "gray22"),
            "error":     ("#c0392b", "#922b21"),
        }
        text_colors = {
            "user": ("white", "white"),
            "assistant": ("gray10", "gray95"),
            "error": ("white", "white"),
        }
        anchor = "e" if role == "user" else "w"

        bubble = ctk.CTkFrame(row, fg_color=colors.get(role, ("gray80", "gray20")),
                              corner_radius=14)
        bubble.pack(anchor=anchor, padx=6)

        ctk.CTkLabel(
            bubble, text=text,
            text_color=text_colors.get(role, ("gray10", "gray90")),
            wraplength=480, justify="left", anchor="w",
        ).pack(padx=14, pady=8)

        self._scroll_bottom()

    def _add_thinking(self) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=3)
        bubble = ctk.CTkFrame(row, fg_color=("gray82", "gray22"), corner_radius=14)
        bubble.pack(anchor="w", padx=6)
        ctk.CTkLabel(bubble, text="⏳ 思考中…", text_color="gray").pack(padx=14, pady=8)
        self._scroll_bottom()
        return row

    def _add_system(self, text: str):
        ctk.CTkLabel(
            self.msg_frame, text=text,
            text_color="gray", font=ctk.CTkFont(size=12),
            wraplength=520
        ).pack(pady=12)

    def _scroll_bottom(self):
        self.msg_frame.update_idletasks()
        try:
            self.msg_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Callbacks from App ────────────────────────

    def on_agent_ready(self):
        self._add_system("✓ 已連線，開始對話吧！")

    def on_show(self):
        self.input.focus_set()
