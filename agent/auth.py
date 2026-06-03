"""API key 管理：優先從 macOS Keychain 讀取，fallback 到環境變數。"""
import json
import os
from pathlib import Path

import keyring
from openai import AsyncOpenAI

KEYCHAIN_SERVICE = "my-agent"
KEYCHAIN_USERNAME = "openai-api-key"
CONFIG_PATH = Path.home() / ".my-agent" / "config.json"


# ── 儲存 / 讀取 ───────────────────────────────────

def save_api_key(api_key: str) -> None:
    keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_USERNAME, api_key)


def load_api_key() -> str | None:
    # 1. macOS Keychain
    key = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_USERNAME)
    if key:
        return key
    # 2. 環境變數（.env 或 shell export）
    return os.getenv("OPENAI_API_KEY")


def delete_api_key() -> None:
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass


# ── 設定檔（model 等非敏感設定）────────────────────

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


# ── OpenAI client ────────────────────────────────

def get_openai_client() -> AsyncOpenAI:
    api_key = load_api_key()
    if not api_key:
        raise EnvironmentError(
            "找不到 OpenAI API Key。\n"
            "請先執行：python main.py setup"
        )
    return AsyncOpenAI(api_key=api_key)


def get_model() -> str:
    cfg = load_config()
    return cfg.get("model") or os.getenv("OPENAI_MODEL", "gpt-4o")
