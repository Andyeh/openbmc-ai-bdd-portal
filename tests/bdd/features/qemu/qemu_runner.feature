# Copyright (c) 2026 Andy Yeh
# SPDX-License-Identifier: Apache-2.0
# Feature: QEMU Runner
# ────────────────────────────────────────────────────────────────────────────
# BDD specification for the QEMU launch module.
# Covers: parameter input, preset commands, async execution, log streaming.
# ────────────────────────────────────────────────────────────────────────────

Feature: QEMU Runner — Launch and Monitor QEMU Instance
  As a firmware QA engineer
  I want to configure and launch a QEMU instance from the Portal UI
  So that I can boot an OpenBMC image and monitor the serial console output
  without manually typing shell commands

  Background:
    Given the OpenBMC AI-BDD Portal backend is running on port 8080
    And the QEMU binary exists at the configured path
    And at least one firmware image exists in the image directory

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 1 — 使用預設範例指令快速啟動 (ast2700-default)
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User fills in QEMU parameters using the ast2700 preset button
    Given the user is on the QEMU panel
    When the user clicks the "ast2700-default Preset" button
    Then the machine field should be auto-filled with "ast2700a1-evb"
    And the QEMU binary field should be auto-filled with the configured aarch64 binary path
    And the memory field should be auto-filled with "1G"
    And the extra args field should contain "-serial mon:stdio -serial null -display none"

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 2 — 使用預設範例指令快速啟動 (romulus)
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User fills in QEMU parameters using the romulus preset button
    Given the user is on the QEMU panel
    When the user clicks the "romulus Preset" button
    Then the machine field should be auto-filled with "romulus-bmc"
    And the QEMU binary field should be auto-filled with the configured arm binary path
    And the extra args field should contain "-nographic"

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 3 — API 接受 JSON 參數並組合 QEMU 指令
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: Backend receives JSON parameters and builds a valid QEMU command
    When the user sends a POST request to "/api/qemu/build-command" with body
      """
      {
        "machine": "ast2700a1-evb",
        "memory": "1G",
        "image": "obmc-phosphor-image-ast2700-default.static.mtd",
        "extra_args": "-serial mon:stdio -serial null -display none"
      }
      """
    Then the response status code should be 200
    And the response body should contain a "command" field
    And the command should include "-machine ast2700a1-evb"
    And the command should include "-m 1G"
    And the command should include "-drive file="
    And the command should include "if=mtd,format=raw"

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 4 — 成功啟動 QEMU 並取得 PID
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User launches QEMU with valid parameters and gets a process ID
    Given no QEMU instance is currently running
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "ast2700a1-evb",
        "memory": "1G",
        "image": "obmc-phosphor-image-ast2700-default.static.mtd",
        "extra_args": "-serial mon:stdio -serial null -display none",
        "dry_run": false
      }
      """
    Then the response status code should be 200
    And the response body should contain "ok" equal to true
    And the response body should contain a "pid" field
    And the response body should contain a "command" field showing the assembled command

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 5 — 重複啟動應被拒絕
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User attempts to launch QEMU when one is already running
    Given a QEMU instance is currently running
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "ast2700a1-evb",
        "memory": "1G",
        "image": "obmc-phosphor-image-ast2700-default.static.mtd"
      }
      """
    Then the response status code should be 409
    And the response body should contain an "detail" field

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 6 — 缺少必填欄位時應回傳錯誤
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: Backend rejects launch request with missing required fields
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "ast2700a1-evb"
      }
      """
    Then the response status code should be 422

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 7 — WebSocket 串流 QEMU 序列埠 Log
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: Client connects via WebSocket and receives QEMU serial output
    Given a QEMU instance is currently running
    When the client connects to the WebSocket endpoint "/api/qemu/ws/logs"
    Then the WebSocket connection should be established successfully
    And the client should receive at least one log message within 10 seconds

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 8 — 停止 QEMU
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User stops a running QEMU instance
    Given a QEMU instance is currently running
    When the user sends a POST request to "/api/qemu/stop" with body
      """
      {}
      """
    Then the response status code should be 200
    And the response body should contain "ok" equal to true
    And the QEMU status should change to "running" equal to false

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 9 — 停止不存在的 QEMU 應回傳適當錯誤
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: User attempts to stop QEMU when nothing is running
    Given no QEMU instance is currently running
    When the user sends a POST request to "/api/qemu/stop" with body
      """
      {}
      """
    Then the response status code should be 404
    And the response body should contain an "detail" field

  # ──────────────────────────────────────────────────────────────────────────
  # Scenario 10 — Dry-run 模式只回傳指令不實際執行
  # ──────────────────────────────────────────────────────────────────────────
  Scenario: Dry-run mode returns assembled command without executing it
    Given no QEMU instance is currently running
    When the user sends a POST request to "/api/qemu/launch" with body
      """
      {
        "machine": "ast2700a1-evb",
        "memory": "1G",
        "image": "obmc-phosphor-image-ast2700-default.static.mtd",
        "dry_run": true
      }
      """
    Then the response status code should be 200
    And the response body should contain "ok" equal to true
    And the response body should contain "dry_run" equal to true
    And no new QEMU process should be created
