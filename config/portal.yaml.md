# config/portal.yaml 參數說明

這是 OpenBMC AI-BDD Portal 的**唯一主設定檔**。所有服務行為、路徑、計時器、QEMU preset 均在此集中設定。

修改後需重啟 uvicorn 才生效（QEMU presets 除外，可透過 `/api/qemu/presets/reload` 熱載入）。

---

## 讀取機制

`backend/core/config.py` 透過 `_y()` helper 讀取本檔，並對應到 `Settings` class 的各欄位：

```python
# 範例：讀取 qemu.default_memory，不存在時回傳 "1G"
_y("qemu", "default_memory", default="1G")
```

`Settings` 在 server 啟動時被 import 並初始化一次；若有需要覆蓋（CI/CD），可在 `.env` 設定同名環境變數（優先級高於 portal.yaml）。

---

## `server` 區塊

```yaml
server:
  host:  "0.0.0.0"
  port:  8080
  debug: true
```

| 參數 | Settings 欄位 | 說明 |
|------|--------------|------|
| `host` | `settings.app_host` | uvicorn 綁定的 IP。`0.0.0.0` 接受所有介面；改為 `127.0.0.1` 可限制僅本機存取 |
| `port` | `settings.app_port` | uvicorn 監聽埠。`scripts/start.sh` 啟動腳本使用此值 |
| `debug` | `settings.app_debug` | FastAPI debug 模式。`true` 時啟用詳細 traceback；正式部署建議改為 `false` |

---

## `openbmc` 區塊

```yaml
openbmc:
  workspace:        "/home/your-user/workspace/openbmc"
  machine:          "ast2700-default"
  robot_script_dir: "/home/your-user/workspace/openbmc-test-automation"
```

### `workspace`

- **Settings 欄位**: `settings.openbmc_workspace`（型別：`Path`）
- **用途**: OpenBMC 的 bitbake build 根目錄。服務層會以此為基礎自動衍生以下兩個路徑：

  | 衍生路徑 | 計算方式 | 用途 |
  |---------|---------|------|
  | `upstream_workspace` | `{workspace}/build/{machine}` | QEMU build 目錄根 |
  | `qemu_image_dir` | `{workspace}/build/{machine}/tmp/deploy/images/{machine}` | 掃描 `.mtd` firmware image 的位置 |

- **使用端點**: `GET /api/qemu/images`、`GET /api/qemu/machines`

### `machine`

- **Settings 欄位**: `settings.machine`
- **用途**: 計算 `upstream_workspace` 和 `qemu_image_dir` 的預設 machine 名稱；也作為 QEMU launch 的 fallback machine
- **注意**: 這是系統層面的預設值，不影響 preset 和 UI 表單中個別指定的 machine

### `robot_script_dir`

- **Settings 欄位**: `settings.robot_script_dir`（型別：`Path`）
- **用途**: `openbmc-test-automation` repository 的 clone 路徑
- **使用位置**:

  | API 端點 | 用途 |
  |---------|------|
  | `GET /api/robot/suites` | 掃描此目錄下所有 `.robot` 檔案 |
  | `GET /api/robot/categorized` | 依目錄結構分類測試案例，回傳 `robot_dir` 欄位 |
  | `GET /api/robot/test-lists` | 掃描 `{robot_script_dir}/test_lists/*.yaml`，回傳 CI 套件定義 |
  | `POST /api/robot/run` | 以此目錄為 base 路徑，執行 `robot -d ... {suite}` |

---

## `qemu` 區塊

### 計時器參數

```yaml
qemu:
  run_timer:    3600
  login_timer:  180
  boot_timeout: 300
```

| 參數 | Settings 欄位 | 說明 |
|------|--------------|------|
| `run_timer` | `settings.qemu_run_timer` | Docker 容器最長存活時間（秒）。超時後容器自動停止，防止殭屍容器持續佔用資源。預設 1 小時。 |
| `login_timer` | `settings.qemu_login_timer` | 等待 BMC 出現 `OPENBMC-READY` log 訊息的最大時間（秒）。超時視為啟動失敗。 |
| `boot_timeout` | `settings.qemu_boot_timeout` | Portal 層面的啟動完成等待逾時（秒），是比 `login_timer` 更外層的 watchdog，防止整個啟動流程卡住。 |

### `default_ports`

```yaml
default_ports:
  ssh:   2222
  https: 2443
  ipmi:  2623
```

