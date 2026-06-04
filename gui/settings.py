"""設定頁面：模型選擇、system prompt。"""
import customtkinter as ctk

MODELS = ["gpt-5.5", "gpt-5.5-pro", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-pro", "gpt-5.3-codex"]


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

        # 模型
        ctk.CTkLabel(card, text="模型", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 6), sticky="w"
        )
        self.model_var = ctk.StringVar()
        self.model_menu = ctk.CTkOptionMenu(
            card, values=MODELS, variable=self.model_var, width=200
        )
        self.model_menu.grid(row=0, column=1, padx=20, pady=(20, 6), sticky="w")

        # System prompt
        ctk.CTkLabel(card, text="System Prompt", font=ctk.CTkFont(weight="bold")).grid(
            row=1, column=0, padx=20, pady=(10, 6), sticky="nw"
        )
        self.prompt_box = ctk.CTkTextbox(card, height=140, wrap="word")
        self.prompt_box.grid(row=1, column=1, padx=20, pady=(10, 6), sticky="ew")

        # 儲存
        ctk.CTkButton(
            card, text="儲存", command=self._save, width=100
        ).grid(row=2, column=1, padx=20, pady=(6, 20), sticky="e")

        self._load()

    def _load(self):
        from agent.auth import load_config, get_model
        cfg = load_config()
        model = cfg.get("model") or get_model()
        if model not in MODELS:
            MODELS.append(model)
            self.model_menu.configure(values=MODELS)
        self.model_var.set(model)
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", cfg.get("system_prompt", "You are a helpful assistant."))

    def _save(self):
        from agent.auth import load_config, save_config
        cfg = load_config()
        cfg["model"]         = self.model_var.get()
        cfg["system_prompt"] = self.prompt_box.get("1.0", "end-1c").strip()
        save_config(cfg)

        # 更新 agent 的 model 與 system prompt（不需重啟）
        if self.app.agent:
            self.app.agent.model         = cfg["model"]
            self.app.agent.system_prompt = cfg["system_prompt"]

        ctk.CTkButton(self, text="✓ 已儲存", state="disabled",
                      fg_color="green", width=100).place(x=0, y=0)
        self.after(1500, lambda: None)  # 簡單的視覺回饋

    def on_show(self):
        self._load()
