# Copyright (c) 2026 Andy Yeh
# SPDX-License-Identifier: Apache-2.0
"""
BDD Step Definitions — 測試報告整合模組 (report_viewer.feature)

All steps test via HTTP API — no browser automation required.
Browser-interaction steps are mapped to equivalent API/filesystem checks.
"""
from pathlib import Path
import httpx
from behave import given, when, then, step


# ── Background ────────────────────────────────────────────────────────────────

@given("後端服務已正常運行")
def step_backend_running(context):
    resp = httpx.get(f"{context.base_url}/health", timeout=10)
    assert resp.status_code == 200, f"Health check failed: {resp.status_code}"


@given('目錄 "tests/bdd/reports" 存在')
def step_reports_dir_exists(context):
    assert Path("tests/bdd/reports").exists(), \
        "Directory tests/bdd/reports does not exist"


# ── When / Then — reports list ────────────────────────────────────────────────

@when('使用者開啟「報告」分頁')
def step_open_reports_tab(context):
    """Simulate opening the Reports tab — calls the same API the frontend uses."""
    context.response = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)


@step('系統呼叫 GET "/api/robot/reports"')
def step_call_reports_api(context):
    """Make (or verify) the reports API call."""
    if not hasattr(context, "response") or context.response is None:
        context.response = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    assert context.response.status_code == 200, \
        f"Expected 200, got {context.response.status_code}"


@then('回應的 "reports" 欄位為陣列')
def step_reports_is_array(context):
    data = context.response.json()
    assert isinstance(data.get("reports"), list), \
        f"'reports' is not a list: {data}"


@then('每筆紀錄包含 "name", "report_path", "log_path", "modified" 欄位')
def step_record_has_required_fields(context):
    data = context.response.json()
    required = ("name", "report_path", "log_path", "modified")
    for record in data.get("reports", []):
        for field in required:
            assert field in record, \
                f"Missing field '{field}' in record: {list(record.keys())}"


# ── Given — scenarios requiring specific report files ─────────────────────────

@given('已有一筆包含 "output.xml" 的執行紀錄')
def step_has_report_with_output_xml(context):
    """Find a report where output.xml was parsed (passed/failed fields present)."""
    resp = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    reports = resp.json().get("reports", [])
    context.target_report = next(
        (r for r in reports if r.get("passed") is not None),
        None,
    )
    if context.target_report is None:
        context.scenario.skip("No reports with parsed output.xml found — skipping")


@given('已有一筆包含 "report.html" 的執行紀錄')
def step_has_report_html(context):
    resp = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    reports = resp.json().get("reports", [])
    context.target_report = next(
        (r for r in reports if r.get("report_path")),
        None,
    )
    if context.target_report is None:
        context.scenario.skip("No reports with report.html found — skipping")


@given('已有一筆包含 "log.html" 的執行紀錄')
def step_has_log_html(context):
    resp = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    reports = resp.json().get("reports", [])
    context.target_report = next(
        (r for r in reports if r.get("log_path")),
        None,
    )
    if context.target_report is None:
        context.scenario.skip("No reports with log.html found — skipping")


@given('已有一筆包含 "allure-report/index.html" 的執行紀錄')
def step_has_allure_report(context):
    resp = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    reports = resp.json().get("reports", [])
    context.target_report = next(
        (r for r in reports if r.get("allure_path")),
        None,
    )
    if context.target_report is None:
        context.scenario.skip("No reports with allure-report/index.html found — skipping")


# ── Then — stats fields ───────────────────────────────────────────────────────

@then('對應紀錄的 "passed" 與 "failed" 欄位為整數')
def step_passed_failed_are_int(context):
    r = context.target_report
    assert isinstance(r.get("passed"), int), f"'passed' not int: {r}"
    assert isinstance(r.get("failed"), int), f"'failed' not int: {r}"


@then('"elapsed_s" 欄位為浮點數')
def step_elapsed_s_is_float(context):
    r = context.target_report
    assert isinstance(r.get("elapsed_s"), (int, float)), \
        f"'elapsed_s' not numeric: {r}"


# ── When / Then — clicking report links ──────────────────────────────────────

