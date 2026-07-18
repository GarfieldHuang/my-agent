"""設定頁面：system prompt。（模型與推理強度改在 Chat 頁選擇）"""
import customtkinter as ctk

# Chat 頁選單使用的內建預設清單；登入後會由後端即時列表更新。
MODELS = ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini"]
REASONING = [
    ("medium", "Medium（預設，平衡速度與深度）"),
    ("high",   "High（更深入，較慢）"),
    ("xhigh",  "XHigh（最深，僅 gpt-5.4+ 支援）"),
    ("low",    "Low（快速，淺層思考）"),
    ("none",   "關閉（不推理，直接回答）"),
]


class SettingsView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        ctk.CTkLabel(
            self, text="設定",
            font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, padx=30, pady=(28, 6), sticky="w")

        card = ctk.CTkFrame(self)
        card.grid(row=1, column=0, padx=30, pady=10, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # System prompt
        ctk.CTkLabel(card, text="System Prompt", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 6), sticky="nw"
        )
        self.prompt_box = ctk.CTkTextbox(card, height=120, wrap="word")
        self.prompt_box.grid(row=0, column=1, padx=20, pady=(20, 6), sticky="ew")

        # 模型 / 推理強度改到 Chat 頁選擇
        ctk.CTkLabel(
            card,
            text="模型與推理強度請在 Chat 頁下方的選單選擇。",
            text_color="gray", font=ctk.CTkFont(size=12),
        ).grid(row=1, column=1, padx=20, pady=(0, 6), sticky="w")

        # 儲存
        ctk.CTkButton(
            card, text="儲存", command=self._save, width=100
        ).grid(row=2, column=1, padx=20, pady=(6, 20), sticky="e")

        self._load()

    def _load(self):
        from agent.auth import load_config
        cfg = load_config()
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", cfg.get("system_prompt", "You are a helpful assistant."))

    def _save(self):
        from agent.auth import load_config, save_config
        cfg = load_config()
        cfg["system_prompt"] = self.prompt_box.get("1.0", "end-1c").strip()
        save_config(cfg)

        if self.app.agent:
            self.app.agent.system_prompt = cfg["system_prompt"]

        ctk.CTkButton(self, text="✓ 已儲存", state="disabled",
                      fg_color="green", width=100).place(x=0, y=0)
        self.after(1500, lambda: None)  # 簡單的視覺回饋

    def on_show(self):
        self._load()
