"""設定頁面：模型選擇、system prompt。"""
import threading

import customtkinter as ctk

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
        self._models = list(MODELS)   # 先用內建列表，背景抓到即時列表後再更新
        self.grid_columnconfigure(0, weight=1)
        self._build()
        self._fetch_models()

    def _build(self):
        ctk.CTkLabel(
            self, text="設定",
            font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=0, column=0, padx=30, pady=(28, 6), sticky="w")

        card = ctk.CTkFrame(self)
        card.grid(row=1, column=0, padx=30, pady=10, sticky="ew")
        card.grid_columnconfigure(1, weight=1)

        # 模型
        ctk.CTkLabel(card, text="模型", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 6), sticky="w"
        )
        self.model_var = ctk.StringVar()
        self.model_menu = ctk.CTkOptionMenu(
            card, values=self._models, variable=self.model_var, width=220
        )
        self.model_menu.grid(row=0, column=1, padx=20, pady=(20, 6), sticky="w")

        # 推理強度
        ctk.CTkLabel(card, text="推理強度", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=20, pady=(10, 6), sticky="w"
        )
        self.reasoning_var = ctk.StringVar()
        self.reasoning_menu = ctk.CTkOptionMenu(
            card, values=[r[1] for r in REASONING],
            variable=self.reasoning_var, width=320,
        )
        self.reasoning_menu.grid(row=1, column=1, padx=20, pady=(10, 6), sticky="w")

        # System prompt
        ctk.CTkLabel(card, text="System Prompt", font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=20, pady=(10, 6), sticky="nw"
        )
        self.prompt_box = ctk.CTkTextbox(card, height=120, wrap="word")
        self.prompt_box.grid(row=2, column=1, padx=20, pady=(10, 6), sticky="ew")

        # 儲存
        ctk.CTkButton(
            card, text="儲存", command=self._save, width=100
        ).grid(row=3, column=1, padx=20, pady=(6, 20), sticky="e")

        self._load()

    def _load(self):
        from agent.auth import load_config, get_model
        cfg = load_config()
        model = cfg.get("model") or get_model()
        if model not in self._models:
            self._models.append(model)
            self.model_menu.configure(values=self._models)
        self.model_var.set(model)

        effort = cfg.get("reasoning_effort", "medium")
        label  = next((r[1] for r in REASONING if r[0] == effort), REASONING[0][1])
        self.reasoning_var.set(label)

        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", cfg.get("system_prompt", "You are a helpful assistant."))

    def _save(self):
        from agent.auth import load_config, save_config
        cfg = load_config()
        cfg["model"]           = self.model_var.get()
        cfg["system_prompt"]   = self.prompt_box.get("1.0", "end-1c").strip()
        label = self.reasoning_var.get()
        cfg["reasoning_effort"] = next((r[0] for r in REASONING if r[1] == label), "medium")
        save_config(cfg)

        if self.app.agent:
            self.app.agent.model           = cfg["model"]
            self.app.agent.system_prompt   = cfg["system_prompt"]
            self.app.agent.reasoning_effort = cfg["reasoning_effort"]

        ctk.CTkButton(self, text="✓ 已儲存", state="disabled",
                      fg_color="green", width=100).place(x=0, y=0)
        self.after(1500, lambda: None)  # 簡單的視覺回饋

    def _fetch_models(self):
        """背景抓取後端即時模型列表；失敗或未登入時維持內建列表。"""
        def worker():
            from agent.auth import fetch_available_models
            models = fetch_available_models()
            if models:
                try:
                    self.after(0, lambda: self._apply_models(models))
                except Exception:
                    pass   # 視窗已關閉
        threading.Thread(target=worker, daemon=True).start()

    def _apply_models(self, models):
        current = self.model_var.get()
        if current and current not in models:
            models = models + [current]
        self._models = models
        self.model_menu.configure(values=self._models)

    def on_show(self):
        self._load()
