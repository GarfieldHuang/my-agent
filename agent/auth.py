"""OpenAI OAuth 2.0 PKCE — 用 ChatGPT 帳號登入，不需要 API Key。"""
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from base64 import urlsafe_b64encode
from pathlib import Path
from urllib.parse import urlencode

import httpx
import keyring
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

KEYCHAIN_SERVICE = "my-agent"
KEYCHAIN_KEY = "openai-token"
CONFIG_PATH = Path.home() / ".my-agent" / "config.json"

AUTH_URL = "https://auth.openai.com/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:8899/callback"


# ── PKCE helpers ──────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── Token 存取（存在 macOS Keychain）─────────────

def _save_token(token: dict) -> None:
    if "expires_in" in token and "expires_at" not in token:
        token["expires_at"] = time.time() + token["expires_in"]
    keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY, json.dumps(token))


def _load_token() -> dict | None:
    raw = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY)
    return json.loads(raw) if raw else None


def _is_expired(token: dict) -> bool:
    return token.get("expires_at", 0) < time.time() + 60


def _try_refresh(token: dict, client_id: str) -> dict | None:
    refresh = token.get("refresh_token")
    if not refresh:
        return None
    try:
        data = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh,
        }
        # 如果有 client_secret（非公開 client），也一起帶上
        secret = os.getenv("OPENAI_CLIENT_SECRET")
        if secret:
            data["client_secret"] = secret

        resp = httpx.post(TOKEN_URL, data=data, timeout=10)
        if resp.status_code == 200:
            new_token = {**token, **resp.json()}
            _save_token(new_token)
            return new_token
    except Exception:
        pass
    return None


# ── 瀏覽器 OAuth 流程 ─────────────────────────────

def _browser_oauth(client_id: str) -> dict:
    """開瀏覽器讓用戶登入 OpenAI，回傳 token dict。"""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = AUTH_URL + "?" + urlencode(params)

    # 本機 callback server
    bucket: dict = {}
    app = FastAPI()

    @app.get("/callback")
    async def callback(code: str, state: str = ""):
        bucket["code"] = code
        return HTMLResponse(
            "<h1 style='font-family:sans-serif;text-align:center;padding-top:20vh;color:#10a37f'>"
            "✓ 認證成功！請關閉此視窗回到終端機。</h1>"
        )

    server = uvicorn.Server(uvicorn.Config(app, host="localhost", port=8899, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    print("\n[Auth] 開啟瀏覽器，請用你的 OpenAI 帳號登入…")
    webbrowser.open(auth_url)

    for _ in range(300):
        if "code" in bucket:
            server.should_exit = True
            break
        time.sleep(1)
    else:
        raise TimeoutError("OAuth 認證逾時（5 分鐘）")

    # 交換 token
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": bucket["code"],
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    secret = os.getenv("OPENAI_CLIENT_SECRET")
    if secret:
        data["client_secret"] = secret

    resp = httpx.post(TOKEN_URL, data=data, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ── 主要 API ──────────────────────────────────────

def get_access_token() -> str:
    """取得有效 access token；必要時開瀏覽器重新登入。"""
    client_id = os.getenv("OPENAI_CLIENT_ID")
    if not client_id:
        raise EnvironmentError(
            "未設定 OPENAI_CLIENT_ID。\n"
            "請複製 .env.example → .env 並填入 client_id。\n"
            "申請網址：https://platform.openai.com/settings/organization/apps"
        )

    token = _load_token()

    if token and not _is_expired(token):
        return token["access_token"]

    if token:
        refreshed = _try_refresh(token, client_id)
        if refreshed:
            return refreshed["access_token"]

    # 需要重新登入
    token = _browser_oauth(client_id)
    _save_token(token)
    print("[Auth] ✓ 登入成功，token 已存入 Keychain。\n")
    return token["access_token"]


def get_openai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=get_access_token())


def logout() -> None:
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY)
        print("✓ 已登出。")
    except Exception:
        print("（沒有找到已儲存的登入資訊）")


def get_model() -> str:
    cfg = load_config()
    return cfg.get("model") or os.getenv("OPENAI_MODEL", "gpt-4o")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
