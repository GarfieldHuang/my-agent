# My Agent

個人 AI Agent 桌面應用，用你的 **ChatGPT 帳號（Plus/Pro）直接登入**，不需要 API Key。

預設是圖形介面（GUI），也支援純終端機模式。

## 功能

- **一鍵登入** — 執行後自動開瀏覽器，用 ChatGPT 帳號授權，token 存入系統憑證管理員
- **圖形介面** — Chat、MCP 工具、Skills、自動化、Plugins、設定、帳號 七個分頁
- **MCP 工具掛載** — 設定任意 MCP server，tools 自動整合到 agent
- **Skills** — Markdown 寫的技能手冊，模型按需載入
- **Slash Commands / Subagents / Hooks** — 自訂指令、子代理、生命週期掛勾
- **Plugins** — 一個 zip 打包安裝 skills + commands + agents + MCP servers
- **檔案上傳** — 圖片（vision）、PDF、程式碼，可拖放或用 `/file` 指令
- **文件生成** — 產出 Word / PowerPoint / Excel / PDF
- **生圖** — `gpt-image-2`，走 ChatGPT 訂閱配額，支援圖生圖
- **瀏覽器操作** — 內建 Python MCP server，用系統已裝的 Edge/Chrome，不需要 Node.js
- **對話記憶** — 保留 session 歷史，`/clear` 重置

---

## 給一般使用者：免安裝版

不需要 Python、不需要系統管理員權限、安裝時不需要網路。

1. 拿到 `MyAgent-portable.zip`（約 92 MB）
2. 解壓縮到任何自己的資料夾，例如「文件」底下
3. 雙擊 **`start.bat`**

第一次執行會自動開瀏覽器，用 ChatGPT 帳號登入並授權，之後啟動就直接進入。

