# ⚡ OpenBMC AI-BDD Portal

> **基於 FastAPI & Behave BDD 的 OpenBMC QEMU 模擬與自動化測試管理平台**

OpenBMC AI-BDD Portal 是一款專為 OpenBMC 開發與測試設計的 Web 控制平台。整合了 **QEMU 模擬器生命週期管理**、**Robot Framework 測試套件排程執行** 與 **Behave 行為驅動開發 (BDD) 測試架構**，並能即時透過 WebSocket 串流執行日誌與生成 Allure 測試報告。

---

## 🌟 核心特色

- 🖥️ **Web 控制面板**：直觀的三分頁介面（QEMU / Robot 測試 / 報告），一鍵啟動/停止 QEMU 模擬器
- ⚡ **YAML Preset 系統**：在 `config/portal.yaml` 定義機器預設值，一鍵套用 machine、binary、image、port、memory 等參數
- 🐳 **Docker / Host 雙模式**：QEMU 可在 Docker 容器內或 Host 直接執行，per-preset 可設定
- 🧪 **Robot Framework 整合**：CI 預設套件卡片 + 手動挑選測試案例，支援即時 WebSocket 串流日誌
- 📊 **Allure 報告自動生成**：Robot 執行結束後自動呼叫 `allure generate`，報告頁面可直接開啟
- 🔄 **即時日誌串流**：xterm.js 互動式終端機，QEMU Serial Console 與 Robot 輸出均即時推送
- ⚙️ **API 文件**：FastAPI 自動生成 Swagger UI (`/api/docs`) 與 ReDoc (`/api/redoc`)

---

## 📂 專案目錄結構

```text
openbmc-ai-bdd-portal/
├── backend/                  # FastAPI 後端主程式
│   ├── api/routes/           # qemu.py、robot.py API 路由
│   ├── core/config.py        # 統一設定載入（portal.yaml → Settings）
│   └── services/             # qemu_service.py、robot_service.py 核心邏輯
├── config/
│   ├── portal.yaml           # ★ 唯一需要編輯的設定檔
│   └── portal.yaml.md        # portal.yaml 參數說明文件
├── frontend/
│   ├── static/css/           # style.css
│   ├── static/js/            # app.js
│   └── templates/            # index.html (Jinja2)
├── tests/bdd/
│   ├── features/             # Behave .feature 描述檔
│   └── reports/              # 測試報告輸出（含 allure-results/）
├── scripts/
│   ├── start.sh              # 一鍵啟動腳本
│   └── run_bdd.sh            # 執行 BDD 測試腳本
├── .env.example              # CI/CD 環境變數覆蓋範本（一般使用者不需修改）
└── requirements.txt          # Python 依賴套件
```

---

## 🚀 快速開始

### 1. 系統需求

- Python 3.10+
- Docker（若使用容器化 QEMU，如 ast2700）
- Allure Commandline（用於產生測試報告）

### 2. 建立 Python 虛擬環境

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

若需在 Portal 內執行 openbmc-test-automation 的 Robot 測試腳本，需額外安裝其依賴：

```bash
pip install -r /path/to/openbmc-test-automation/requirements.txt
```

確認 Robot Framework 與必要套件已安裝：

```bash
python3 -m robot --version
pip show allure-robotframework robotframework-requests
```

離開虛擬環境：

```bash
deactivate
```

### 3. 編輯設定檔

**所有設定集中在一個檔案：**

```bash
vim config/portal.yaml
```

主要設定項目：

```yaml
openbmc:
  workspace: "/home/user/workspace/openbmc"   # OpenBMC 根目錄
  machine:   "ast2700-default"                # 預設機器
  robot_script_dir: "/path/to/openbmc-test-automation"

qemu:
  default_ports:
    ssh:   2222
    https: 2443
    ipmi:  2623
  presets:
    ast2700-default:
      label:           "ast2700-default (aarch64)"
      machine:         "ast2700a1-evb"
      binary_rel_path: "tmp/work/x86_64-linux/qemu-helper-native/..."
      image:           "obmc-phosphor-image-ast2700-default.static.mtd"
      extra_args:      "-serial mon:stdio -serial null -display none"
      # use_docker: true (預設)
    romulus:
      label:           "romulus (arm)"
      machine:         "romulus-bmc"
      memory:          "256M"
      binary_rel_path: "tmp/sysroots/x86_64-linux/usr/bin/qemu-system-arm"
      image:           "obmc-phosphor-image-romulus.static.mtd"
      extra_args:      "-nographic"
      use_docker:      false   # 使用 Host Ubuntu 系統庫執行

docker:
  image:   "openbmc/ast2700-robot-qemu:your-tag"  # Robot 測試容器（自行 build 的客製 image）
  runner_image: "crops/poky:ubuntu-22.04"          # QEMU 執行容器
```

