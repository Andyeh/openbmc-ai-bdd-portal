Feature: Robot Framework 解析與調度模組
  作為 OpenBMC 測試工程師
  我希望能透過 Portal 瀏覽、篩選並執行 openbmc-test-automation 中的 Robot 腳本
  以便在 QEMU 環境上快速調度自動化測試，並即時觀察執行進度與報告

  Background:
    Given the Portal backend is running and healthy
    And the Robot script directory is configured at "/home/andyeh/workspace/ci_test_area/openbmc-test-automation"

  # ─────────────────────────────────────────────────────────────────────
  # Scenario 1 — 目錄掃描與樹狀結構回傳
  # ─────────────────────────────────────────────────────────────────────
  Scenario: 系統能正確掃描目錄並以樹狀 JSON 格式回傳 .robot 檔案分類
    Given the openbmc-test-automation directory exists and contains .robot files
    When the user sends a GET request to "/api/robot/tree"
    Then the response status should be 200
    And the response should contain a "tree" field with a list of category nodes
    And each category node should have "name", "path", and "children" fields
    And the "children" field should contain .robot file entries with "name" and "path"
    And top-level categories should include known directories like "redfish", "network", "pldm"

  Scenario: 當目錄不存在時，樹狀 API 應回傳空列表而非錯誤
    Given the robot script directory path is set to a non-existent path
    When the user sends a GET request to "/api/robot/tree?root=/tmp/__nonexistent_bdd_test__"
    Then the response status should be 200
    And the "tree" field should be an empty list

  Scenario: 樹狀結構應正確反映子目錄的巢狀層級
    Given the openbmc-test-automation directory exists and contains .robot files
    When the user sends a GET request to "/api/robot/tree"
    Then directories with sub-directories should appear as nested nodes
    And leaf .robot files should be listed under their parent category node

  # ─────────────────────────────────────────────────────────────────────
  # Scenario 2 — 使用者勾選腳本並觸發測試執行
  # ─────────────────────────────────────────────────────────────────────
  Scenario: 使用者選擇單一腳本並帶入 OPENBMC_HOST 等參數後成功觸發測試
    Given the openbmc-test-automation directory exists and contains .robot files
    And the user has selected the suite "redfish/extended/test_basic_ci.robot"
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["redfish/extended/test_basic_ci.robot"],
        "variables": {
          "OPENBMC_HOST": "192.168.7.2",
          "OPENBMC_PASSWORD": "0penBmc",
          "OPENBMC_USERNAME": "root"
        },
        "dry_run": true
      }
      """
    Then the response status should be 200
    And the response body should contain "ok" equal to true
    And the response body should contain a "command" field when dry_run is true
    And the command should include "robot"
    And the command should include "OPENBMC_HOST:192.168.7.2"
    And the command should include "OPENBMC_PASSWORD:0penBmc"

  Scenario: 使用者依類別勾選整個目錄下所有腳本後觸發批次測試
    Given the openbmc-test-automation directory exists and contains .robot files
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["network"],
        "variables": {
          "OPENBMC_HOST": "192.168.7.2",
          "OPENBMC_PASSWORD": "0penBmc"
        },
        "dry_run": true
      }
      """
    Then the response status should be 200
    And the response body should contain "ok" equal to true
    And the command should include "network"

  Scenario: 當指定的腳本路徑不存在時，後端應回傳清楚的錯誤訊息
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["non_existent/missing.robot"],
        "variables": {},
        "dry_run": false
      }
      """
    Then the response status should be 200
    And the response body should contain "ok" equal to false
    And the response body should contain an "error" field

  Scenario: 缺少 OPENBMC_HOST 參數時，系統仍可以 dry_run 模式組出指令
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["redfish/extended/test_basic_ci.robot"],
        "variables": {},
        "dry_run": true
      }
      """
    Then the response status should be 200
    And the response body should contain "ok" equal to true
    And the command should include "robot"

  # ─────────────────────────────────────────────────────────────────────
  # Scenario 3 — 即時日誌 WebSocket 串流
  # ─────────────────────────────────────────────────────────────────────
  Scenario: 測試執行期間前端能透過 WebSocket 接收即時 stdout 日誌
    Given a Robot test run has been started with a valid run_id
    When the client connects to the WebSocket endpoint "/api/robot/ws/logs/{run_id}"
    Then the WebSocket connection should be accepted
    And the client should receive log messages as the test progresses

  Scenario: 測試完成後 WebSocket 應自動關閉並回傳 exit code
    Given a Robot test run has been started with a valid run_id
    When the test run completes
    Then the WebSocket should send a final JSON message containing "returncode"
    And the WebSocket connection should close gracefully

  # ─────────────────────────────────────────────────────────────────────
  # Scenario 4 — 安全性驗證
  # ─────────────────────────────────────────────────────────────────────
  Scenario: 包含路徑穿越序列的腳本路徑應被拒絕
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["../../etc/passwd"],
        "variables": {},
        "dry_run": false
      }
      """
    Then the response status should be 400
    And the response body should contain an "error" field

  Scenario: 含有 shell injection 的變數值應被過濾或拒絕
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["redfish/dmtf/test_dmtf_tools.robot"],
        "variables": {
          "OPENBMC_HOST": "192.168.7.2; rm -rf /"
        },
        "dry_run": true
      }
      """
    Then the response status should be 400
    And the response body should contain an "error" field
