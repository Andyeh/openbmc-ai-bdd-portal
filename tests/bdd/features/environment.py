# Copyright (c) 2026 Andy Yeh
# SPDX-License-Identifier: Apache-2.0
"""
Behave environment hooks.
"""


def before_all(context):
    context.base_url = "http://localhost:8080"


def before_scenario(context, scenario):
    context.response = None
    context.viewport = {"width": 1920, "height": 1080}


def after_scenario(context, scenario):
    if scenario.status == "failed":
        print(f"\n[HOOK] Scenario failed: {scenario.name}")
        if context.response is not None:
            print(f"  Last response status: {context.response.status_code}")
    
    # 確保每個測試案例結束後，皆能清理並停止背景的 QEMU 進程
    import httpx
    try:
        httpx.post(f"{context.base_url}/api/qemu/stop", timeout=5)
    except Exception:
        pass