- **讀取位置**: `backend/api/routes/qemu.py` 頂層（`_DEF_SSH`、`_DEF_HTTPS`、`_DEF_IPMI`）
- **用途**: QEMU 的 host-side port forwarding 預設值。QEMU guest 側 port 固定（22 / 443 / 623），host 側 port 可調整以避免與系統服務衝突。
- **生成的 QEMU 參數**: `-net nic -net user,hostfwd=tcp::2222-:22,hostfwd=tcp::2443-:443,hostfwd=udp::2623-:623`
- **可覆寫**: `LaunchRequest` model 的 `host_ssh_port` / `host_https_port` / `host_ipmi_port` 欄位，或在各 preset 中個別設定

### `default_memory`

- **Settings 欄位**: `settings.qemu_default_memory`（預設 `"1G"`）
- **用途**: QEMU `-m` 參數的 fallback 值。各 preset 可用 `memory:` 欄位覆寫（例如 romulus 設 `"256M"`）

### `temp_image_dir`

- **Settings 欄位**: `settings.qemu_temp_image_dir`（預設 `"/tmp"`）
- **用途**: QEMU 啟動前會將 `.mtd` firmware image 複製到此目錄，避免 QEMU 直接寫入 build 目錄的原始 image 檔案

---

## `qemu.presets` 區塊

Preset 是「一鍵啟動設定組合」，點擊前端 Preset 按鈕後，表單欄位會自動填入對應值。

```yaml
presets:
  ast2700-default:
    label:           "ast2700-default (aarch64)"
    machine:         "ast2700a1-evb"
    binary_rel_path: "tmp/work/x86_64-linux/qemu-helper-native/1.0/recipe-sysroot-native/usr/bin/qemu-system-aarch64"
    image:           "obmc-phosphor-image-ast2700-default.static.mtd"
    extra_args:      "-serial mon:stdio -serial null -display none"

  romulus:
    label:           "romulus (arm)"
    machine:         "romulus-bmc"
    memory:          "256M"
    binary_rel_path: "tmp/sysroots/x86_64-linux/usr/bin/qemu-system-arm"
    image:           "obmc-phosphor-image-romulus.static.mtd"
    extra_args:      "-nographic"
    use_docker:      false
```

### Preset 參數說明

| 參數 | 必填 | 說明 |
|------|------|------|
| `label` | 是 | 前端 Preset 按鈕顯示的文字標籤 |
| `machine` | 是 | QEMU `-machine` 參數值（可用 `qemu-system-arm -machine ?` 查看可用名稱） |
| `binary_rel_path` | 是（二擇一）| QEMU 可執行檔相對於 `{workspace}/build/{preset_id}/` 的路徑 |
| `binary_abs_path` | 是（二擇一）| QEMU 可執行檔的完整絕對路徑，優先於 `binary_rel_path`，適合 binary 不在 build 目錄內的情況 |
| `image` | 是 | firmware image 檔名（僅檔名，不含路徑）。服務層在 `qemu_image_dir` 中搜尋此檔案 |
| `memory` | 否 | 覆寫 `default_memory`。未填則沿用 `qemu.default_memory` |
| `extra_args` | 否 | 附加到 QEMU 命令結尾的原始參數字串，直接傳入 subprocess |
| `use_docker` | 否 | 決定此 preset 的 QEMU 是否在 Docker 容器中執行（預設 `true`）|

### `use_docker` 詳細說明

這是 preset 中最重要的開關，決定 QEMU 的執行模式。

#### `use_docker: true`（預設，適用於 ast2700）

適用場景：QEMU binary 由 bitbake 自行編譯，帶有獨立的 sysroot（自包含的 shared library），必須在相容環境的容器中執行。

服務層組裝 `docker run` 命令：
```bash
docker run --rm \
  -e LD_LIBRARY_PATH=/path/to/sysroot/lib \
  -v {workspace}:{workspace} \
  -v {image_path}:/tmp/bmc.mtd \
  crops/poky:ubuntu-22.04 \
  /path/to/qemu-system-aarch64 -machine ast2700a1-evb ...
```

#### `use_docker: false`（適用於 romulus）

適用場景：QEMU binary 是標準 Ubuntu 套件版本（如 `qemu-system-arm`），依賴 Host 系統 `/lib/x86_64-linux-gnu/` 的 shared library（`libpixman`、`libglib` 等）。在容器中執行反而因 library 路徑不同而失敗。

服務層直接用 Host Python 的 `subprocess.Popen()` 執行：
```bash
/path/to/qemu-system-arm -machine romulus-bmc -m 256M -nographic ...
```

---

