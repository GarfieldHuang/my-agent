"""OpenAI OAuth 2.0 PKCE — 用 ChatGPT 帳號（Plus/Pro）登入，不需要 API Key。

技術細節參考自 openclaw/openclaw 的 openai-codex provider 實作。
"""
import base64
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

import certifi
import httpx
import keyring

# ── SSL：優先用 OS 系統憑證庫（支援公司 proxy CA）──
# truststore 讓 Python 讀 Windows/macOS/Linux 的系統憑證庫，
# 跟瀏覽器用同一套 CA，公司 MITM proxy 就能過。
try:
    import truststore
    truststore.inject_into_ssl()
    _SSL_VERIFY = True          # truststore 已接管，用預設即可
except ImportError:
    _SSL_VERIFY = certifi.where()   # fallback：Mozilla CA bundle
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

# ── OAuth 設定 ────────────────────────────────────
# 預設使用 openclaw 的 OAuth App（無需自行申請即可使用）。
# 若要換成自己的 App，在 .env 設定 OPENAI_CLIENT_ID。

DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

AUTH_URL     = "https://auth.openai.com/oauth/authorize"
TOKEN_URL    = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"   # 必須跟 client_id 登記的一致
SCOPE        = "openid profile email offline_access"

KEYCHAIN_SERVICE = "my-agent"
KEYCHAIN_KEY     = "openai-token"
CONFIG_PATH  = Path.home() / ".my-agent" / "config.json"
TOKEN_FILE   = Path.home() / ".my-agent" / "token.json"   # keyring fallback


# ── PKCE ─────────────────────────────────────────

def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ── JWT 解析（不驗簽，只讀 payload）─────────────

def _decode_jwt_payload(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (4 - len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


def _extract_account_id(access_token: str) -> str | None:
    payload = _decode_jwt_payload(access_token)
    auth = payload.get("https://api.openai.com/auth", {})
    return auth.get("chatgpt_account_id")


# ── Token 儲存（Keychain 優先，失敗 fallback 到檔案）──
# Windows Credential Manager 有 2500 bytes 限制，JWT token 容易超過；
# 公司 group policy 也可能禁止寫入。失敗時改存 ~/.my-agent/token.json。

def _save_token(token: dict) -> None:
    if "expires_in" in token and "expires_at" not in token:
        token["expires_at"] = time.time() + token["expires_in"]
    data = json.dumps(token)
    try:
        keyring.set_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY, data)
    except Exception:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(data, encoding="utf-8")


def _load_token() -> dict | None:
    # 1. Keychain
    try:
        raw = keyring.get_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY)
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    # 2. 檔案 fallback
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _is_expired(token: dict) -> bool:
    return token.get("expires_at", 0) < time.time() + 60


def _try_refresh(token: dict, client_id: str) -> dict | None:
    refresh = token.get("refresh_token")
    if not refresh:
        return None
    try:
        resp = httpx.post(TOKEN_URL, data={
            "grant_type":    "refresh_token",
            "client_id":     client_id,
            "refresh_token": refresh,
        }, timeout=10, verify=_SSL_VERIFY)
        if resp.status_code == 200:
            new_token = {**token, **resp.json()}
            _save_token(new_token)
            return new_token
    except Exception:
        pass
    return None


# ── 瀏覽器 OAuth 流程 ─────────────────────────────

def _browser_oauth(client_id: str) -> dict:
    """開瀏覽器讓用戶用 ChatGPT 帳號授權，回傳 token dict。"""
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_url = AUTH_URL + "?" + urlencode({
        "response_type":              "code",
        "client_id":                  client_id,
        "redirect_uri":               REDIRECT_URI,
        "scope":                      SCOPE,
        "state":                      state,
        "code_challenge":             challenge,
        "code_challenge_method":      "S256",
        # OpenAI 專用參數（參考 openclaw 實作）
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow":  "true",
        "originator":                 "my-agent",
    })

    bucket: dict = {}
    app = FastAPI()

    @app.get("/auth/callback")
    async def callback(code: str, state: str = ""):
        bucket["code"] = code
        return HTMLResponse(
            "<h1 style='font-family:sans-serif;text-align:center;"
            "padding-top:20vh;color:#10a37f'>"
            "✓ 認證成功！請關閉此視窗回到終端機。</h1>"
        )

    server = uvicorn.Server(uvicorn.Config(app, host="localhost", port=1455, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 嘗試開啟瀏覽器；在遠端/VPS 環境可能失敗
    opened = webbrowser.open(auth_url)

    if opened:
        print("\n[Auth] 瀏覽器已開啟，請用你的 ChatGPT 帳號（Plus/Pro）登入並授權…")
    else:
        print("\n[Auth] 無法自動開啟瀏覽器，請手動複製以下網址：")
    print(f"\n  {auth_url}\n")
    print("[Auth] 授權完成後會自動繼續，請勿關閉此視窗。")

    # 等待 callback（15 秒後提示可手動貼 redirect URL，仿 openclaw 行為）
    for i in range(300):
        if "code" in bucket:
            server.should_exit = True
            break
        if i == 15 and not opened:
            redirect_url = input(
                "\n[Auth] 登入後請貼上瀏覽器跳轉的完整 redirect URL：\n> "
            ).strip()
            from urllib.parse import urlparse, parse_qs
            parsed = parse_qs(urlparse(redirect_url).query)
            if "code" in parsed:
                bucket["code"] = parsed["code"][0]
                server.should_exit = True
                break
        time.sleep(1)
    else:
        server.should_exit = True
        raise TimeoutError("OAuth 認證逾時（5 分鐘）")

    resp = httpx.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     client_id,
        "code":          bucket["code"],
        "redirect_uri":  REDIRECT_URI,
        "code_verifier": verifier,
    }, timeout=10, verify=_SSL_VERIFY)
    resp.raise_for_status()
    return resp.json()


# ── 主要 API ──────────────────────────────────────

def get_access_token() -> str:
    """取得有效 access token；必要時開瀏覽器重新登入。"""
    client_id = os.getenv("OPENAI_CLIENT_ID") or DEFAULT_CLIENT_ID

    token = _load_token()

    if token and not _is_expired(token):
        return token["access_token"]

    if token:
        refreshed = _try_refresh(token, client_id)
        if refreshed:
            return refreshed["access_token"]

    token = _browser_oauth(client_id)
    _save_token(token)
    print("[Auth] ✓ 登入成功！\n")
    return token["access_token"]


def get_openai_client():
    """建立 OpenAI client，帶上 ChatGPT OAuth 所需的 headers。"""
    from openai import AsyncOpenAI

    access_token = get_access_token()
    account_id = _extract_account_id(access_token)

    extra_headers = {"originator": "my-agent"}
    if account_id:
        extra_headers["chatgpt-account-id"] = account_id

    return AsyncOpenAI(
        api_key=access_token,
        default_headers=extra_headers,
    )


def logout() -> None:
    cleared = False
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, KEYCHAIN_KEY)
        cleared = True
    except Exception:
        pass
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        cleared = True
    print("✓ 已登出。" if cleared else "（沒有找到已儲存的登入資訊）")


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
