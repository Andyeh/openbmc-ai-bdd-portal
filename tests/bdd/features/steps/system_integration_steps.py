# Copyright (c) 2026 Andy Yeh
# SPDX-License-Identifier: Apache-2.0
"""
BDD Step Definitions — System Integration & Exception Handling (Step 5)

Covers:
  - Backend HTTP error codes for invalid/conflicting requests
  - Frontend state management contracts (API always returns structured JSON)
  - End-to-end smoke flow validation

NOTE: Generic steps (status code, response field, command fragment) are defined in
portal_steps.py and reused here automatically by behave's shared step registry.
"""
import httpx
from behave import given, then


# ── Given ─────────────────────────────────────────────────────────────────────

@given("no QEMU instance is currently running via the API")
def step_ensure_qemu_not_running(context):
    """Stop any running QEMU instance before the test, ignoring 404."""
    resp = httpx.post(f"{context.base_url}/api/qemu/stop", json={}, timeout=10)
    # 404 is expected when nothing is running — that is acceptable here
    assert resp.status_code in (200, 404), (
        f"Unexpected status stopping QEMU: {resp.status_code}\n{resp.text}"
    )


# ── Then — new steps not covered by portal_steps.py ──────────────────────────

@then('the response status code should be 4xx')
def step_status_4xx(context):
    """Assert any 4xx client error response."""
    actual = context.response.status_code
    assert 400 <= actual < 500, (
        f"Expected 4xx, got HTTP {actual}.\n"
        f"Response: {context.response.text[:400]}"
    )


@then('the response body should contain an "{field}" field')
def step_response_has_field_an(context, field):
    """Assert a JSON field exists (grammar variant: 'an' instead of 'a')."""
    try:
        data = context.response.json()
    except Exception:
        raise AssertionError(
            f"Response is not valid JSON: {context.response.text[:200]}"
        )
    assert field in data, (
        f"Expected field '{field}' in response, got keys: {list(data.keys())}\n"
        f"Body: {context.response.text[:400]}"
    )


