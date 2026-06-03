"""OpenAI OAuth 2.0 PKCE flow + API key fallback."""
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
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

TOKEN_PATH = Path.home() / ".my-agent" / "token.json"


class OpenAIOAuth:
    AUTH_URL = "https://auth.openai.com/authorize"
    TOKEN_URL = "https://auth.openai.com/oauth/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:8899/callback",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    # ── PKCE helpers ──────────────────────────────

    def _pkce_pair(self) -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = urlsafe_b64encode(digest).rstrip(b"=").decode()
        return verifier, challenge

    # ── Token persistence ─────────────────────────

    def _load_token(self) -> dict | None:
        if not TOKEN_PATH.exists():
            return None
        token = json.loads(TOKEN_PATH.read_text())
        if token.get("expires_at", 0) > time.time() + 60:
            return token
        return self._try_refresh(token)

    def _save_token(self, token: dict) -> None:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        if "expires_in" in token and "expires_at" not in token:
            token["expires_at"] = time.time() + token["expires_in"]
        TOKEN_PATH.write_text(json.dumps(token, indent=2))

    def _try_refresh(self, token: dict) -> dict | None:
        refresh = token.get("refresh_token")
        if not refresh:
            return None
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh,
            },
        )
        if resp.status_code != 200:
            return None
        new_token = {**token, **resp.json()}
        self._save_token(new_token)
        return new_token

    # ── Main auth flow ────────────────────────────

    def authenticate(self) -> str:
        """Return a valid access token, running browser OAuth if needed."""
        token = self._load_token()
        if token:
            return token["access_token"]

        verifier, challenge = self._pkce_pair()
        state = secrets.token_urlsafe(16)

        auth_url = self.AUTH_URL + "?" + urlencode({
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "openid",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        })

        code = self._browser_callback(auth_url)
        token = self._exchange(code, verifier)
        self._save_token(token)
        return token["access_token"]

    def _browser_callback(self, auth_url: str) -> str:
        """Spin up local server, open browser, wait for code."""
        bucket: dict = {}
        app = FastAPI()

        @app.get("/callback")
        async def callback(code: str):
            bucket["code"] = code
            return HTMLResponse(
                "<h1 style='font-family:sans-serif'>認證成功！請關閉此視窗。</h1>"
            )

        config = uvicorn.Config(app, host="localhost", port=8899, log_level="error")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        print("\n[OAuth] 開啟瀏覽器登入 OpenAI…")
        webbrowser.open(auth_url)

        for _ in range(300):
            if "code" in bucket:
                server.should_exit = True
                return bucket["code"]
            time.sleep(1)
        raise TimeoutError("OAuth 認證逾時（5 分鐘）")

    def _exchange(self, code: str, verifier: str) -> dict:
        resp = httpx.post(
            self.TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "code_verifier": verifier,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def revoke(self) -> None:
        """清除本地 token 快取。"""
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()


def get_openai_client():
    """建立 OpenAI client：優先 OAuth，次選 API key。"""
    from openai import AsyncOpenAI

    client_id = os.getenv("OPENAI_CLIENT_ID")
    api_key = os.getenv("OPENAI_API_KEY")

    if client_id:
        oauth = OpenAIOAuth(
            client_id=client_id,
            client_secret=os.environ["OPENAI_CLIENT_SECRET"],
            redirect_uri=os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8899/callback"),
        )
        token = oauth.authenticate()
        return AsyncOpenAI(api_key=token)

    if api_key:
        return AsyncOpenAI(api_key=api_key)

    raise EnvironmentError(
        "需要設定 OPENAI_CLIENT_ID 或 OPENAI_API_KEY（見 .env.example）"
    )
