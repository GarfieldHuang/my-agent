"""聊天介面：訊息泡泡、推理展開區塊、輸入欄、附加檔案。"""

import logging
import threading
from pathlib import Path
import customtkinter as ctk
from PIL import Image
from tkinterdnd2 import DND_FILES

log = logging.getLogger("my-agent")


class ChatView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")

        self.app = app

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._pending_files: list[str] = []
        self._chip_images: list = []   # 縮圖的 CTkImage 參照，防止被 GC

        # 對話重建與捲動排程控制。
        self._rendering_history = False
        self._scroll_jobs: list[str] = []
        self._render_generation = 0

        self._build()

    # ─────────────────────────────────────────────
    # 介面建立
    # ─────────────────────────────────────────────

    def _build(self):
        
        # 外層對話訊息捲動區
        self.msg_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=("gray95", "gray12"),
            scrollbar_button_color=("gray65", "gray35"),
            scrollbar_button_hover_color=("gray50", "gray50"),
            corner_radius=0,
        )
        self.msg_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.msg_frame.grid_columnconfigure(0, weight=1)

        # 附件顯示列
        self.attach_bar = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
        )
        self.attach_bar.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(4, 0),
        )

        # 附件縮圖列（有附件時才顯示）
        self.attach_frame = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        self.attach_frame.grid(
            row=2,
            column=0,
            sticky="w",
            padx=14,
            pady=(2, 0),
        )
        self.attach_frame.grid_remove()

        # 輸入區
        input_frame = ctk.CTkFrame(
            self,
            height=70,
        )
        input_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=10,
            pady=8,
        )
        input_frame.grid_columnconfigure(0, weight=1)

        self.input = ctk.CTkTextbox(
            input_frame,
            height=52,
            wrap="word",
        )
        self.input.grid(
            row=0,
            column=0,
            padx=(8, 4),
            pady=8,
            sticky="ew",
        )

        self.input.bind(
            "<Return>",
            self._on_enter,
        )
        self.input.bind(
            "<Shift-Return>",
            lambda event: None,
        )

        # ── IME 修正（Windows 中文輸入法）──────────
        self._ime_state = {
            "comp": "",
            "base": "",
            "pending": None,
            "skip_until": 0.0,
        }

        for sequence in (
            "<KeyPress-Escape>",
            "<KeyPress-BackSpace>",
        ):
            self.input.bind(
                sequence,
                self._ime_mark_cancel,
                add="+",
            )

        self.input.bind(
            "<Control-space>",
            self._on_ctrl_space,
        )

        self.after(
            50,
            self._ime_poll,
        )

        # Ctrl+V：剪貼簿若為圖片，直接附加
        self.input.bind(
            "<Control-v>",
            self._on_paste,
        )

        icon_path = Path(__file__).parent / "assets" / "icon_attach.png"
        
        self.attach_icon = ctk.CTkImage(
            light_image=Image.open(icon_path),
            dark_image=Image.open(icon_path),
            size=(22, 22),
        )

        # 附件按鈕
        ctk.CTkButton(
            input_frame,
            text="",
            image=self.attach_icon,
            width=40,
            height=40,
            fg_color="transparent",
            hover_color=("gray70", "gray30"),
            command=self._attach_file,
        ).grid(
            row=0,
            column=1,
            padx=2,
            pady=8,
        )

        # 送出按鈕
        self.send_btn = ctk.CTkButton(
            input_frame,
            text="送出",
            width=72,
            command=self._send,
        )
        self.send_btn.grid(
            row=0,
            column=2,
            padx=(2, 8),
            pady=8,
        )

        # ── 模型 / 推理強度快速選單 ────────────────
        from gui.settings import MODELS, REASONING
        from agent.auth import load_config, get_model

        opts_row = ctk.CTkFrame(
            input_frame,
            fg_color="transparent",
        )
        opts_row.grid(
            row=1,
            column=0,
            columnspan=3,
            padx=8,
            pady=(0, 6),
            sticky="w",
        )

        cfg = load_config()
        model = cfg.get("model") or get_model()
        model_values = (
            MODELS if model in MODELS else MODELS + [model]
        )

        ctk.CTkLabel(
            opts_row,
            text="模型",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).grid(row=0, column=0, padx=(2, 6))

        self.model_var = ctk.StringVar(value=model)
        self.model_menu = ctk.CTkOptionMenu(
            opts_row,
            values=model_values,
            variable=self.model_var,
            width=150,
            height=26,
            font=ctk.CTkFont(size=12),
            command=lambda _v: self._apply_chat_options(),
        )
        self.model_menu.grid(row=0, column=1, padx=(0, 14))

        # 推理強度用短標籤（取全名「（」之前的部分）
        self._effort_short = [
            (key, label.split("（")[0])
            for key, label in REASONING
        ]
        effort = cfg.get("reasoning_effort", "medium")
        short = next(
            (s for k, s in self._effort_short if k == effort),
            "Medium",
        )

        ctk.CTkLabel(
            opts_row,
            text="推理",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).grid(row=0, column=2, padx=(0, 6))

        self.effort_var = ctk.StringVar(value=short)
        self.effort_menu = ctk.CTkOptionMenu(
            opts_row,
            values=[s for _k, s in self._effort_short],
            variable=self.effort_var,
            width=110,
            height=26,
            font=ctk.CTkFont(size=12),
            command=lambda _v: self._apply_chat_options(),
        )
        self.effort_menu.grid(row=0, column=3)

        # 背景抓取後端即時模型列表更新選單
        self._fetch_models_async()

        self._add_system(
            "登入後即可開始對話。Enter 送出，Shift+Enter 換行。"
        )

        # 啟用檔案拖放。
        self._setup_file_drop()

    # ─────────────────────────────────────────────
    # 檔案拖放
    # ─────────────────────────────────────────────

    def _setup_file_drop(self):
        """讓聊天區、輸入框與附件列支援拖放檔案。"""

        drop_targets = [
            self.msg_frame,
            self.input,
            self.attach_bar,
        ]

        registered = set()

        for widget in drop_targets:
            targets = [widget]

            # CustomTkinter 的事件有時由內部 Tk 元件接收。
            for attribute in (
                "_textbox",
                "_canvas",
                "_text_label",
                "_parent_canvas",
            ):
                internal_widget = getattr(widget, attribute, None)

                if internal_widget is not None:
                    targets.append(internal_widget)

            for target in targets:
                target_name = str(target)

                if target_name in registered:
                    continue

                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind(
                        "<<Drop>>",
                        self._on_file_drop,
                    )
                    target.dnd_bind(
                        "<<DropEnter>>",
                        self._on_drop_enter,
                    )
                    target.dnd_bind(
                        "<<DropLeave>>",
                        self._on_drop_leave,
                    )
                    registered.add(target_name)
                except Exception:
                    # 並非每個 CustomTkinter 內部元件都能註冊拖放。
                    log.debug(
                        "拖放目標註冊失敗：%s",
                        target_name,
                        exc_info=True,
                    )

    def _on_file_drop(self, event):
        """接收拖入的檔案，並加入待送出的附件清單。"""

        try:
            # splitlist 能正確處理含空格與大括號的 Windows 路徑。
            dropped_paths = self.tk.splitlist(event.data)
            added_count = 0

            for raw_path in dropped_paths:
                file_path = Path(raw_path).expanduser()

                if not file_path.is_file():
                    continue

                normalized_path = str(file_path.resolve())

                if normalized_path in self._pending_files:
                    continue

                self._pending_files.append(normalized_path)
                added_count += 1

            self._restore_drop_style()

            if added_count:
                self._add_system(
                    f"已附加 {added_count} 個檔案。"
                )

        except Exception:
            log.exception("拖放附加檔案失敗")
            self._restore_drop_style()
            self._add_system(
                "檔案拖放失敗，請重新嘗試。"
            )

        return "break"

    def _on_drop_enter(self, event):
        """檔案進入拖放區時顯示提示。"""

        self.attach_bar.configure(
            text="放開滑鼠即可附加檔案",
            text_color=("#1a56db", "#6ea8ff"),
        )

        return getattr(event, "action", "copy")

    def _on_drop_leave(self, event):
        """檔案離開拖放區時還原附件列。"""

        self._restore_drop_style()
        return getattr(event, "action", "copy")

    def _restore_drop_style(self):
        """還原附件列的提示文字與縮圖列。"""

        self.attach_bar.configure(text="", text_color="gray")
        self._update_attachment_bar()

    def _update_attachment_bar(self):
        """重建待送出附件的縮圖列（圖片顯示縮圖，其他顯示檔名，均附移除鈕）。"""

        for widget in self.attach_frame.winfo_children():
            widget.destroy()
        self._chip_images = []

        if not self._pending_files:
            self.attach_frame.grid_remove()
            return

        self.attach_frame.grid()

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico"}

        for col, path in enumerate(self._pending_files):
            file_path = Path(path)

            chip = ctk.CTkFrame(
                self.attach_frame,
                corner_radius=8,
            )
            chip.grid(row=0, column=col, padx=(0, 6), pady=2)

            thumb = None
            if file_path.suffix.lower() in image_exts:
                try:
                    img = Image.open(file_path)
                    w, h = img.size
                    scale = 48 / max(w, h)
                    thumb = ctk.CTkImage(
                        light_image=img,
                        dark_image=img,
                        size=(
                            max(1, round(w * scale)),
                            max(1, round(h * scale)),
                        ),
                    )
                    self._chip_images.append(thumb)
                except Exception:
                    thumb = None

            if thumb is not None:
                ctk.CTkLabel(
                    chip, text="", image=thumb
                ).grid(row=0, column=0, padx=(6, 2), pady=4)
            else:
                ctk.CTkLabel(
                    chip,
                    text=f"📎 {file_path.name}",
                    font=ctk.CTkFont(size=12),
                ).grid(row=0, column=0, padx=(8, 2), pady=4)

            ctk.CTkButton(
                chip,
                text="✕",
                width=22,
                height=22,
                corner_radius=6,
                fg_color="transparent",
                text_color="gray",
                hover_color=("gray70", "gray30"),
                command=lambda p=path: self._remove_attachment(p),
            ).grid(row=0, column=1, padx=(0, 4))

    def _remove_attachment(self, path: str):
        """移除單一待送出附件。"""

        if path in self._pending_files:
            self._pending_files.remove(path)

        self._update_attachment_bar()

    def _apply_chat_options(self, _value=None):
        """Chat 快速選單變更時寫入設定並即時更新 agent。"""

        from agent.auth import load_config, save_config

        cfg = load_config()
        cfg["model"] = self.model_var.get()

        short = self.effort_var.get()
        cfg["reasoning_effort"] = next(
            (k for k, s in self._effort_short if s == short),
            "medium",
        )
        save_config(cfg)

        if self.app.agent:
            self.app.agent.model            = cfg["model"]
            self.app.agent.reasoning_effort = cfg["reasoning_effort"]

    def _fetch_models_async(self):
        """背景抓取後端即時模型列表；失敗或未登入時維持現有選單。"""

        def worker():
            from agent.auth import fetch_available_models

            models = fetch_available_models()
            if models:
                try:
                    self.after(0, lambda: self._apply_models(models))
                except Exception:
                    pass   # 視窗已關閉

        threading.Thread(target=worker, daemon=True).start()

    def _apply_models(self, models: list[str]):
        current = self.model_var.get()
        if current and current not in models:
            models = models + [current]
        self.model_menu.configure(values=models)

    def _sync_chat_options(self):
        """從設定檔同步選單（設定頁改過時保持一致）。"""

        from agent.auth import load_config, get_model

        cfg = load_config()
        model = cfg.get("model") or get_model()

        values = list(self.model_menu.cget("values"))
        if model not in values:
            self.model_menu.configure(values=values + [model])
        self.model_var.set(model)

        effort = cfg.get("reasoning_effort", "medium")
        self.effort_var.set(next(
            (s for k, s in self._effort_short if k == effort),
            "Medium",
        ))

    # ─────────────────────────────────────────────
    # 滑鼠滾輪控制
    # ─────────────────────────────────────────────

    @staticmethod
    def _wheel_direction(event) -> int:
        """
        將不同作業系統的滾輪事件轉為方向。

        回傳：
        -1：向上
         1：向下
         0：無法判定
        """

        delta = getattr(event, "delta", 0)

        # Windows 與 macOS
        if delta:
            return -1 if delta > 0 else 1

        button_number = getattr(event, "num", None)

        # Linux
        if button_number == 4:
            return -1

        if button_number == 5:
            return 1

        return 0

    def _scroll_outer_messages(self, direction: int):
        """
        捲動整個對話訊息區。

        direction：
        -1：向上
         1：向下
        """

        try:
            canvas = self.msg_frame._parent_canvas
            canvas.yview_scroll(direction * 40, "units")
        except Exception:
            log.exception("無法捲動外層對話訊息區")

    def _bind_outer_scroll(self, widget):
        """
        讓指定元件上的滑鼠滾輪控制整個對話區。
        適用於圖片、系統訊息、檔案卡片等元件。
        """

        def on_mousewheel(event):
            direction = self._wheel_direction(event)

            if direction:
                self._scroll_outer_messages(direction)

            return "break"

        targets = [widget]

        # 部分 CustomTkinter 元件的事件實際由內部 Tk 元件接收
        for attribute in (
            "_canvas",
            "_text_label",
            "_textbox",
        ):
            internal_widget = getattr(widget, attribute, None)

            if internal_widget is not None:
                targets.append(internal_widget)

        for target in targets:
            try:
                target.bind(
                    "<MouseWheel>",
                    on_mousewheel,
                    add="+",
                )
                target.bind(
                    "<Button-4>",
                    on_mousewheel,
                    add="+",
                )
                target.bind(
                    "<Button-5>",
                    on_mousewheel,
                    add="+",
                )
            except Exception:
                pass

    def _bind_bubble_scroll(self, textbox):
        """
        讓訊息泡泡具有獨立滑鼠滾輪控制。

        行為：
        1. 泡泡內還有內容時，先捲動泡泡。
        2. 泡泡已到頂端或底端時，改捲動整個對話區。
        3. 短訊息無須捲動時，直接捲動整個對話區。
        """

        def on_mousewheel(event):
            direction = self._wheel_direction(event)

            if not direction:
                return "break"

            try:
                first, last = textbox.yview()

                can_scroll_up = (
                    direction < 0
                    and first > 0.0001
                )

                can_scroll_down = (
                    direction > 0
                    and last < 0.9999
                )

                if can_scroll_up or can_scroll_down:
                    # 泡泡內仍有內容可捲動
                    textbox.yview_scroll(
                        direction * 3,
                        "units",
                    )
                else:
                    # 泡泡已到邊界，改捲動外層對話區
                    self._scroll_outer_messages(direction)

            except Exception:
                log.exception("無法捲動訊息泡泡")
                self._scroll_outer_messages(direction)

            return "break"

        targets = [textbox]

        # CTkTextbox 內部實際文字元件
        internal_textbox = getattr(
            textbox,
            "_textbox",
            None,
        )

        if internal_textbox is not None:
            targets.append(internal_textbox)

        for target in targets:
            try:
                target.bind(
                    "<MouseWheel>",
                    on_mousewheel,
                    add="+",
                )
                target.bind(
                    "<Button-4>",
                    on_mousewheel,
                    add="+",
                )
                target.bind(
                    "<Button-5>",
                    on_mousewheel,
                    add="+",
                )
            except Exception:
                pass

    # ─────────────────────────────────────────────
    # 送出訊息
    # ─────────────────────────────────────────────

    def _on_ctrl_space(self, event):
        """
        Ctrl+Space 切換輸入法。

        組字救援交由 _ime_poll 處理。
        此處只處理沒在組字時，可能漏進輸入框的空白。
        """

        from gui.ime import get_composition

        if not get_composition():
            snapshot = self.input.get(
                "1.0",
                "end-1c",
            )

            state = {
                "tries": 0,
            }

            def _watch():
                now = self.input.get(
                    "1.0",
                    "end-1c",
                )

                index = self._diff_single_space(
                    snapshot,
                    now,
                )

                if index is not None:
                    self.input.delete(
                        f"1.0+{index}c",
                        f"1.0+{index + 1}c",
                    )
                    return

                state["tries"] += 1

                if (
                    state["tries"] < 10
                    and now == snapshot
                ):
                    self.after(
                        20,
                        _watch,
                    )

            self.after(
                10,
                _watch,
            )

        return "break"

    # ─────────────────────────────────────────────
    # IME 組字救援
    # ─────────────────────────────────────────────

    def _ime_mark_cancel(self, event=None):
        import time

        self._ime_state["skip_until"] = (
            time.time() + 0.4
        )

    def _ime_poll(self):
        try:
            self._ime_tick()
        except Exception:
            pass
        finally:
            self.after(
                50,
                self._ime_poll,
            )

    def _ime_tick(self):
        import time

        from gui.ime import get_composition

        state = self._ime_state

        # 焦點不在聊天輸入框時重置
        focused = self.focus_get()

        if (
            not focused
            or not str(focused).startswith(str(self.input))
        ):
            state.update(
                comp="",
                pending=None,
            )
            return

        composition = get_composition()

        text = self.input.get(
            "1.0",
            "end-1c",
        )

        if composition:
            state.update(
                comp=composition,
                base=text,
                pending=None,
            )
            return

        if state["comp"]:
            # 組字剛消失，等待正常文字提交
            state["pending"] = {
                "comp": state["comp"],
                "base": state["base"],
            }
            state["comp"] = ""
            return

        pending = state["pending"]

        if not pending:
            return

        state["pending"] = None

        if time.time() < state["skip_until"]:
            log.debug(
                "IME rescue skipped "
                "(user cancelled) comp=%r",
                pending["comp"],
            )
            return

        if text == pending["base"]:
            # 組字內容未進入輸入框，手動補回
            log.debug(
                "IME rescue insert comp=%r",
                pending["comp"],
            )

            self.input.insert(
                "insert",
                pending["comp"],
            )
        else:
            index = self._diff_single_space(
                pending["base"],
                text,
            )

            if index is not None:
                # 將誤插入的空白替換成組字內容
                log.debug(
                    "IME rescue replace-space comp=%r",
                    pending["comp"],
                )

                self.input.delete(
                    f"1.0+{index}c",
                    f"1.0+{index + 1}c",
                )
                self.input.insert(
                    "insert",
                    pending["comp"],
                )
            else:
                log.debug(
                    "IME committed normally, "
                    "text grew by %d chars",
                    len(text) - len(pending["base"]),
                )

    @staticmethod
    def _diff_single_space(
        previous: str,
        current: str,
    ) -> int | None:
        """
        current 若只比 previous 多一個半形或全形空白，
        回傳空白位置；否則回傳 None。
        """

        if len(current) != len(previous) + 1:
            return None

        index = next(
            (
                position
                for position in range(len(previous))
                if previous[position] != current[position]
            ),
            len(previous),
        )

        if (
            current[index] in (" ", "　")
            and previous
            == current[:index] + current[index + 1:]
        ):
            return index

        return None

    def _on_enter(self, event):
        from gui.ime import has_composition

        if has_composition():
            # IME 組字中，Enter 是選字而非送出
            return "break"

        self._send()

        return "break"

    def _send(self):
        text = self.input.get(
            "1.0",
            "end-1c",
        ).strip()

        if not text:
            return

        if not self.app.is_ready:
            self._add_system(
                "⚠ 尚未登入，請先到「帳號」頁面登入。"
            )
            return

        self.input.delete(
            "1.0",
            "end",
        )

        files = self._pending_files
        self._pending_files = []

        self.attach_bar.configure(text="")
        self._update_attachment_bar()

        self._add_bubble(
            text,
            "user",
        )

        spinner = self._add_spinner()

        self.send_btn.configure(
            state="disabled",
        )

        future = self.app.run_async(
            self.app.agent.chat(
                text,
                attachments=files,
            )
        )

        self.after(
            100,
            lambda: self._poll(
                future,
                spinner,
            ),
        )

    def _poll(self, future, spinner):
        if future.done():
            spinner.destroy()

            self.send_btn.configure(
                state="normal",
            )

            try:
                thinking, reply = future.result()

                if thinking:
                    self._add_reasoning(thinking)

                self._add_bubble(
                    reply,
                    "assistant",
                )

                for image_path in getattr(
                    self.app.agent,
                    "last_images",
                    [],
                ):
                    self._add_image(image_path)

                for file_path in getattr(
                    self.app.agent,
                    "last_files",
                    [],
                ):
                    self._add_file_link(file_path)

                self.app.save_current_chat()

            except Exception as error:
                self._add_bubble(
                    f"錯誤：{error}",
                    "error",
                )
        else:
            self.after(
                100,
                lambda: self._poll(
                    future,
                    spinner,
                ),
            )

    # ─────────────────────────────────────────────
    # 附加檔案
    # ─────────────────────────────────────────────

    def _on_paste(self, event):
        """
        剪貼簿有圖片時存成暫存 PNG 並附加；
        若剪貼簿為文字，交由預設貼上處理。
        """

        try:
            from PIL import ImageGrab

            data = ImageGrab.grabclipboard()
        except Exception:
            return None

        if data is None:
            return None

        import tempfile
        import time as current_time

        paths: list[str] = []

        if isinstance(data, list):
            # 從檔案總管複製的圖片檔
            paths = [
                path
                for path in data
                if Path(path).suffix.lower()
                in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".webp",
                }
            ]
        else:
            # 截圖或點陣圖
            temporary_path = (
                Path(tempfile.gettempdir())
                / (
                    "my-agent-paste-"
                    f"{current_time.strftime('%H%M%S')}.png"
                )
            )

            data.save(
                temporary_path,
                "PNG",
            )

            paths = [
                str(temporary_path),
            ]

        if not paths:
            return None

        for path in paths:
            if path not in self._pending_files:
                self._pending_files.append(path)

        self._update_attachment_bar()

        return "break"

    def _attach_file(self):
        from tkinter import filedialog

        paths = filedialog.askopenfilenames(
            title="選擇要附加的檔案",
            filetypes=[
                (
                    "所有檔案",
                    "*.*",
                ),
                (
                    "圖片",
                    "*.png *.jpg *.jpeg *.gif *.webp",
                ),
                (
                    "文件",
                    "*.pdf *.txt *.md *.csv *.docx *.xlsx *.pptx",
                ),
            ],
        )

        for path in paths:
            normalized_path = str(Path(path).resolve())

            if normalized_path not in self._pending_files:
                self._pending_files.append(normalized_path)

        self._update_attachment_bar()

    # ─────────────────────────────────────────────
    # 訊息泡泡
    # ─────────────────────────────────────────────

    DEFAULT_BUBBLE_MAX_LINES = 15

    def _bubble_max_lines(self) -> int:
        """訊息泡泡的最大顯示行數（config.json 的 bubble_max_lines）。"""
        from agent.auth import load_config

        try:
            return max(1, int(
                load_config().get(
                    "bubble_max_lines",
                    self.DEFAULT_BUBBLE_MAX_LINES,
                )
            ))
        except Exception:
            return self.DEFAULT_BUBBLE_MAX_LINES

    def _fit_textbox_height(
        self,
        textbox: ctk.CTkTextbox,
        max_lines: int = 15,
        pad: int = 26,   # CTkTextbox 圓角內距（上下各約 corner_radius）+ 餘裕
    ):
        """依實際換行後的顯示行數調整高度。

        字數粗估對中文（全形字寬）嚴重失準，改在排版完成後
        用 tk 的 displaylines 量真實行數。超過 max_lines 才出現
        泡泡內捲軸。
        """

        def fit(attempt: int = 0):
            try:
                tk_text = textbox._textbox

                # 寬度尚未確定時換行數不可信，稍後重量
                if tk_text.winfo_width() <= 1 and attempt < 10:
                    textbox.after(30, lambda: fit(attempt + 1))
                    return

                # displaylines 回傳的是「換行次數」，單行時為 None → 行數要 +1
                lines = tk_text.count("1.0", "end-1c", "displaylines")
                if isinstance(lines, (tuple, list)):
                    lines = lines[0]
                lines = max(1, min(int(lines or 0) + 1, max_lines))

                line_height = int(tk_text.tk.call(
                    "font", "metrics", tk_text.cget("font"), "-linespace"
                ))

                textbox.configure(height=lines * line_height + pad)
                self._scroll_bottom()
            except Exception:
                pass   # 元件可能已被銷毀

        textbox.after_idle(fit)

    def _add_bubble(
        self,
        text: str,
        role: str,
    ):
        row = ctk.CTkFrame(
            self.msg_frame,
            fg_color="transparent",
        )
        row.pack(
            fill="x",
            padx=8,
            pady=3,
        )

        background_color = {
            "user": (
                "#1a56db",
                "#1a56db",
            ),
            "assistant": (
                "gray82",
                "gray22",
            ),
            "error": (
                "#c0392b",
                "#922b21",
            ),
        }.get(
            role,
            (
                "gray80",
                "gray20",
            ),
        )

        text_color = {
            "user": (
                "white",
                "white",
            ),
            "assistant": (
                "gray10",
                "gray95",
            ),
            "error": (
                "white",
                "white",
            ),
        }.get(
            role,
            (
                "gray10",
                "gray90",
            ),
        )

        anchor = (
            "e"
            if role == "user"
            else "w"
        )

        bubble = ctk.CTkFrame(
            row,
            fg_color=background_color,
            corner_radius=14,
        )
        bubble.pack(
            anchor=anchor,
            padx=6,
        )

        # 高度先給一行，插入文字後依實際顯示行數調整
        # （最多 15 行，超過才用泡泡內 scrollbar）
        textbox = ctk.CTkTextbox(
            bubble,
            width=480,
            height=36,
            wrap="word",
            fg_color=background_color,
            text_color=text_color,
            border_width=0,
            corner_radius=10,
            scrollbar_button_color=(
                "gray65",
                "gray40",
            ),
            scrollbar_button_hover_color=(
                "gray50",
                "gray55",
            ),
            activate_scrollbars=True,
            font=ctk.CTkFont(size=13),
        )

        textbox.insert(
            "1.0",
            text,
        )

        textbox.configure(
            state="disabled",
        )

        textbox.pack(
            padx=10,
            pady=8,
        )

        # 依實際顯示行數調整高度（中文寬度粗估會失準）；
        # 超過設定的最大行數時固定高度、泡泡內捲動
        self._fit_textbox_height(
            textbox,
            max_lines=self._bubble_max_lines(),
        )

        # 每個訊息泡泡皆可使用滑鼠滾輪
        self._bind_bubble_scroll(textbox)

        # 行、泡泡空白處控制外層對話區
        self._bind_outer_scroll(row)
        self._bind_outer_scroll(bubble)

        self._scroll_bottom()

    # ─────────────────────────────────────────────
    # 推理展開區塊
    # ─────────────────────────────────────────────

    def _add_reasoning(self, thinking: str):
        """
        可展開或收合的推理過程區塊。
        """

        container = ctk.CTkFrame(
            self.msg_frame,
            fg_color="transparent",
        )
        container.pack(
            fill="x",
            padx=8,
            pady=(4, 0),
        )

        toggle_button = ctk.CTkButton(
            container,
            text="▶  思考過程",
            fg_color="transparent",
            text_color="gray",
            hover_color=(
                "gray85",
                "gray20",
            ),
            anchor="w",
            height=26,
            font=ctk.CTkFont(size=11),
        )
        toggle_button.pack(
            anchor="w",
            padx=4,
        )

        panel = ctk.CTkFrame(
            container,
            fg_color=(
                "gray88",
                "gray18",
            ),
            corner_radius=8,
        )

        textbox = ctk.CTkTextbox(
            panel,
            wrap="word",
            height=50,   # 展開時依實際行數調整
            fg_color=(
                "gray88",
                "gray18",
            ),
            border_width=0,
            text_color=(
                "gray40",
                "gray60",
            ),
            scrollbar_button_color=(
                "gray65",
                "gray40",
            ),
            scrollbar_button_hover_color=(
                "gray50",
                "gray55",
            ),
            font=ctk.CTkFont(
                size=11,
                slant="italic",
            ),
            activate_scrollbars=True,
        )

        textbox.insert(
            "1.0",
            thinking,
        )

        textbox.configure(
            state="disabled",
        )

        textbox.pack(
            padx=10,
            pady=8,
            fill="x",
        )

        # 思考內容也使用相同的智慧滾輪行為
        self._bind_bubble_scroll(textbox)
        self._bind_outer_scroll(container)
        self._bind_outer_scroll(panel)
        self._bind_outer_scroll(toggle_button)

        shown = [False]

        def toggle():
            if shown[0]:
                panel.pack_forget()

                toggle_button.configure(
                    text="▶  思考過程",
                )
            else:
                panel.pack(
                    fill="x",
                    padx=4,
                    pady=(2, 4),
                )

                toggle_button.configure(
                    text="▼  思考過程",
                )

                # 首次展開後才知道實際寬度，依顯示行數調高度
                self._fit_textbox_height(textbox, max_lines=12)

                self._scroll_bottom()

            shown[0] = not shown[0]

        toggle_button.configure(
            command=toggle,
        )

        self._scroll_bottom()

    # ─────────────────────────────────────────────
    # 圖片
    # ─────────────────────────────────────────────

    def _add_image(self, path):
        """
        在對話中顯示圖片。
        點擊圖片後使用系統預設程式開啟。
        """

        try:
            from PIL import Image

            image = Image.open(path)

            width, height = image.size

            display_width = min(
                width,
                360,
            )

            display_height = max(
                1,
                round(
                    height
                    * display_width
                    / width
                ),
            )

            custom_image = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=(
                    display_width,
                    display_height,
                ),
            )

            row = ctk.CTkFrame(
                self.msg_frame,
                fg_color="transparent",
            )
            row.pack(
                fill="x",
                padx=8,
                pady=3,
            )

            label = ctk.CTkLabel(
                row,
                image=custom_image,
                text="",
                cursor="hand2",
            )
            label.pack(
                anchor="w",
                padx=6,
            )

            import webbrowser

            label.bind(
                "<Button-1>",
                lambda event: webbrowser.open(
                    Path(path).as_uri()
                ),
            )

            self._bind_outer_scroll(row)
            self._bind_outer_scroll(label)

            self._scroll_bottom()

        except Exception:
            log.exception(
                "無法顯示圖片：%s",
                path,
            )

    # ─────────────────────────────────────────────
    # 檔案連結
    # ─────────────────────────────────────────────

    def _add_file_link(self, path):
        """
        將產生的文件顯示成可點擊的檔案卡片。
        """

        file_path = Path(path)

        icon = {
            ".docx": "📝",
            ".pptx": "📊",
            ".pdf": "📄",
        }.get(
            file_path.suffix.lower(),
            "📄",
        )

        row = ctk.CTkFrame(
            self.msg_frame,
            fg_color="transparent",
        )
        row.pack(
            fill="x",
            padx=8,
            pady=2,
        )

        button = ctk.CTkButton(
            row,
            text=f"{icon}  {file_path.name}",
            anchor="w",
            height=34,
            corner_radius=8,
            fg_color=(
                "gray80",
                "gray25",
            ),
            text_color=(
                "gray10",
                "gray90",
            ),
            hover_color=(
                "gray70",
                "gray30",
            ),
            command=lambda: self._open_file(
                file_path
            ),
        )
        button.pack(
            anchor="w",
            padx=6,
        )

        self._bind_outer_scroll(row)
        self._bind_outer_scroll(button)

        self._scroll_bottom()

    @staticmethod
    def _open_file(path: Path):
        import os

        try:
            # Windows
            os.startfile(str(path))
        except (AttributeError, OSError):
            import webbrowser

            webbrowser.open(
                path.as_uri()
            )

    # ─────────────────────────────────────────────
    # 思考中提示
    # ─────────────────────────────────────────────

    def _add_spinner(self) -> ctk.CTkFrame:
        row = ctk.CTkFrame(
            self.msg_frame,
            fg_color="transparent",
        )
        row.pack(
            fill="x",
            padx=8,
            pady=3,
        )

        bubble = ctk.CTkFrame(
            row,
            fg_color=(
                "gray82",
                "gray22",
            ),
            corner_radius=14,
        )
        bubble.pack(
            anchor="w",
            padx=6,
        )
        
        image_path = Path(__file__).parent / "assets" / "icon_agent_thinking.png"
        
        self.thinking_icon = ctk.CTkImage(
            light_image=Image.open(image_path),
            dark_image=Image.open(image_path),
            size=(48, 48),
        )

        label = ctk.CTkLabel(
            bubble,
            text="  思考中…",
            image=self.thinking_icon,
            compound="left",
            text_color="gray",
        )
        label.pack(
            padx=14,
            pady=8,
        )

        self._bind_outer_scroll(row)
        self._bind_outer_scroll(bubble)
        self._bind_outer_scroll(label)

        self._scroll_bottom()

        return row

    # ─────────────────────────────────────────────
    # 系統訊息
    # ─────────────────────────────────────────────

    def _add_system(self, text: str, image=None):
        label = ctk.CTkLabel(
            self.msg_frame,
            text=text,
            image=image,
            compound="left",  # 圖片顯示在文字左側
            text_color="gray",
            font=ctk.CTkFont(size=14),
            wraplength=520,
        )
        label.pack(
            pady=12,
        )
    
        self._bind_outer_scroll(label)
        self._scroll_bottom()

    # ─────────────────────────────────────────────
    # 自動捲動到底部
    # ─────────────────────────────────────────────

    def _cancel_scroll_jobs(self):
        """取消尚未執行的捲動工作，避免切換對話後套用舊位置。"""

        for job_id in self._scroll_jobs:
            try:
                self.after_cancel(job_id)
            except Exception:
                pass

        self._scroll_jobs.clear()

    def _refresh_scrollregion(self):
        """強制更新 CTkScrollableFrame 內部 Canvas 的內容範圍。"""

        canvas = self.msg_frame._parent_canvas

        self.update_idletasks()
        self.msg_frame.update_idletasks()
        canvas.update_idletasks()

        content_box = canvas.bbox("all")

        if content_box is not None:
            canvas.configure(scrollregion=content_box)

        return canvas

    def _scroll_bottom(self, force: bool = False, delay: int = 0):
        """
        等待訊息元件完成尺寸計算後，更新 scrollregion 並捲動到底部。

        對話紀錄重建期間，個別訊息不觸發捲動；全部建立完成後，
        由 render_history() 使用 force=True 統一處理。
        """

        if self._rendering_history and not force:
            return

        self._cancel_scroll_jobs()

        generation = self._render_generation

        # CustomTkinter 可能分數個事件循環才完成內部 Canvas 尺寸更新。
        # 多階段重算可避免必須縮放視窗或手動拉 scrollbar 才顯示。
        delays = (delay, delay + 35, delay + 100, delay + 220)

        def perform_scroll(expected_generation=generation):
            if expected_generation != self._render_generation:
                return

            try:
                canvas = self._refresh_scrollregion()
                canvas.yview_moveto(1.0)
            except Exception:
                log.exception("無法將對話區捲動到底部")

        for milliseconds in delays:
            job_id = self.after(milliseconds, perform_scroll)
            self._scroll_jobs.append(job_id)

    # ─────────────────────────────────────────────
    # Session 載入與重置
    # ─────────────────────────────────────────────

    def reset(self):
        """清空訊息區並開始新對話。"""

        self._render_generation += 1
        self._cancel_scroll_jobs()
        self._rendering_history = True

        try:
            for widget in self.msg_frame.winfo_children():
                widget.destroy()

            self._pending_files = []
            self.attach_bar.configure(text="")
            self._update_attachment_bar()

            # 先讓舊元件的刪除反映到 Canvas。
            self.update_idletasks()
            self.msg_frame.update_idletasks()

            self._add_system("新對話開始。")
        finally:
            self._rendering_history = False

        self._scroll_bottom(force=True, delay=30)

    def render_history(
        self,
        history: list[dict],
    ):
        """將載入的 session 歷史完整重建成訊息泡泡。"""

        self._render_generation += 1
        self._cancel_scroll_jobs()
        self._rendering_history = True

        try:
            canvas = self.msg_frame._parent_canvas

            # 清除舊對話。
            for widget in self.msg_frame.winfo_children():
                widget.destroy()

            # 立即清除舊 scrollregion，避免新對話沿用前一個對話高度。
            self.update_idletasks()
            self.msg_frame.update_idletasks()
            canvas.update_idletasks()
            canvas.configure(scrollregion=(0, 0, 0, 0))
            canvas.yview_moveto(0.0)

            # 建立新對話。重建期間 _scroll_bottom() 會被抑制，
            # 避免每則訊息排入一個尚未完成尺寸計算的捲動工作。
            for message in history:
                role = message.get("role", "")

                text = self._content_text(
                    message.get("content", "")
                )

                if not text:
                    continue

                bubble_role = (
                    "user"
                    if role == "user"
                    else "assistant"
                )

                self._add_bubble(text, bubble_role)

                if role == "assistant":
                    # 回覆中的圖片或文件路徑若仍存在，重新顯示。
                    for line in text.splitlines():
                        line = line.strip()

                        if line.startswith("🖼️"):
                            path = Path(
                                line.lstrip("🖼️").strip()
                            )

                            if path.exists():
                                self._add_image(path)

                        elif line.startswith("📄"):
                            path = Path(
                                line.lstrip("📄").strip()
                            )

                            if path.exists():
                                self._add_file_link(path)

            # 先完成一次完整版面配置。
            self.update_idletasks()
            self.msg_frame.update_idletasks()
            canvas.update_idletasks()

        finally:
            self._rendering_history = False

        # 全部訊息建立完成後，再分階段更新 scrollregion 並捲到底部。
        self._scroll_bottom(force=True, delay=30)

    @staticmethod
    def _content_text(content) -> str:
        if isinstance(content, str):
            return content

        parts = []

        for part in content:
            if not isinstance(part, dict):
                continue

            content_type = part.get("type")

            if content_type in (
                "input_text",
                "text",
            ):
                parts.append(
                    part.get(
                        "text",
                        "",
                    )
                )

            elif content_type in (
                "image_url",
                "input_image",
            ):
                parts.append(
                    "📎 [圖片附件]"
                )

        return "\n".join(parts)

    # ─────────────────────────────────────────────
    # App callbacks
    # ─────────────────────────────────────────────

    def on_agent_ready(self):
        
        icon_path = Path(__file__).parent / "assets" / "icon_agent_check.png"
        
        self.check_icon = ctk.CTkImage(
            light_image=Image.open(icon_path),
            dark_image=Image.open(icon_path),
            size=(56, 56),
        )
        
        self._add_system(
            "    已連線，開始對話吧！",
            image=self.check_icon,
        )

        # 登入完成後再抓一次即時模型列表（啟動時可能尚未登入）
        self._fetch_models_async()

    def on_show(self):
        self._sync_chat_options()
        self.input.focus_set()
        
