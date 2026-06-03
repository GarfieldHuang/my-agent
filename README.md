# My Agent

個人 AI Agent，用你的 **OpenAI 帳號直接登入**，不需要管理 API Key。

## 功能

- **OpenAI OAuth 登入** — 第一次執行自動開瀏覽器，用你的 ChatGPT 帳號授權，token 自動存入 macOS Keychain
- **MCP 工具掛載** — 設定任意 MCP server，tools 自動整合到 agent
- **檔案上傳** — 圖片（vision）、PDF、程式碼等，用 `/file` 指令附加
- **對話記憶** — 同一 session 保留完整歷史，`/clear` 重置

---

## 安裝

**前置需求：** Python 3.11+

```bash
git clone https://github.com/GarfieldHuang/my-agent.git
cd my-agent
pip install -r requirements.txt
```

---

## 首次設定（只需一次）

### Step 1：建立 OAuth App（repo 作者做一次）

> 如果你只是安裝別人的 agent，跳到 Step 2。

1. 前往 [platform.openai.com/settings/organization/apps](https://platform.openai.com/settings/organization/apps)
2. 建立新的 OAuth App
3. Redirect URI 填：`http://localhost:8899/callback`
4. 複製 **Client ID**

### Step 2：設定 .env

```bash
cp .env.example .env
```

編輯 `.env`，填入 Client ID：

```env
OPENAI_CLIENT_ID=your_client_id_here
```

> **注意：** Client ID 不是密碼，可以放進 repo 公開分享。每個安裝這個 agent 的人共用同一個 Client ID，但各自用自己的帳號登入。

### Step 3：啟動

```bash
python main.py
```

第一次執行會自動開啟瀏覽器 → 用你的 OpenAI 帳號登入 → 授權 → 回到終端機。之後 token 存在 Keychain，不需要再登入。

---

## 指令

| 命令 | 說明 |
|------|------|
| `python main.py` | 啟動 agent（未登入自動觸發 OAuth） |
| `python main.py setup` | 設定精靈（重新登入、換模型、設定 MCP） |
| `python main.py logout` | 登出（清除 Keychain token） |
| `python main.py --system "..."` | 自訂 system prompt 啟動 |

### 對話中的斜線指令

| 指令 | 說明 |
|------|------|
| `/file <路徑>` | 附加檔案到下一則訊息 |
| `/clear` | 清除對話歷史 |
| `/logout` | 登出並離開 |
| `/quit` | 離開 |

---

## 設定 MCP 工具（可選）

執行 `python main.py setup` 可用問答方式新增，或直接編輯 `mcp_config.yaml`：

```yaml
servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
```

---

## 專案結構

```
my-agent/
├── agent/
│   ├── auth.py          # OpenAI OAuth PKCE 流程 + Keychain 儲存
│   ├── wizard.py        # 互動式設定精靈
│   ├── mcp_manager.py   # MCP server 管理
│   ├── files.py         # 檔案上傳
│   └── core.py          # Agent loop
├── main.py              # CLI 入口
├── mcp_config.yaml      # MCP 設定
├── .env.example         # 設定範本
└── requirements.txt
```

---

## 常見問題

**Q: 想換帳號登入？**
```bash
python main.py logout
python main.py
```

**Q: Token 失效或出現認證錯誤？**
```bash
python main.py logout
python main.py
```

**Q: 想換模型（例如 gpt-4o-mini）？**
```bash
python main.py setup   # 選 ② 模型
```