> `.env` 僅供 CI/CD 環境變數覆蓋使用，一般使用者只需編輯 `config/portal.yaml`。

### 4. 啟動平台

```bash
source .venv/bin/activate
PYTHONPATH=$(pwd) uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

或使用啟動腳本：

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

啟動後訪問：
- **Web 控制面板**：[http://localhost:8080](http://localhost:8080)
- **API 文件**：[http://localhost:8080/api/docs](http://localhost:8080/api/docs)

---

## 🖥️ QEMU 操作

### Preset 快速套用

點擊「⚡ Preset 按鈕」即可一鍵填入 machine、binary、image、ports、memory 及 Docker 模式設定。

### Docker vs Host 模式

| Preset | 模式 | 說明 |
|--------|------|------|
| ast2700-default | Docker | bitbake 自建 binary，帶獨立 sysroot，放入容器執行 |
| romulus | Host | 標準 Ubuntu 系統套件，依賴 Host 系統庫，不放入容器 |

### 即時 Serial Console

QEMU 啟動後 Terminal 區域會顯示互動式 xterm.js 終端機，可直接鍵入指令與 QEMU Serial Console 互動。

---

## 🤖 Robot Framework 測試

### CI 預設套件

從 `robot_script_dir/test_lists/` 自動掃描 `.yaml` 定義的測試套件。點擊卡片選取後按 **▶ Run** 即時執行並串流日誌。

### 手動挑選測試

瀏覽 `.robot` 測試案例，依類別篩選或搜尋，勾選個別測試後執行。支援 `--test "Name"` 精確指定。

### 執行流程

1. 在「⚙ Robot 執行參數」填入 OPENBMC_HOST、帳密等變數（或點「⚡ 帶入 QEMU 預設值」自動填入）
2. 選擇 CI 套件或手動挑選測試案例
3. 按 **▶ Run** 啟動，切換至「📡 Live Log」觀看即時輸出
4. 執行結束後至「📊 報告」頁面查看結果，支援 HTML Report、Full Log 及 Allure 報告

---

## 🧪 BDD 測試（開發驗證用）

驗證 Portal 本身的 API 與流程是否正常。執行前請確認 Portal 已在 port 8080 啟動。

### 執行全部測試（含 Allure 報告）

```bash
./scripts/run_bdd.sh
```

### 執行單一 Feature 檔

```bash
./scripts/run_bdd.sh tests/bdd/features/system/system_integration.feature
```

### 純 terminal 輸出（不產生 Allure）

```bash
source .venv/bin/activate
PYTHONPATH=$(pwd) python -m behave tests/bdd/features/
```

### 執行單一 Scenario（指定行號）

```bash
source .venv/bin/activate
PYTHONPATH=$(pwd) python -m behave tests/bdd/features/system/system_integration.feature:11
```

### 查看 Allure 報告

```bash
allure serve tests/bdd/reports/allure-results
```

### Feature 涵蓋範圍

| Feature 檔 | 說明 |
|-----------|------|
| `portal/portal_architecture.feature` | 首頁結構、三分頁面板、基本 API |
| `qemu/qemu_runner.feature` | QEMU 啟動/停止/dry-run/WebSocket |
| `robot/robot_runner.feature` | Robot 執行、dry-run、stream-run |
| `report/report_viewer.feature` | 報告列表、HTML/Log/Allure 連結 |
| `system/system_integration.feature` | 例外處理、安全驗證、E2E smoke flow |

---

## 🛠️ 開發

1. 建立 Feature 分支：`git checkout -b feature/AmazingFeature`
2. 提交變更：`git commit -m 'Add some AmazingFeature'`
3. 推送分支：`git push origin feature/AmazingFeature`
4. 發起 Pull Request

## License

Copyright (c) 2026 Andy Yeh. Licensed under the [Apache License 2.0](LICENSE).
