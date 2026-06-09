# Copyright (c) 2026 Andy Yeh
# SPDX-License-Identifier: Apache-2.0
"""
Application configuration.

載入順序（優先級由低至高）：
  1. config/portal.yaml  — 使用者編輯的主設定檔
  2. .env / 環境變數     — CI/CD 覆蓋用

一般使用者只需編輯 config/portal.yaml。
"""
from pathlib import Path
from typing import Optional

import yaml
from pydantic import model_validator
from pydantic_settings import BaseSettings

# ── Load portal.yaml ──────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "portal.yaml"


def _yaml() -> dict:
    if _CONFIG_PATH.exists():
        with _CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _y(*keys, default=None):
    """Traverse nested YAML dict with dot-style keys, return default if missing."""
    node = _yaml()
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
        if node is default:
            return default
    return node


# ── Settings ──────────────────────────────────────────────────────────────────

class Settings(BaseSettings):
    # ── Server ────────────────────────────────────────────────────
    app_host:  str  = _y("server", "host",  default="0.0.0.0")
    app_port:  int  = _y("server", "port",  default=8080)
    app_debug: bool = _y("server", "debug", default=True)

    # ── OpenBMC ───────────────────────────────────────────────────
    openbmc_workspace: Path = Path(_y("openbmc", "workspace", default="/home/andyeh/workspace/openbmc"))
    machine:           str  = _y("openbmc", "machine",          default="ast2700-default")
    robot_script_dir:  Path = Path(_y("openbmc", "robot_script_dir",
                                      default="/home/andyeh/workspace/ci_test_area/openbmc-test-automation"))

    # ── QEMU ─────────────────────────────────────────────────────
    qemu_run_timer:     int = _y("qemu", "run_timer",     default=3600)
    qemu_login_timer:   int = _y("qemu", "login_timer",   default=180)
    qemu_boot_timeout:  int = _y("qemu", "boot_timeout",  default=300)
    qemu_default_memory: str = _y("qemu", "default_memory", default="1G")
    qemu_temp_image_dir: str = _y("qemu", "temp_image_dir", default="/tmp")

    # ── Docker ────────────────────────────────────────────────────
    docker_img_name:      str = _y("docker", "image",          default="openbmc/ast2700-robot-qemu:latest")
    docker_socket:        str = _y("docker", "socket",         default="/var/run/docker.sock")
    obmc_build_dir:       str = _y("docker", "build_dir",      default="/tmp/openbmc/build")
    docker_runner_image:  str = _y("docker", "runner_image",   default="crops/poky:ubuntu-22.04")
    docker_container_name: str = _y("docker", "container_name", default="qemu-portal-session")

    # ── Robot Framework ───────────────────────────────────────────
    robot_output_dir:           Path = Path(_y("robot", "output_dir", default="tests/bdd/reports"))
    robot_log_level:            str  = _y("robot", "log_level",            default="INFO")
    robot_run_timeout:          int  = _y("robot", "run_timeout",          default=600)
    robot_allure_timeout:       int  = _y("robot", "allure_timeout",       default=120)
    robot_cleanup_grace_period: int  = _y("robot", "cleanup_grace_period", default=300)

    # ── Allure (derived from robot_output_dir) ────────────────────
    allure_results_dir: Optional[Path] = None

    # ── Derived paths (not user-editable directly) ────────────────
    upstream_workspace: Optional[Path] = None
    qemu_image_dir:     Optional[Path] = None
    qemu_binary:        Optional[str]  = None

    @model_validator(mode="after")
    def derive_paths(self) -> "Settings":
        build_dir = self.openbmc_workspace / "build" / self.machine
        if self.upstream_workspace is None:
            self.upstream_workspace = build_dir
        if self.qemu_image_dir is None:
            self.qemu_image_dir = build_dir / "tmp" / "deploy" / "images" / self.machine
        if self.allure_results_dir is None:
            self.allure_results_dir = self.robot_output_dir / "allure-results"
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
