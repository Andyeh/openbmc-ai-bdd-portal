# Feature: Portal Architecture
# ────────────────────────────────────────────────────────────────────────────
# BDD specification for the OpenBMC AI-BDD Portal's foundational UI layout.
# Covers: QEMU control panel, Robot script selector, and Report viewer.
# ────────────────────────────────────────────────────────────────────────────

Feature: Portal Architecture — Main Dashboard Layout
  As a firmware QA engineer
  I want to open the OpenBMC AI-BDD Portal in a browser
  So that I can control QEMU, select Robot scripts, and view test reports
  from a single unified interface

  Background:
    Given the OpenBMC AI-BDD Portal backend is running on port 8080
    And the portal home page is accessible at "http://localhost:8080"

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 1 — Basic page load
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User opens the portal and sees the main dashboard
    When the user navigates to the portal home page
    Then the page title should be "OpenBMC AI-BDD Portal"
    And the HTTP response status code should be 200
    And the page should contain the main navigation bar
    And the page should display exactly three panels:
      | panel_id      | panel_label              |
      | qemu-panel    | QEMU 操作區              |
      | robot-panel   | Robot 測試               |
      | report-panel  | 報告                     |

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 2 — QEMU Control Panel
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User sees the QEMU operation panel with status and controls
    When the user navigates to the portal home page
    Then the QEMU panel should be visible
    And the QEMU panel should display the current QEMU status
    And the QEMU panel should show a machine type selector
    And the QEMU panel should show a firmware image selector
    And the QEMU panel should have a "Launch QEMU" button
    And the QEMU panel should have a "Stop QEMU" button
    And the QEMU panel should show a real-time log console

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 3 — Robot Script Selector Panel
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User sees the Robot Framework script selection panel
    When the user navigates to the portal home page
    Then the Robot panel should be visible
    And the Robot panel should list available .robot test suites
    And the Robot panel should have a "▶ Run" button
    And the Robot panel should allow setting extra Robot variables

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 4 — Report Viewer Panel
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User sees the test report viewer panel
    When the user navigates to the portal home page
    Then the Report panel should be visible
    And the Report panel should list past test run reports

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 5 — API Health Check
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: Backend health endpoint is reachable
    When the user sends a GET request to "/health"
    Then the response status code should be 200
    And the response body should contain "status" equal to "ok"

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 6 — QEMU Status API
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: QEMU status API returns current state
    When the user sends a GET request to "/api/qemu/status"
    Then the response status code should be 200
    And the response body should contain a "running" field

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 7 — Robot Suite List API
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: Robot suite list API returns available suites
    When the user sends a GET request to "/api/robot/suites"
    Then the response status code should be 200
    And the response body should contain a "suites" list

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 8 — Responsive layout on mobile viewport
  # ──────────────────────────────────────────────────────────────────────────
  Scenario Outline: Dashboard panels are accessible on different screen sizes
    Given the browser viewport is set to "<width>" x "<height>"
    When the user navigates to the portal home page
    Then all three panels should be visible without horizontal scrolling

    Examples:
      | width | height |
      | 1920  | 1080   |
      | 1280  | 800    |
      | 768   | 1024   |