個人資料（token、設定、對話紀錄、安裝的 skills / plugins）一律放在 `C:\Users\<你的帳號>\.my-agent\`，程式資料夾本身不會被寫入 — 要升級時直接把整個資料夾換成新版即可，設定不會掉。

---

## 給開發者：從原始碼安裝

**前置需求：** Python 3.11+、ChatGPT Plus / Pro 訂閱、Windows

> 不需要系統管理員權限。以下步驟已在乾淨環境實測通過。

```bash
git clone https://github.com/GarfieldHuang/my-agent.git
cd my-agent
py -m venv venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
```

裝完後，之後每次啟動就雙擊 **`start.bat`**（它會用 `venv\Scripts\python.exe` 跑 `main.py`）。

第一次執行會自動開啟瀏覽器 → 用 ChatGPT 帳號登入並授權 → 回到程式開始使用。
之後啟動就直接進入，不需要再登入。

不需要另外跑 `playwright install`：瀏覽器工具直接用系統已安裝的 Edge / Chrome。

### 公司網路裝不起來？

若 `git clone` 出現 `schannel: ... CRYPT_E_NO_REVOCATION_CHECK`，是憑證撤銷檢查被公司 Proxy 擋掉。改用 openssl backend：

```bash
git -c http.sslbackend=openssl clone https://github.com/GarfieldHuang/my-agent.git
```

若連 GitHub 都連不到，改用網頁版 **Code → Download ZIP** 下載後解壓，再從 `py -m venv venv` 那步繼續。

---

## 打包免安裝版發給同事

有兩種打包方式。**預設用可攜版** — 除非確定目標環境沒有信譽式防毒。

### 可攜版（建議）

```bash
venv\Scripts\python.exe build_portable.py
```

產出 `dist\MyAgent-portable.zip`（約 92 MB）。把它放到共用磁碟 / SharePoint，同事解壓後雙擊 `start.bat`。

結構是「官方簽章的 `pythonw.exe` + 原始碼 + 預裝套件」：

```
MyAgent/
├── start.bat     啟動器
├── PORTABLE      給 agent/paths.py 認的標記檔（在 app/ 內）
├── python/       CPython 複本（含 tkinter、tcl/tk）
└── app/          原始碼與內建資源
```

**為什麼不用單一 exe** — PyInstaller 產出的 exe 沒有程式碼簽章，且每次 build 的 hash 都是新的，Symantec Endpoint Protection 之類的信譽式防毒會判為 `Unproven.LowPrevalence` 直接隔離。這不是誤判成惡意程式，是「這個檔案全球沒幾個人跑過」的信譽結論，所以**每次改版都會再中一次**。可攜版實際被執行的是 python.org 官方簽章、全球普及度極高的 `pythonw.exe`，完全繞開這個判定。

用 `pythonw.exe` 而非 `python.exe` 是為了不跳黑窗；代價是 `sys.stdout` / `sys.stderr` 都是 `None`，未捕捉的例外會無聲消失（症狀：雙擊後完全沒反應）。要除錯時改用 `python\python.exe app\main.py` 就看得到錯誤。

### PyInstaller 單一 exe

```bash
build.bat
```

產出 `dist\MyAgent.zip`（約 46 MB），解壓後雙擊 `MyAgent.exe`。體積小一半、啟動是單一執行檔，但會踩上述的防毒信譽問題，只適合已加白名單或沒有信譽式防毒的環境。

設定在 [`MyAgent.spec`](MyAgent.spec)，幾個刻意的選擇：

- **onedir 而非 onefile** — onefile 每次啟動都要解壓到 temp（慢），且防毒誤判率更高
- **關閉 UPX 壓縮** — UPX 是防毒誤判的大宗
- **排除 playwright** — 它會拖進數百 MB 的瀏覽器 driver；瀏覽器 MCP 走外部 python 執行
- **排除 `mcp.cli`** — 它需要 `typer`（不在 requirements 內），掃到會讓 build 直接失敗

### 路徑規則（兩種打包都適用）

見 [`agent/paths.py`](agent/paths.py)：`bundle_dir()` 是隨程式發佈的唯讀資源，`user_dir()`（`~/.my-agent/`）是所有可寫狀態，`is_packaged()` 同時涵蓋 PyInstaller 與可攜版。

**新增會被寫入的檔案時請走 `user_dir()`**，否則打包後會寫進唯讀目錄，或在下次更新時被整包覆蓋。

---

## 啟動方式

| 命令 | 說明 |
|------|------|
| `start.bat` | 啟動 GUI（推薦，雙擊即可） |
| `venv\Scripts\python.exe main.py` | 同上，GUI 模式 |
| `venv\Scripts\python.exe main.py --cli` | 終端機模式 |
| `venv\Scripts\python.exe main.py --cli --system "..."` | 自訂 system prompt 啟動 |
| `venv\Scripts\python.exe main.py setup` | 設定精靈（重新登入、換模型、設定 MCP 工具） |
| `venv\Scripts\python.exe main.py logout` | 登出（清除已儲存的 token） |
| `venv\Scripts\python.exe main.py image "描述"` | 命令列生圖 |

### CLI 模式的斜線指令

| 指令 | 說明 |
|------|------|
| `/file <路徑>` | 附加檔案到下一則訊息 |
| `/image <描述>` | 生圖（先 `/file` 附加圖片即為圖生圖） |
| `/clear` | 清除對話歷史 |
| `/logout` | 登出並離開 |
| `/quit` | 離開 |

---

## 設定 MCP 工具（可選）

GUI 的「MCP 工具」分頁可直接新增設定，或用設定精靈：

```bash
venv\Scripts\python.exe main.py setup   # 選 ③ MCP 工具
```

也可以直接編輯 `mcp_config.yaml`（沒有這個檔時會自動 fallback 到 `mcp_config.example.yaml`）：

```yaml
servers:
  # 本機 stdio server
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

  # 遠端 SSE server
  my-remote:
    transport: sse
    url: http://localhost:3001/sse

  # 瀏覽器操作（純 Python，用系統已裝的 Edge/Chrome）
  browser:
    transport: stdio
    command: python
    args: ["browser_mcp.py"]
