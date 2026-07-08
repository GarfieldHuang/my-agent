"""聊天介面：訊息泡泡、推理展開區塊、輸入欄、附加檔案。"""
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
        self.msg_frame = ctk.CTkScrollableFrame(self, fg_color=("gray95", "gray12"))
        self.msg_frame.grid(row=0, column=0, sticky="nsew")
        self.msg_frame.grid_columnconfigure(0, weight=1)

        self.attach_bar = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color="gray", anchor="w"
        )
        self.attach_bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 0))

        input_frame = ctk.CTkFrame(self, height=70)
        input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=8)
        input_frame.grid_columnconfigure(0, weight=1)

        self.input = ctk.CTkTextbox(input_frame, height=52, wrap="word")
        self.input.grid(row=0, column=0, padx=(8, 4), pady=8, sticky="ew")
        self.input.bind("<Return>",       lambda e: self._on_enter(e))
        self.input.bind("<Shift-Return>", lambda e: None)

        # ── IME 修正（Windows 中文輸入法）──────────
        # 切輸入法（Shift / Ctrl+Space）時 IME 會丟棄組字中的內容。
        # 在可能觸發切換的按鍵當下先記住組字字串，之後若發現被丟棄
        # 就手動補回輸入框（見 _guard_composition）。
        # 組字期間按 Enter 是選字，不觸發送出（見 _on_enter）。
        for seq in ("<KeyPress-Shift_L>", "<KeyPress-Shift_R>",
                    "<KeyPress-Control_L>", "<KeyPress-Control_R>",
                    "<FocusOut>"):
            self.input.bind(seq, lambda e: self._guard_composition(), add="+")
        self.input.bind("<Control-space>", self._on_ctrl_space)

        # Ctrl+V：剪貼簿是圖片就直接附加，不用先存檔
        self.input.bind("<Control-v>", self._on_paste)

        ctk.CTkButton(
            input_frame, text="📎", width=40,
            fg_color="transparent", hover_color=("gray70", "gray30"),
            command=self._attach_file
        ).grid(row=0, column=1, padx=2, pady=8)

        self.send_btn = ctk.CTkButton(
            input_frame, text="送出", width=72, command=self._send
        )
        self.send_btn.grid(row=0, column=2, padx=(2, 8), pady=8)

        self._add_system("登入後即可開始對話。Enter 送出，Shift+Enter 換行。")

    # ── 送出 ──────────────────────────────────────

    def _on_ctrl_space(self, event):
        self._guard_composition()
        return "break"   # 攔掉 Tk 預設的空白插入

    def _guard_composition(self):
        """組字內容防丟失。

        記下目前的組字字串與輸入框內容，接著監看約 0.6 秒：
        - 組字還在（或繼續打字）→ 不動作
        - 組字消失、輸入框沒變 → 輸入法把字丟了，手動補回
        - 組字消失、只多出一個（全形）空白 → Ctrl+Space 漏的空白，換成組字內容
        - 組字消失、輸入框有正常新增文字 → 輸入法自己 commit 成功，不動作
        """
        from gui.ime import get_composition
        comp = get_composition()
        if not comp:
            return
        snapshot = self.input.get("1.0", "end-1c")
        state = {"tries": 0}

        def _check():
            cur = get_composition()
            if cur:
                if cur == comp and state["tries"] < 20:
                    state["tries"] += 1
                    self.after(30, _check)
                return   # 組字內容變了 = 使用者還在打字，收工

            now = self.input.get("1.0", "end-1c")
            if now == snapshot:
                self.input.insert("insert", comp)          # 被丟棄 → 補回
            else:
                i = self._diff_single_space(snapshot, now)
                if i is not None:                          # 只漏進一個空白
                    self.input.delete(f"1.0+{i}c", f"1.0+{i + 1}c")
                    self.input.insert("insert", comp)

        self.after(30, _check)

    @staticmethod
    def _diff_single_space(prev: str, now: str) -> int | None:
        """now 若只比 prev 多出一個（全形）空白，回傳其位置，否則 None。"""
        if len(now) != len(prev) + 1:
            return None
        i = next((k for k in range(len(prev)) if prev[k] != now[k]), len(prev))
        if now[i] in (" ", "　") and prev == now[:i] + now[i + 1:]:
            return i
        return None

    def _on_enter(self, event):
        from gui.ime import has_composition
        if has_composition():
            return "break"   # IME 組字中，這個 Enter 是選字不是送出
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
        spinner = self._add_spinner()
        self.send_btn.configure(state="disabled")

        future = self.app.run_async(self.app.agent.chat(text, attachments=files))
        self.after(100, lambda: self._poll(future, spinner))

    def _poll(self, future, spinner):
        if future.done():
            spinner.destroy()
            self.send_btn.configure(state="normal")
            try:
                thinking, reply = future.result()
                if thinking:
                    self._add_reasoning(thinking)
                self._add_bubble(reply, "assistant")
                for img in getattr(self.app.agent, "last_images", []):
                    self._add_image(img)
                self.app.save_current_chat()
            except Exception as e:
                self._add_bubble(f"錯誤：{e}", "error")
        else:
            self.after(100, lambda: self._poll(future, spinner))

    # ── 附加檔案 ──────────────────────────────────

    def _on_paste(self, event):
        """剪貼簿有圖片（截圖/複製的圖）→ 存成暫存 PNG 附加；否則走一般文字貼上。"""
        try:
            from PIL import ImageGrab
            data = ImageGrab.grabclipboard()
        except Exception:
            return None   # 交給預設貼上

        if data is None:
            return None   # 剪貼簿是文字，交給預設貼上

        import tempfile
        import time as _time
        paths: list[str] = []

        if isinstance(data, list):
            # 複製的是檔案（例如從檔案總管複製圖片檔）
            paths = [p for p in data
                     if Path(p).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}]
        else:
            # 複製的是點陣圖（截圖等）→ 存暫存 PNG
            tmp = Path(tempfile.gettempdir()) / f"my-agent-paste-{_time.strftime('%H%M%S')}.png"
            data.save(tmp, "PNG")
            paths = [str(tmp)]

        if not paths:
            return None

        self._pending_files.extend(paths)
        names = ", ".join(Path(p).name for p in self._pending_files)
        self.attach_bar.configure(text=f"📎 {names}")
        return "break"   # 圖片已處理，不要再貼文字

    def _attach_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="選擇要附加的檔案",
            filetypes=[("所有檔案", "*.*"),
                       ("圖片", "*.png *.jpg *.jpeg *.gif *.webp"),
                       ("文件", "*.pdf *.txt *.md *.csv")]
        )
        if path:
            self._pending_files.append(path)
            names = ", ".join(Path(p).name for p in self._pending_files)
            self.attach_bar.configure(text=f"📎 {names}")

    # ── 訊息元件 ──────────────────────────────────

    def _add_bubble(self, text: str, role: str):
        row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=3)

        bg = {"user": ("#1a56db","#1a56db"), "assistant": ("gray82","gray22"),
              "error": ("#c0392b","#922b21")}.get(role, ("gray80","gray20"))
        fg = {"user": ("white","white"), "assistant": ("gray10","gray95"),
              "error": ("white","white")}.get(role, ("gray10","gray90"))
        anchor = "e" if role == "user" else "w"

        bubble = ctk.CTkFrame(row, fg_color=bg, corner_radius=14)
        bubble.pack(anchor=anchor, padx=6)

        lines  = text.count("\n") + max(1, len(text) // 55)
        height = min(max(lines * 22, 36), 400)

        tb = ctk.CTkTextbox(
            bubble, width=480, height=height, wrap="word",
            fg_color=bg, text_color=fg, border_width=0,
            scrollbar_button_color=bg, scrollbar_button_hover_color=bg,
            activate_scrollbars=False, font=ctk.CTkFont(size=13),
        )
        tb.insert("1.0", text)
        tb.configure(state="disabled")
        tb.pack(padx=10, pady=8)
        self._scroll_bottom()

    def _add_reasoning(self, thinking: str):
        """可展開/收合的推理過程區塊（openclaw 風格）。"""
        container = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        container.pack(fill="x", padx=8, pady=(4, 0))

        # 展開/收合按鈕
        toggle_btn = ctk.CTkButton(
            container, text="▶  思考過程",
            fg_color="transparent", text_color="gray",
            hover_color=("gray85", "gray20"),
            anchor="w", height=26, font=ctk.CTkFont(size=11),
        )
        toggle_btn.pack(anchor="w", padx=4)

        # 思考內容（預設隱藏）
        panel = ctk.CTkFrame(container, fg_color=("gray88","gray18"), corner_radius=8)

        lines  = thinking.count("\n") + max(1, len(thinking) // 60)
        height = min(max(lines * 18, 50), 260)

        tb = ctk.CTkTextbox(
            panel, wrap="word", height=height,
            fg_color=("gray88","gray18"), border_width=0,
            text_color=("gray40","gray60"),
            font=ctk.CTkFont(size=11, slant="italic"),
            activate_scrollbars=True,
        )
        tb.insert("1.0", thinking)
        tb.configure(state="disabled")
        tb.pack(padx=10, pady=8, fill="x")

        shown = [False]
        def toggle():
            if shown[0]:
                panel.pack_forget()
                toggle_btn.configure(text="▶  思考過程")
            else:
                panel.pack(fill="x", padx=4, pady=(2, 4))
                toggle_btn.configure(text="▼  思考過程")
                self._scroll_bottom()
            shown[0] = not shown[0]

        toggle_btn.configure(command=toggle)
        self._scroll_bottom()

    def _add_image(self, path):
        """把生成的圖片顯示在對話中，點擊用系統檢視器開啟。"""
        try:
            from PIL import Image
            img = Image.open(path)
            w, h = img.size
            disp_w = min(w, 360)
            disp_h = max(1, round(h * disp_w / w))
            cimg = ctk.CTkImage(light_image=img, dark_image=img, size=(disp_w, disp_h))

            row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            label = ctk.CTkLabel(row, image=cimg, text="", cursor="hand2")
            label.pack(anchor="w", padx=6)

            import webbrowser
            label.bind("<Button-1>", lambda e: webbrowser.open(Path(path).as_uri()))
            self._scroll_bottom()
        except Exception:
            pass  # 圖片顯示失敗不影響對話（路徑已在回覆文字裡）

    def _add_spinner(self) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.msg_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=3)
        bubble = ctk.CTkFrame(row, fg_color=("gray82","gray22"), corner_radius=14)
        bubble.pack(anchor="w", padx=6)
        ctk.CTkLabel(bubble, text="⏳ 思考中…", text_color="gray").pack(padx=14, pady=8)
        self._scroll_bottom()
        return row

    def _add_system(self, text: str):
        ctk.CTkLabel(
            self.msg_frame, text=text,
            text_color="gray", font=ctk.CTkFont(size=12), wraplength=520
        ).pack(pady=12)

    def _scroll_bottom(self):
        self.msg_frame.update_idletasks()
        try:
            self.msg_frame._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Session 載入/重置 ─────────────────────────

    def reset(self):
        """清空訊息區（開新對話）。"""
        for w in self.msg_frame.winfo_children():
            w.destroy()
        self._pending_files = []
        self.attach_bar.configure(text="")
        self._add_system("新對話開始。")

    def render_history(self, history: list[dict]):
        """把載入的 session 歷史重建成訊息泡泡。"""
        for w in self.msg_frame.winfo_children():
            w.destroy()
        for msg in history:
            role = msg.get("role", "")
            text = self._content_text(msg.get("content", ""))
            if not text:
                continue
            self._add_bubble(text, "user" if role == "user" else "assistant")
            if role == "assistant":
                # 回覆裡的 🖼️ 路徑若檔案還在，重新顯示圖片
                for line in text.splitlines():
                    if line.strip().startswith("🖼️"):
                        p = Path(line.strip().lstrip("🖼️").strip())
                        if p.exists():
                            self._add_image(p)

    @staticmethod
    def _content_text(content) -> str:
        if isinstance(content, str):
            return content
        parts = []
        for p in content:
            if not isinstance(p, dict):
                continue
            if p.get("type") in ("input_text", "text"):
                parts.append(p.get("text", ""))
            elif p.get("type") in ("image_url", "input_image"):
                parts.append("📎 [圖片附件]")
        return "\n".join(parts)

    # ── App callbacks ─────────────────────────────

    def on_agent_ready(self):
        self._add_system("✓ 已連線，開始對話吧！")

    def on_show(self):
        self.input.focus_set()
