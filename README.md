# My Agent

個人 AI Agent，用你的 **ChatGPT 帳號（Plus/Pro）直接登入**，不需要 API Key，不需要任何設定。

## 功能

- **一鍵登入** — 執行後自動開瀏覽器，用 ChatGPT 帳號授權，token 存入 macOS Keychain
- **MCP 工具掛載** — 設定任意 MCP server，tools 自動整合到 agent
- **檔案上傳** — 圖片（vision）、PDF、程式碼，用 `/file` 指令附加
- **對話記憶** — 同一 session 保留完整歷史，`/clear` 重置

---

## 安裝與啟動

**前置需求：** Python 3.11+、ChatGPT Plus / Pro 訂閱

```bash
git clone https://github.com/GarfieldHuang/my-agent.git
cd my-agent
pip install -r requirements.txt
python main.py
```

第一次執行會自動開啟瀏覽器 → 用你的 ChatGPT 帳號登入並授權 → 回到終端機開始使用。

之後每次執行 `python main.py` 就直接進入對話，不需要再登入。

---

## 指令

| 命令 | 說明 |
|------|------|
| `python main.py` | 啟動 agent |
| `python main.py setup` | 設定精靈（重新登入、換模型、設定 MCP 工具） |
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

```bash
python main.py setup   # 選 ③ MCP 工具，用問答方式新增
```

或直接編輯 `mcp_config.yaml`：

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
├── requirements.txt
└── .env.example         # 進階設定（一般使用者不需要）
```

---

## 常見問題

**Q: 想換帳號或 token 失效？**
```bash
python main.py logout
python main.py
```

**Q: 想換模型？**
```bash
python main.py setup
```

**Q: 沒有 ChatGPT Plus/Pro，只有 API Key？**

在 `.env` 加入：
```env
OPENAI_API_KEY=sk-...
```