## `docker` 區塊

```yaml
docker:
  image:          "openbmc/ast2700-robot-qemu:Andy"
  runner_image:   "crops/poky:ubuntu-22.04"
  container_name: "qemu-portal-session"
  socket:         "/var/run/docker.sock"
  build_dir:      "/tmp/openbmc/build"
```

| 參數 | Settings 欄位 | 說明 |
|------|--------------|------|
| `image` | `settings.docker_img_name` | **Robot 測試容器** image。執行 openbmc-test-automation 測試腳本時使用，需預裝 Python、Robot Framework 及相關依賴 |
| `runner_image` | `settings.docker_runner_image` | **QEMU 執行容器** image。`use_docker: true` 的 preset 使用此 image 執行 QEMU binary。`crops/poky` 提供與 bitbake 相容的 Ubuntu 22.04 環境 |
| `container_name` | `settings.docker_container_name` | QEMU 容器的固定名稱。Portal 透過此名稱執行 `docker stop`、`docker inspect` 等生命週期管理，確保同時只有一個 QEMU session 存在 |
| `socket` | `settings.docker_socket` | Docker daemon socket 路徑。非標準安裝時（如 Rootless Docker）可改為 `~/.docker/run/docker.sock` |
| `build_dir` | `settings.obmc_build_dir` | **容器內部**的 build 目錄掛載點。Host 的 `{workspace}/build/` 會掛載到容器的此路徑，讓容器內的 QEMU 可存取 firmware image |

### `image` vs `runner_image` 的差異

| | `image` | `runner_image` |
|-|---------|---------------|
| 用途 | 執行 Robot Framework 測試 | 執行 QEMU binary |
| 需要的套件 | Python、Robot Framework、openbmc-test-automation 依賴 | 與 bitbake sysroot 相容的 libc/glibc |
| 典型 image | 自行 build 的客製 image | `crops/poky:ubuntu-22.04` |

---

## `robot` 區塊

```yaml
robot:
  output_dir:           "tests/bdd/reports"
  log_level:            "INFO"
  run_timeout:          600
  allure_timeout:       120
  cleanup_grace_period: 300
```

| 參數 | Settings 欄位 | 說明 |
|------|--------------|------|
| `output_dir` | `settings.robot_output_dir` | Robot 輸出根目錄。`output.xml`、`log.html`、`report.html` 均寫入此處。`allure_results_dir` 自動衍生為 `{output_dir}/allure-results` |
| `log_level` | `settings.robot_log_level` | Robot `--loglevel` 參數值。`INFO` 為標準；`DEBUG` 顯示所有 keyword 細節；`WARN` 只顯示警告與錯誤 |
| `run_timeout` | `settings.robot_run_timeout` | `asyncio.wait_for()` 的逾時（秒）。整個 Robot run 超過此時間會被強制終止，防止測試卡住不結束 |
| `allure_timeout` | `settings.robot_allure_timeout` | `allure generate` 指令的最長執行時間（秒）。Allure 解析大量 XML 時可能很慢，超時後跳過報告生成 |
| `cleanup_grace_period` | `settings.robot_cleanup_grace_period` | Robot run 結束後，保留 WebSocket log stream 連線的時間（秒）。讓前端能在測試結束後繼續讀取剩餘 log，再清理 run 記錄 |

---

## 自動衍生路徑（無需手動設定）

`config.py` 的 `derive_paths()` model validator 在 `Settings()` 初始化後自動計算，不出現在 portal.yaml：

| 欄位 | 計算方式 |
|------|---------|
| `upstream_workspace` | `{openbmc_workspace}/build/{machine}` |
| `qemu_image_dir` | `{openbmc_workspace}/build/{machine}/tmp/deploy/images/{machine}` |
| `allure_results_dir` | `{robot_output_dir}/allure-results` |

---

## 環境變數完整參考

所有 `portal.yaml` 的設定皆可透過環境變數覆蓋（優先級高於 yaml），適用於 CI/CD pipeline 或多人共用機器的個人覆蓋。環境變數名稱為對應 Settings 欄位的 **UPPER_SNAKE_CASE**，設定於 `.env` 檔或 shell 環境。

### Server

| 環境變數 | 對應 yaml | 預設值 | 說明 |
|---------|-----------|--------|------|
| `APP_HOST` | `server.host` | `0.0.0.0` | 監聽 IP |
| `APP_PORT` | `server.port` | `8080` | 監聽 port |
| `APP_DEBUG` | `server.debug` | `true` | 開啟 debug 模式 |

