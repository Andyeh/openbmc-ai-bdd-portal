# ⚡ OpenBMC AI-BDD Portal

> **基於 FastAPI & Behave BDD 的 OpenBMC QEMU 模擬與自動化測試管理平台**

OpenBMC AI-BDD Portal 是一款專為 OpenBMC 開發與測試設計的 Web 控制平台。整合了 **QEMU 模擬器生命週期管理**、**Robot Framework 測試套件排程執行** 與 **Behave 行為驅動開發 (BDD) 測試架構**，並能即時透過 WebSocket 串流執行日誌與生成 Allure 測試報告。

---

## 🌟 核心特色

- 🖥️ **Web 控制面板**：直觀的主頁面，一鍵啟動/停止 QEMU 模擬器，並即時監控狀態。
- 🧪 **自動化測試排程**：整合 OpenBMC 官方的 Robot Framework 測試指令，快速發起測試。
- 📊 **BDD 測試架構**：採用 `behave` 框架編寫 Behavior-Driven Development 測試，將測試情境自然語言化。
- 📈 **Allure 測試報告**：整合 `allure-behave`，測試完成後可一鍵產出豐富精美的互動式圖表報告。
- 🔄 **即時日誌串流**：利用 WebSocket 技術，將後端執行過程與 Robot 輸出即時推送到前端網頁。
- ⚙️ **完整的 API 文件**：基於 FastAPI 自動生成的 Swagger UI (`/api/docs`) 與 ReDoc (`/api/redoc`)。

---

## 📂 專案目錄結構

```text
openbmc-ai-bdd-portal/
├── backend/                  # FastAPI 後端主程式
│   ├── api/                  # API 路由與控制器
│   │   └── routes/           # qemu.py (模擬器管理), robot.py (測試執行)
│   ├── core/                 # 系統核心設定 (Pydantic Settings)
│   └── main.py               # 後端應用程式入口
├── frontend/                 # 前端靜態網頁與範本
│   ├── static/               # CSS, JS, 圖片等靜態資源
│   └── templates/            # Jinja2 HTML 模板 (主控制面板)
├── scripts/                  # 運維與自動化腳本
│   ├── start.sh              # 專案環境初始化與啟動腳本
│   └── run_bdd.sh            # 執行 Behave BDD 測試腳本
├── tests/                    # 測試套件
│   └── bdd/                  # BDD 測試相關檔案
│       ├── features/         # behave feature 描述檔 (.feature)
│       └── reports/          # 測試報告輸出目錄 (含 allure-results)
├── .env.example              # 環境變數範本檔
├── behave.ini                # Behave 測試組態檔
└── requirements.txt          # Python 依賴套件清單
```

---

## 🚀 快速開始

### 1. 系統需求
- Python 3.8+
- Docker (若要執行容器化 QEMU 模擬)
- Allure Commandline (用以產生與預覽測試報告)

### 2. 建立 Python 虛擬環境

建議使用虛擬環境隔離專案依賴，避免與系統 Python 套件衝突。

```bash
# 建立虛擬環境
python3 -m venv .venv

# 啟動虛擬環境
source .venv/bin/activate          # Linux / macOS
# .venv\Scripts\activate           # Windows

# 安裝專案依賴
pip install -r requirements.txt
```

若需在 Portal 內執行 openbmc-test-automation 的 Robot 測試腳本，需額外安裝其依賴：

```bash
pip install -r /path/to/openbmc-test-automation/requirements.txt
```

離開虛擬環境：

```bash
deactivate
```

### 3. 一鍵啟動平台
專案已內建自動化啟動腳本 `scripts/start.sh`，會自動建立虛擬環境、安裝依賴，並產生預設環境變數：

```bash
# 賦予腳本執行權限
chmod +x scripts/start.sh scripts/run_bdd.sh

# 啟動平台
./scripts/start.sh
```

啟動後，您可以透過瀏覽器訪問：
- **Web 控制面板**：[http://localhost:8080](http://localhost:8080)
- **API 互動式文件**：[http://localhost:8080/api/docs](http://localhost:8080/api/docs)

### 3. 環境變數配置
啟動後會自動複製 `.env.example` 產生 `.env`。您可以根據實際的 OpenBMC 與 QEMU 路徑進行調整：

```bash
# QEMU 二進位檔路徑與映像檔目錄
QEMU_BINARY=/path/to/your/qemu-system-arm
QEMU_IMAGE_DIR=/path/to/your/deploy/images/romulus
QEMU_DEFAULT_MACHINE=romulus-bmc

# Robot Framework 設定
ROBOT_SCRIPT_DIR=/path/to/openbmc-test-automation
```

---

## 🧪 執行 BDD 測試與報告

您可以透過執行本地 BDD 測試，來驗證 Portal、QEMU 以及 Robot 流程是否正常運作。

### 1. 執行 Behave 測試
```bash
./scripts/run_bdd.sh
```
此腳本會調用 `behave` 框架，並將結果輸出至 `tests/bdd/reports/allure-results/`。

### 2. 檢視 Allure 互動式測試報告
確保本機已安裝 Allure，接著執行以下指令即可自動開啟瀏覽器檢視精美報告：
```bash
allure serve tests/bdd/reports/allure-results
```

---

## 🛠️ 開發與貢獻

1. 建立 Feature 分支 (`git checkout -b feature/AmazingFeature`)
2. 提交您的變更 (`git commit -m 'Add some AmazingFeature'`)
3. 推送到遠端分支 (`git push origin feature/AmazingFeature`)
4. 發起 Pull Request (PR)
