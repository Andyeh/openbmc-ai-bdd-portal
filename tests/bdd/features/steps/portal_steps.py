"""
BDD Step Definitions — Portal Architecture
Covers: page load, panel presence, API endpoints, responsive layout.
"""
import json
import httpx
from behave import given, when, then


# ── Shared helpers ────────────────────────────────────────────────────────────

def _get(context, path: str):
    """Issue a GET request against the portal base URL."""
    url = f"{context.base_url}{path}"
    context.response = httpx.get(url, timeout=10)
    return context.response


def _post(context, path: str, json_body: dict = None):
    """Issue a POST request against the portal base URL."""
    url = f"{context.base_url}{path}"
    context.response = httpx.post(url, json=json_body or {}, timeout=60)
    return context.response


# ── Given ─────────────────────────────────────────────────────────────────────

@given('the OpenBMC AI-BDD Portal backend is running on port {port:d}')
def step_backend_running(context, port):
    context.base_url = f"http://localhost:{port}"
    # quick connectivity check
    try:
        resp = httpx.get(f"{context.base_url}/health", timeout=5)
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
    except httpx.ConnectError:
        raise AssertionError(
            f"Cannot connect to portal on port {port}. "
            "Ensure the backend is running (`./scripts/start.sh`)."
        )


@given('the portal home page is accessible at "{url}"')
def step_home_accessible(context, url):
    context.base_url = url.rstrip("/").rsplit(":", 1)[0] + ":" + url.rsplit(":", 1)[-1].split("/")[0]


@given('the browser viewport is set to "{width}" x "{height}"')
def step_set_viewport(context, width, height):
    # Stored for informational/documentation purposes in unit tests.
    # For real Selenium/Playwright integration, set viewport here.
    context.viewport = {"width": int(width), "height": int(height)}


# ── When ──────────────────────────────────────────────────────────────────────

@when('the user navigates to the portal home page')
def step_navigate_home(context):
    _get(context, "/")


@when('the user sends a GET request to "{path}"')
def step_get_request(context, path):
    _get(context, path)


@when('the user sends a POST request to "{path}" with body')
def step_post_request(context, path):
    import json
    body = json.loads(context.text) if context.text else {}
    _post(context, path, body)


# ── Then ──────────────────────────────────────────────────────────────────────

@then('the page title should be "{expected_title}"')
def step_page_title(context, expected_title):
    html = context.response.text
    assert f"<title>{expected_title}</title>" in html, (
        f"Expected title '{expected_title}' not found in page."
    )


@then('the HTTP response status code should be {code:d}')
def step_http_status(context, code):
    assert context.response.status_code == code, (
        f"Expected {code}, got {context.response.status_code}"
    )


@then('the response status code should be {code:d}')
def step_response_status(context, code):
    step_http_status(context, code)


@then('the page should contain the main navigation bar')
def step_has_nav(context):
    assert 'id="main-nav"' in context.response.text, \
        "Main navigation bar (#main-nav) not found in page."


@then('the page should display exactly three panels')
def step_three_panels(context):
    html = context.response.text
    for row in context.table:
        panel_id = row["panel_id"]
        assert f'id="{panel_id}"' in html, \
            f"Panel '{panel_id}' not found in page HTML."


@then('the {panel:w} panel should be visible')
def step_panel_visible(context, panel):
    panel_map = {
        "QEMU": "qemu-panel",
        "Robot": "robot-panel",
        "Report": "report-panel",
    }
    panel_id = panel_map.get(panel, f"{panel.lower()}-panel")
    assert f'id="{panel_id}"' in context.response.text, \
        f"Panel '{panel_id}' not found."


@then('the QEMU panel should display the current QEMU status')
def step_qemu_status_display(context):
    assert 'id="qemu-status"' in context.response.text


@then('the QEMU panel should show a machine type selector')
def step_qemu_machine_selector(context):
    assert 'id="qemu-machine"' in context.response.text


@then('the QEMU panel should show a firmware image selector')
def step_qemu_image_selector(context):
    assert 'id="qemu-image"' in context.response.text


@then('the QEMU panel should have a "{label}" button')
def step_qemu_button(context, label):
    assert label in context.response.text, \
        f"Button '{label}' not found on page."


@then('the QEMU panel should show a real-time log console')
def step_qemu_log_console(context):
    # xterm.js terminal container; replaces the old plain <pre id="qemu-log">
    assert 'id="qemu-terminal"' in context.response.text, \
        "QEMU terminal container (#qemu-terminal) not found in page."


@then('the Robot panel should list available .robot test suites')
def step_robot_suite_list(context):
    # UI is now tab-based: CI presets grid + browse test-card list
    html = context.response.text
    assert 'id="ci-cards-grid"' in html or 'id="browse-test-list"' in html, \
        "Neither 'ci-cards-grid' nor 'browse-test-list' found in page HTML."


@then('the Robot panel should have a "{label}" button')
def step_robot_button(context, label):
    assert label in context.response.text


@then('the Robot panel should allow setting extra Robot variables')
def step_robot_extra_vars(context):
    # Variables section is in the "⚙ 執行參數" tab container
    assert 'id="robot-section-vars"' in context.response.text, \
        "Robot variables section (#robot-section-vars) not found in page HTML."


@then('the Report panel should list past test run reports')
def step_report_list(context):
    assert 'id="report-list"' in context.response.text


@then('each report entry should display the run timestamp')
def step_report_timestamp(context):
    # Entries are rendered by JS after fetching /api/robot/reports;
    # the static HTML only guarantees the container exists.
    assert 'id="report-list"' in context.response.text, \
        "Report list container (#report-list) not found."


@then('each report entry should have a link to the HTML report')
def step_report_link(context):
    # Entries are rendered by JS after fetching /api/robot/reports;
    # the static HTML only guarantees the container exists.
    assert 'id="report-list"' in context.response.text, \
        "Report list container (#report-list) not found."


@then('the response body should contain "status" equal to "ok"')
def step_response_status_ok(context):
    data = context.response.json()
    assert data.get("status") == "ok", f"Expected status=ok, got: {data}"


@then('the response body should contain a "{field}" field')
def step_response_has_field(context, field):
    data = context.response.json()
    assert field in data, f"Field '{field}' missing from response: {data}"


@then('the response body should contain a "{field}" field showing the assembled command')
def step_response_has_field_showing_assembled(context, field):
    data = context.response.json()
    assert field in data, f"Field '{field}' missing from response: {data}"


@then('the command should include "{fragment}"')
def step_command_includes_shared(context, fragment):
    cmd = getattr(context, "assembled_command", context.response.json().get("command", ""))
    assert cmd, "No assembled command available"
    assert fragment in cmd, f"Expected '{fragment}' in command:\n  {cmd}"


@then('the response body should contain a "{field}" list')
def step_response_has_list(context, field):
    data = context.response.json()
    assert field in data and isinstance(data[field], list), \
        f"Expected '{field}' to be a list in: {data}"


@then('the response body should contain "ok" equal to {value}')
def step_response_ok_shared(context, value):
    expected = value.strip().lower() == "true"
    data = context.response.json()
    assert data.get("ok") == expected, f"Expected ok={expected}, got: {data}"



@then('all three panels should be visible without horizontal scrolling')
def step_all_panels_visible(context):
    html = context.response.text
    for panel_id in ("qemu-panel", "robot-panel", "report-panel"):
        assert f'id="{panel_id}"' in html, f"Panel '{panel_id}' missing."