### OpenBMC

| 環境變數 | 對應 yaml | 預設值 | 說明 |
|---------|-----------|--------|------|
| `OPENBMC_WORKSPACE` | `openbmc.workspace` | `/home/user/workspace/openbmc` | OpenBMC build root |
| `MACHINE` | `openbmc.machine` | `ast2700-default` | 目標機型 |
| `ROBOT_SCRIPT_DIR` | `openbmc.robot_script_dir` | `/path/to/openbmc-test-automation` | Robot 測試腳本目錄 |

### QEMU

| 環境變數 | 對應 yaml | 預設值 | 說明 |
|---------|-----------|--------|------|
| `QEMU_RUN_TIMER` | `qemu.run_timer` | `3600` | QEMU 最長執行秒數 |
| `QEMU_LOGIN_TIMER` | `qemu.login_timer` | `180` | 等待登入逾時（秒）|
| `QEMU_BOOT_TIMEOUT` | `qemu.boot_timeout` | `300` | 等待開機逾時（秒）|
| `QEMU_DEFAULT_MEMORY` | `qemu.default_memory` | `1G` | 預設記憶體大小 |
| `QEMU_TEMP_IMAGE_DIR` | `qemu.temp_image_dir` | `/tmp` | 暫存 image 目錄 |

### Docker

| 環境變數 | 對應 yaml | 預設值 | 說明 |
|---------|-----------|--------|------|
| `DOCKER_IMG_NAME` | `docker.image` | `openbmc/ast2700-robot-qemu:your-tag` | QEMU Docker image |
| `DOCKER_SOCKET` | `docker.socket` | `/var/run/docker.sock` | Docker socket 路徑 |
| `OBMC_BUILD_DIR` | `docker.build_dir` | `/tmp/openbmc/build` | 容器內 build 目錄掛載點 |
| `DOCKER_RUNNER_IMAGE` | `docker.runner_image` | `crops/poky:ubuntu-22.04` | Robot 執行用 Docker image |
| `DOCKER_CONTAINER_NAME` | `docker.container_name` | `qemu-portal-session` | QEMU 容器名稱 |

### Robot Framework

| 環境變數 | 對應 yaml | 預設值 | 說明 |
|---------|-----------|--------|------|
| `ROBOT_OUTPUT_DIR` | `robot.output_dir` | `tests/bdd/reports` | 測試報告輸出根目錄 |
| `ROBOT_LOG_LEVEL` | `robot.log_level` | `INFO` | Robot `--loglevel` 參數值 |
| `ROBOT_RUN_TIMEOUT` | `robot.run_timeout` | `600` | Robot run 最長逾時（秒）|
| `ROBOT_ALLURE_TIMEOUT` | `robot.allure_timeout` | `120` | `allure generate` 逾時（秒）|
| `ROBOT_CLEANUP_GRACE_PERIOD` | `robot.cleanup_grace_period` | `300` | WebSocket log stream 保留時間（秒）|

### 衍生路徑（可直接覆蓋）

| 環境變數 | 預設計算方式 | 說明 |
|---------|------------|------|
| `UPSTREAM_WORKSPACE` | `{openbmc_workspace}/build/{machine}` | OpenBMC upstream build 目錄 |
| `QEMU_IMAGE_DIR` | `{openbmc_workspace}/build/{machine}/tmp/deploy/images/{machine}` | QEMU image 搜尋目錄 |
| `ALLURE_RESULTS_DIR` | `{robot_output_dir}/allure-results` | Allure 原始結果目錄 |

---

## 常見修改情境

### 新增一個 QEMU preset

在 `qemu.presets` 下新增 key（preset ID），填入必要欄位：

```yaml
qemu:
  presets:
    my-machine:
      label:           "My Machine (armv7)"
      machine:         "my-machine-bmc"
      binary_rel_path: "tmp/sysroots/x86_64-linux/usr/bin/qemu-system-arm"
      image:           "obmc-phosphor-image-my-machine.static.mtd"
      extra_args:      "-nographic"
      use_docker:      false
```

新增後透過 `POST /api/qemu/presets/reload` 熱載入，無需重啟 server。

### 切換 OpenBMC workspace 路徑

只需修改 `openbmc.workspace`，`qemu_image_dir` 和 `upstream_workspace` 會自動重新計算。

### 調整 Robot 執行逾時

若測試套件需要超過 10 分鐘，增加 `robot.run_timeout`：
```yaml
robot:
  run_timeout: 1800  # 30 分鐘
```
