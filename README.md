# My Agent

個人 AI Agent，支援 OpenAI OAuth 認證、MCP 工具掛載、檔案上傳。

## 功能

- **OpenAI OAuth 2.0 PKCE** — 瀏覽器登入一次，token 自動刷新，不用把 API key 存在 `.env`
- **MCP 工具掛載** — 在 `mcp_config.yaml` 設定任意 MCP server，tools 自動合併到 agent
- **檔案上傳** — 圖片轉 base64 vision、文件走 OpenAI Files API，用 `/file` 指令附加
- **對話記憶** — 同一 session 內保留完整歷史，`/clear` 重置

---

## 安裝

### 前置需求

- Python 3.11+
- `pip`

### 步驟

```bash
# 1. clone repo
git clone https://github.com/GarfieldHuang/my-agent.git
cd my-agent

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 建立設定檔
cp .env.example .env
```

---

## 設定

編輯 `.env`，二選一：

### 選項 A：API Key（快速開始）

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

### 選項 B：OAuth（不存 key，更安全）

1. 前往 [platform.openai.com/settings/organization/apps](https://platform.openai.com/settings/organization/apps) 建立 OAuth app
2. Redirect URI 填 `http://localhost:8899/callback`
3. 複製 Client ID / Client Secret 填入 `.env`：

```env
OPENAI_CLIENT_ID=your_client_id
OPENAI_CLIENT_SECRET=your_client_secret
OPENAI_MODEL=gpt-4o
OAUTH_REDIRECT_URI=http://localhost:8899/callback
```

### 掛載 MCP 工具（可選）

編輯 `mcp_config.yaml`，範例：

```yaml
servers:
  # 本機檔案系統
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

  # 自己的 Python MCP server
  my-tools:
    transport: stdio
    command: python
    args: ["my_mcp_server.py"]

  # 遠端 SSE server
  remote:
    transport: sse
    url: http://localhost:3001/sse
```

---

## 啟動

```bash
python main.py
```

首次使用 OAuth 模式時，會自動開啟瀏覽器進行登入，之後 token 存在 `~/.my-agent/token.json`，不需要再登入。

### 自訂 system prompt

```bash
python main.py --system "你是一個繁體中文助理，回覆要簡潔。"
```

---

## CLI 指令

| 指令 | 說明 |
|------|------|
| `/file <路徑>` | 附加檔案到下一則訊息（圖片、PDF、程式碼等） |
| `/clear` | 清除對話歷史 |
| `/quit` | 離開 |

### 附加檔案範例

```
You> /file ~/Desktop/screenshot.png
✓ 已附加：/Users/xxx/Desktop/screenshot.png

You> 這張圖片裡有什麼？
```

---

## 專案結構

```
my-agent/
├── agent/
│   ├── auth.py          # OpenAI OAuth 2.0 PKCE flow
│   ├── mcp_manager.py   # 多 MCP server 管理，tools 自動合併
│   ├── files.py         # 檔案上傳（圖片 base64 / Files API）
│   └── core.py          # Agent loop（tool call 處理）
├── main.py              # CLI 入口
├── mcp_config.yaml      # MCP servers 設定
├── requirements.txt
└── .env.example
```

---

## 常見問題

**Q: OAuth token 壞掉或想重新登入？**
```bash
rm ~/.my-agent/token.json
python main.py
```

**Q: MCP server 啟動失敗？**

確認指令可以獨立執行，例如：
```bash
npx -y @modelcontextprotocol/server-filesystem /tmp
```

**Q: 想換模型？**

在 `.env` 修改：
```env
OPENAI_MODEL=gpt-4o-mini
```
