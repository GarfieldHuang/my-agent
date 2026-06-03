# My Agent

個人 AI Agent，支援 macOS Keychain 安全儲存、MCP 工具掛載、檔案上傳。

## 功能

- **互動式 Setup Wizard** — `python main.py setup` 問答式完成所有設定，不用摸任何設定檔
- **macOS Keychain 儲存** — API Key 存在系統 Keychain，不寫進任何文字檔或 `.env`
- **MCP 工具掛載** — wizard 直接新增 MCP server，tools 自動合併到 agent
- **檔案上傳** — 圖片轉 base64 vision、文件走 OpenAI Files API，用 `/file` 指令附加
- **對話記憶** — 同一 session 內保留完整歷史，`/clear` 重置

---

## 安裝

**前置需求：** Python 3.11+

```bash
# 1. clone repo
git clone https://github.com/GarfieldHuang/my-agent.git
cd my-agent

# 2. 安裝依賴
pip install -r requirements.txt
```

---

## 首次設定

```bash
python main.py setup
```

Wizard 會依序問你三件事：

```
① OpenAI API Key
   → 輸入後自動驗證，存入 macOS Keychain（不寫入任何檔案）
   → 取得 Key：https://platform.openai.com/api-keys

② 預設模型
   1. gpt-4o（最強）
   2. gpt-4o-mini（省錢）
   3. gpt-4-turbo
   4. o1-mini（推理型）
   5. 自訂

③ MCP 工具（可略過）
   → 互動新增 stdio / SSE MCP server
```

設定完成後直接執行：

```bash
python main.py
```

---

## 指令總覽

| 命令 | 說明 |
|------|------|
| `python main.py` | 啟動 agent |
| `python main.py setup` | 重新執行設定精靈（可隨時重新設定） |
| `python main.py reset` | 清除所有設定（API Key + config） |
| `python main.py --system "..."` | 自訂 system prompt 啟動 |

### 對話中可用的斜線指令

| 指令 | 說明 |
|------|------|
| `/file <路徑>` | 附加檔案到下一則訊息（圖片、PDF、程式碼等） |
| `/clear` | 清除對話歷史 |
| `/quit` | 離開 |

---

## 附加檔案範例

```
You> /file ~/Desktop/screenshot.png
✓ 已附加：/Users/xxx/Desktop/screenshot.png

You> 這張圖片裡有什麼？
```

---

## 手動新增 MCP 工具

除了 wizard，也可以直接編輯 `mcp_config.yaml`：

```yaml
servers:
  # 本機檔案系統（需先安裝 Node.js）
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

## 專案結構

```
my-agent/
├── agent/
│   ├── auth.py          # API Key 管理（macOS Keychain + env fallback）
│   ├── wizard.py        # 互動式設定精靈
│   ├── mcp_manager.py   # 多 MCP server 管理，tools 自動合併
│   ├── files.py         # 檔案上傳（圖片 base64 / Files API）
│   └── core.py          # Agent loop（tool call 處理）
├── main.py              # CLI 入口（setup / reset / chat）
├── mcp_config.yaml      # MCP servers 設定
├── requirements.txt
└── .env.example         # 備用：也支援環境變數 OPENAI_API_KEY
```

設定存放位置：

```
~/.my-agent/
└── config.json    # 模型等非敏感設定

macOS Keychain
└── my-agent / openai-api-key    # API Key（加密儲存）
```

---

## 常見問題

**Q: 想換 API Key 或模型？**
```bash
python main.py setup
```
直接重跑 wizard，選「要換新的 Key」即可。

**Q: 想完全重來？**
```bash
python main.py reset
```

**Q: MCP server 啟動失敗？**

先單獨測試指令能否執行：
```bash
npx -y @modelcontextprotocol/server-filesystem /tmp
```

**Q: 不想用 Keychain，想用環境變數？**

在 `.env` 加入：
```env
OPENAI_API_KEY=sk-...
```
agent 會自動 fallback 讀取環境變數。