```

### 自動注入參數（inject）

有些 MCP server 的工具需要傳入 `api_key` 或其他認證參數。
設定 `inject` 後 agent 會自動帶入，**模型不需要知道、也不會被問到**：

```yaml
servers:
  mssql:
    transport: stdio
    command: python
    args: ["C:\\path\\to\\server.py"]
    inject:
      api_key: your-secret-key-here   # 自動注入，模型看不到這個參數
```

`inject` 的 key 對應工具 schema 裡的參數名稱，支援任意數量。

---

## 專案結構

```
my-agent/
├── agent/
│   ├── paths.py         # 唯讀 bundle 資源 vs 可寫使用者資料
│   ├── auth.py          # OpenAI OAuth PKCE 流程 + token 儲存
│   ├── core.py          # Agent loop
│   ├── mcp_manager.py   # MCP server 管理
│   ├── skills.py        # Skills 載入
│   ├── commands.py      # Slash commands
│   ├── subagents.py     # 子代理
│   ├── hooks.py         # 生命週期掛勾
│   ├── plugins.py       # Plugin 安裝／移除
│   ├── sessions.py      # 對話 session
│   ├── files.py         # 檔案上傳
│   ├── doctools.py      # Word / PPT / Excel / PDF 生成
│   ├── imagegen.py      # 生圖
│   ├── shell.py         # run_command 工具
│   └── wizard.py        # 互動式設定精靈
├── gui/                 # customtkinter 圖形介面（各分頁）
├── skills/              # 內建 skills
├── commands/            # 內建 slash commands
├── agents/              # 內建 subagents
├── browser_mcp.py       # 內建瀏覽器 MCP server
├── main.py              # 入口（GUI 預設，--cli 走終端機）
├── start.bat            # 開發模式啟動捷徑
├── build_portable.py    # 打包可攜版（建議）
├── build.bat            # 打包 PyInstaller 單一 exe
├── MyAgent.spec         # PyInstaller 設定
├── mcp_config.yaml      # MCP 設定（gitignore，不會被 commit）
├── requirements.txt
└── .env.example         # 進階設定（一般使用者不需要）
```

使用者資料放在 `~/.my-agent/`：token、`config.json`、`plugins.json`、`hooks.json`、`sessions/`、`agent.log`（打包版），以及使用者自訂或 plugin 裝入的 `skills/`、`commands/`、`agents/`。打包版的 `mcp_config.yaml` 和 `.env` 也在這裡。

---

## 常見問題

**Q: 想換帳號或 token 失效？**
```bash
venv\Scripts\python.exe main.py logout
start.bat
```

**Q: 想換模型？**
GUI 的「設定」分頁，或 `venv\Scripts\python.exe main.py setup`。

**Q: 沒有 ChatGPT Plus/Pro，只有 API Key？**

在 `.env` 加入（可從 `.env.example` 複製）：
```env
OPENAI_API_KEY=sk-...
```

**Q: 要看詳細的執行紀錄？**

log 預設是 INFO。追查問題時在 `.env` 開 DEBUG：
```env
MY_AGENT_LOG_LEVEL=DEBUG
```
`httpx` / `httpcore` / `openai` 等第三方套件無論如何都壓在 WARNING — 它們在 DEBUG 會把含 OAuth token 與 cookie 的完整 HTTP 標頭寫進 `agent.log`，等於在機器上留下一份憑證明文副本。

**Q: 複雜任務（如瀏覽器操作）跑到一半就停？**

工具呼叫輪數上限預設 10，在 `.env` 調高：
```env
MAX_TOOL_ROUNDS=25
```

**Q: token 存在哪裡？**

優先存入系統憑證管理員（Windows Credential Manager / macOS Keychain），失敗時 fallback 到 `~/.my-agent/token.json`。
