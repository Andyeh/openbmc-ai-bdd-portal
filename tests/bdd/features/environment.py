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
