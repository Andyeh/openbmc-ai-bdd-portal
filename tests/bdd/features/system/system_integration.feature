Feature: System Integration & Exception Handling
  As a portal user or developer
  I want the system to handle errors gracefully and maintain a responsive UI
  So that failures are clearly communicated and the portal never gets stuck in a broken state

  Background:
    Given the OpenBMC AI-BDD Portal backend is running on port 8080

  # ── 1. Backend Exception Handling ─────────────────────────────────────────

  Scenario: QEMU launch fails when no image is provided — backend returns 422
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {"machine": "romulus-bmc", "image": ""}
      """
    Then the response status code should be 422

  Scenario: QEMU launch with non-existent image — backend returns 4xx with error detail
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "romulus-bmc",
        "image": "nonexistent-image-99999.mtd",
        "dry_run": false
      }
      """
    Then the response status code should be 4xx
    And the response body should contain an "detail" field

  Scenario: QEMU dry-run always succeeds even with missing binary — returns command without executing
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "romulus-bmc",
        "image": "obmc-phosphor-image-romulus.static.mtd",
        "dry_run": true
      }
      """
    Then the response status code should be 200
    And the response body should contain "ok" equal to true
    And the response body should contain a "command" field

  Scenario: Stopping QEMU when nothing is running — backend returns 404
    Given no QEMU instance is currently running via the API
    When the user sends a POST request to "/api/qemu/stop" with body
      """
      {}
      """
    Then the response status code should be 404
    And the response body should contain an "detail" field

  Scenario: Robot run with path traversal in suite path — backend returns 400
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["../../etc/passwd"],
        "variables": {}
      }
      """
    Then the response status code should be 400
    And the response body should contain an "detail" field

  Scenario: Robot run with shell injection in variable value — backend returns 400
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["templates/test_openbmc_setup.robot"],
        "variables": {"OPENBMC_HOST": "127.0.0.1; rm -rf /"}
      }
      """
    Then the response status code should be 400
    And the response body should contain an "detail" field

  Scenario: Querying status of a non-existent run_id — backend returns 404
    When the user sends a GET request to "/api/robot/run/nonexistent-run-id-00000/status"
    Then the response status code should be 404
    And the response body should contain an "detail" field

  Scenario: Robot stream-run with missing required suite — backend returns 400 or 422
    When the user sends a POST request to "/api/robot/stream-run" with body
      """
      {"suites": [], "variables": {}}
      """
    Then the response status code should be 4xx

  # ── 2. Frontend State: API contracts for button state management ───────────

  Scenario: Health check endpoint is available and returns ok status
    When the user sends a GET request to "/health"
    Then the response status code should be 200
    And the response body should contain "status" equal to "ok"

  Scenario: QEMU status endpoint always returns a structured response
    When the user sends a GET request to "/api/qemu/status"
    Then the response status code should be 200
    And the response body should contain a "running" field


  Scenario: Robot reports endpoint returns a list even when empty
    When the user sends a GET request to "/api/robot/reports"
    Then the response status code should be 200
    And the response body should contain a "reports" list

  Scenario: QEMU images endpoint returns a list even when build dir is absent
    When the user sends a GET request to "/api/qemu/images"
    Then the response status code should be 200
    And the response body should contain a "images" list

  # ── 3. End-to-End Smoke Flow ───────────────────────────────────────────────

  Scenario: Full smoke flow — health, status, dry-run, reports all succeed in sequence
    When the user sends a GET request to "/health"
    Then the response status code should be 200
    When the user sends a GET request to "/api/qemu/status"
    Then the response status code should be 200
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "romulus-bmc",
        "image": "obmc-phosphor-image-romulus.static.mtd",
        "dry_run": true
      }
      """
    Then the response status code should be 200
    And the response body should contain a "command" field
    When the user sends a GET request to "/api/robot/reports"
    Then the response status code should be 200

  Scenario: Robot dry-run returns a properly quoted command with --test flags
    When the user sends a POST request to "/api/robot/run" with body
      """
      {
        "suites": ["templates/test_openbmc_setup.robot"],
        "variables": {"OPENBMC_HOST": "192.168.7.2"},
        "dry_run": true,
        "test_names": ["Verify Ping"]
      }
      """
    Then the response status code should be 200
    And the response body should contain a "command" field
    And the command should include "--test"
    And the command should include "OPENBMC_HOST"