@when('使用者點擊「HTML Report」連結')
def step_click_html_report(context):
    path = context.target_report["report_path"]
    context.clicked_url = f"/reports/{path}"
    context.response = httpx.get(
        f"{context.base_url}/reports/{path}", timeout=10
    )


@when('使用者點擊「Full Log」連結')
def step_click_full_log(context):
    path = context.target_report["log_path"]
    context.clicked_url = f"/reports/{path}"
    context.response = httpx.get(
        f"{context.base_url}/reports/{path}", timeout=10
    )


@when('使用者點擊「Allure 報告」連結')
def step_click_allure_report(context):
    path = context.target_report["allure_path"]
    context.clicked_url = f"/reports/{path}"
    context.response = httpx.get(
        f"{context.base_url}/reports/{path}", timeout=10
    )


@then('瀏覽器開啟 "/reports/{run_name}/report.html"')
def step_browser_opens_report_html(context, run_name):
    assert context.clicked_url.endswith("report.html"), \
        f"Expected URL ending with report.html, got: {context.clicked_url}"


@then('瀏覽器開啟 "/reports/{run_name}/log.html"')
def step_browser_opens_log_html(context, run_name):
    assert context.clicked_url.endswith("log.html"), \
        f"Expected URL ending with log.html, got: {context.clicked_url}"


@then('瀏覽器開啟 "/reports/{run_name}/allure-report/index.html"')
def step_browser_opens_allure(context, run_name):
    assert "allure-report" in context.clicked_url, \
        f"Expected allure-report in URL, got: {context.clicked_url}"
    assert context.clicked_url.endswith("index.html"), \
        f"Expected URL ending with index.html, got: {context.clicked_url}"


@then('HTTP 回應狀態碼為 200')
def step_http_status_200(context):
    assert context.response.status_code == 200, \
        f"Expected 200, got {context.response.status_code}\n{context.response.text[:200]}"


@then('對應紀錄的 "allure_path" 欄位不為 null')
def step_allure_path_not_null(context):
    assert context.target_report.get("allure_path") is not None, \
        f"allure_path is null in: {context.target_report}"


# ── Allure auto-generation scenario ──────────────────────────────────────────

@given('使用者已在「手動挑選」或「CI 預設套件」觸發一次測試執行')
def step_triggered_test_run(context):
    """Verify at least one completed run with allure-results exists."""
    resp = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    reports = resp.json().get("reports", [])
    context.target_report = next(
        (r for r in reports if r.get("allure_path")),
        None,
    )
    if context.target_report is None:
        context.scenario.skip("No completed run with allure output found — skipping")


@when('測試執行完畢')
def step_test_run_completed(context):
    """Confirm the target report was previously completed (allure_path present)."""
    assert context.target_report is not None


@then('系統在執行目錄下生成 "allure-results/" 資料夾')
def step_allure_results_exists(context):
    run_name = context.target_report["name"]
    allure_dir = Path("tests/bdd/reports") / run_name / "allure-results"
    assert allure_dir.exists(), f"allure-results/ not found at {allure_dir}"


@then('系統自動執行 "allure generate" 產生 "allure-report/index.html"')
def step_allure_report_generated(context):
    allure_path = context.target_report.get("allure_path")
    assert allure_path is not None, "allure_path is null — allure generate may have failed"
    full_path = Path("tests/bdd/reports") / allure_path
    assert full_path.exists(), f"allure-report/index.html not found at {full_path}"


# ── Empty state scenario ──────────────────────────────────────────────────────

@given('"tests/bdd/reports" 目錄下尚無任何執行紀錄')
def step_no_reports_exist(context):
    resp = httpx.get(f"{context.base_url}/api/robot/reports", timeout=10)
    reports = resp.json().get("reports", [])
    if reports:
        context.scenario.skip(
            f"{len(reports)} report(s) exist — cannot test empty state without cleanup"
        )
    context.response = resp


@then('頁面顯示「尚無報告。執行測試套件後報告將顯示於此。」')
def step_empty_state_message(context):
    """Verify the portal HTML contains the empty-state element."""
    resp = httpx.get(f"{context.base_url}/", timeout=10)
    assert 'report-empty' in resp.text or '尚無報告' in resp.text, \
        "Empty state element not found in portal HTML"
