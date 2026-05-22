Feature: 測試報告整合模組 (Robot + Allure)
  作為一位測試工程師
  我希望在測試執行完畢後能在 Portal 查看 Robot 原生報告與 Allure 視覺化報告
  以便追蹤測試歷史與分析失敗原因

  Background:
    Given 後端服務已正常運行
    And 目錄 "tests/bdd/reports" 存在

  Scenario: 報告列表頁面顯示過去的執行紀錄
    When 使用者開啟「報告」分頁
    Then 系統呼叫 GET "/api/robot/reports"
    And 回應的 "reports" 欄位為陣列
    And 每筆紀錄包含 "name", "report_path", "log_path", "modified" 欄位

  Scenario: 報告紀錄附帶通過/失敗統計數字
    Given 已有一筆包含 "output.xml" 的執行紀錄
    When 系統呼叫 GET "/api/robot/reports"
    Then 對應紀錄的 "passed" 與 "failed" 欄位為整數
    And "elapsed_s" 欄位為浮點數

  Scenario: Robot 原生 HTML 報告可直接開啟
    Given 已有一筆包含 "report.html" 的執行紀錄
    When 使用者點擊「HTML Report」連結
    Then 瀏覽器開啟 "/reports/{run_name}/report.html"
    And HTTP 回應狀態碼為 200

  Scenario: Robot 完整 Log 可直接開啟
    Given 已有一筆包含 "log.html" 的執行紀錄
    When 使用者點擊「Full Log」連結
    Then 瀏覽器開啟 "/reports/{run_name}/log.html"
    And HTTP 回應狀態碼為 200

  Scenario: 測試執行後自動生成 Allure 靜態報告
    Given 使用者已在「手動挑選」或「CI 預設套件」觸發一次測試執行
    When 測試執行完畢
    Then 系統在執行目錄下生成 "allure-results/" 資料夾
    And 系統自動執行 "allure generate" 產生 "allure-report/index.html"

  Scenario: Allure 報告透過 Portal 可直接開啟
    Given 已有一筆包含 "allure-report/index.html" 的執行紀錄
    When 系統呼叫 GET "/api/robot/reports"
    Then 對應紀錄的 "allure_path" 欄位不為 null
    When 使用者點擊「Allure 報告」連結
    Then 瀏覽器開啟 "/reports/{run_name}/allure-report/index.html"
    And HTTP 回應狀態碼為 200

  Scenario: 無報告時顯示空狀態提示
    Given "tests/bdd/reports" 目錄下尚無任何執行紀錄
    When 使用者開啟「報告」分頁
    Then 頁面顯示「尚無報告。執行測試套件後報告將顯示於此。」
