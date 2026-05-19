"""
Application configuration via pydantic-settings.
Reads from environment variables / .env file.
對應腳本: run-qemu-robot-test.sh / boot-qemu.sh
"""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Server ────────────────────────────────
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    app_debug: bool = True

    # ── QEMU — 對應 run-qemu-robot-test.sh ───
    # UPSTREAM_WORKSPACE: bitbake build 輸出目錄 (BASE_DIR in boot-qemu.sh)
    upstream_workspace: Path = Path("/home/andyeh/workspace/openbmc/build/ast2700-default")
    # MACHINE: 機型名稱 (決定 boot-qemu.sh 的 -machine 參數)
    machine: str = "ast2700-default"
    # QEMU_BIN: 相對於 upstream_workspace 的 binary 路徑 (或絕對路徑)
    qemu_binary: str = (
        "/home/andyeh/workspace/openbmc/build/ast2700-default"
        "/tmp/work/x86_64-linux/qemu-helper-native/1.0"
        "/recipe-sysroot-native/usr/bin/qemu-system-aarch64"
    )
    # QEMU_IMAGE_DIR: deploy images 目錄 (掃描 *.static.mtd / *.ubi.mtd)
    qemu_image_dir: Path = Path(
        "/home/andyeh/workspace/openbmc/build/ast2700-default"
        "/tmp/deploy/images/ast2700-default"
    )
    qemu_default_machine: str = "ast2700a1-evb"
    # QEMU_RUN_TIMER: Docker 容器存活時間 (秒)
    qemu_run_timer: int = 3600
    # QEMU_LOGIN_TIMER: 等待 OPENBMC-READY 的最大時間 (秒)
    qemu_login_timer: int = 180
    # Portal 內部 boot 完成等待逾時
    qemu_boot_timeout: int = 300

    # ── Docker ────────────────────────────────
    # DOCKER_IMG_NAME: 對應 run-qemu-robot-test.sh
    docker_img_name: str = "openbmc/ast2700-robot-qemu:Andy"
    docker_socket: str = "/var/run/docker.sock"
    # OBMC_BUILD_DIR: 容器內的掛載路徑
    obmc_build_dir: str = "/tmp/openbmc/build"

    # ── Robot Framework ───────────────────────
    robot_script_dir: Path = Path(
        "/home/andyeh/workspace/ci_test_area/openbmc-test-automation"
    )
    robot_output_dir: Path = Path("tests/bdd/reports")
    robot_log_level: str = "INFO"

    # ── Allure ────────────────────────────────
    allure_results_dir: Path = Path("tests/bdd/reports/allure-results")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 允許 .env 中有大寫變數名稱對應小寫 field 名稱
        case_sensitive = False


settings = Settings()
