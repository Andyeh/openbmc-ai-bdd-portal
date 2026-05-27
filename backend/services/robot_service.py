"""
Robot Framework Service — directory tree scanning, safe execution, and async log streaming.

Security measures:
  - All suite paths are validated against robot_script_dir boundary (path traversal prevention)
  - Variable keys/values are validated against an allow-list pattern (shell injection prevention)
  - subprocess.run() is called with a list (never shell=True) to avoid command injection
"""
import asyncio
import re
import subprocess
import shlex
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.core.config import settings

# ── Validation constants ───────────────────────────────────────────────────────

# Allow-list for Robot variable keys: UPPER_SNAKE_CASE identifiers only
_VAR_KEY_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,63}$')

# Allow-list for Robot variable values: printable ASCII except shell meta-chars
# Blocks: ; & | ` $ ( ) < > ! \ newline
_VAR_VAL_DANGEROUS = re.compile(r'[;&|`$()<>!\\\n\r]')

# Allow-list for --include tag names (Robot Framework tag syntax)
_TAG_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_\-]{0,127}$')

# Max length for a single variable value
_VAR_VAL_MAX_LEN = 256

# Active robot runs: run_id → {"process": asyncio.subprocess, "log_queue": asyncio.Queue}
_active_runs: dict[str, dict] = {}


# ── Security helpers ───────────────────────────────────────────────────────────

def _resolve_and_validate_suite(suite_relative: str) -> tuple[bool, str, Path]:
    """
    Resolve suite_relative against robot_script_dir and verify it stays within boundary.
    Returns (ok, error_message, resolved_path).
    Path traversal sequences like '../' are caught by the boundary check.
    Also allows "." to refer to the root script dir itself.
    """
    base = settings.robot_script_dir.resolve()
    try:
        candidate = (base / suite_relative).resolve()
    except Exception as exc:
        return False, f"Invalid path: {exc}", Path()

    # Allow the root dir itself (suite_relative = "." resolves to base)
    if str(candidate) == str(base):
        return True, "", candidate

    # Enforce trailing-sep boundary to prevent partial-match bypass (e.g. /sandbox-evil)
    boundary = str(base) + "/"
    if not str(candidate).startswith(boundary):
        return False, f"Path traversal detected: '{suite_relative}'", Path()

    return True, "", candidate


def _validate_variables(variables: dict) -> tuple[bool, str]:
    """
    Validate all Robot variable key/value pairs against the allow-list.
    Returns (ok, error_message).
    """
    for key, val in variables.items():
        if not _VAR_KEY_RE.match(key):
            return False, (
                f"Invalid variable key '{key}'. "
                "Keys must be UPPER_SNAKE_CASE (A-Z, 0-9, underscore, ≤64 chars)."
            )
        val_str = str(val)
        if len(val_str) > _VAR_VAL_MAX_LEN:
            return False, f"Variable value for '{key}' exceeds {_VAR_VAL_MAX_LEN} characters."
        if _VAR_VAL_DANGEROUS.search(val_str):
            return False, (
                f"Variable value for '{key}' contains disallowed characters "
                "(shell metacharacters are forbidden)."
            )
    return True, ""


def _validate_include_tags(tags: list[str]) -> tuple[bool, str]:
    """Validate --include tag names against allow-list."""
    for tag in tags:
        if not _TAG_RE.match(tag):
            return False, f"Invalid include tag '{tag}'. Use alphanumeric/underscore/hyphen only."
    return True, ""


# ── .robot file parser ─────────────────────────────────────────────────────────

def _parse_robot_file(path: Path) -> tuple[str, list[dict]]:
    """
    Parse a .robot file and return (suite_documentation, test_cases).
    Each test case: {"name": str, "doc": str, "tags": list[str]}
    """
    suite_doc = ""
    tests: list[dict] = []

    try:
        lines = path.read_text(errors="replace").splitlines()
    except Exception:
        return "", []

    section = None
    current_test: Optional[dict] = None
    collecting_doc = False   # multi-line [Documentation] continuation

    for line in lines:
        stripped = line.strip()

        # ── Section header ─────────────────────────────────────────────────
        if stripped.startswith("***"):
            # Save previous test before switching sections
            if current_test is not None:
                tests.append(current_test)
                current_test = None
            collecting_doc = False

            if "Settings" in stripped:
                section = "settings"
            elif "Test Cases" in stripped:
                section = "test_cases"
            else:
                section = "other"
            continue

        # ── Settings section ───────────────────────────────────────────────
        if section == "settings":
            low = stripped.lower()
            if low.startswith("documentation"):
                rest = stripped.split(None, 1)
                suite_doc = rest[1].strip() if len(rest) > 1 else ""
            continue

        # ── Test Cases section ─────────────────────────────────────────────
        if section == "test_cases":
            if not stripped:
                collecting_doc = False
                continue

            # A new test case starts at column 0 (no leading whitespace)
            if line and not line[0].isspace():
                if current_test is not None:
                    tests.append(current_test)
                current_test = {"name": stripped, "doc": "", "tags": []}
                collecting_doc = False
                continue

            if current_test is None:
                continue

            low = stripped.lower()

            if low.startswith("[documentation]"):
                rest = stripped[15:].strip()
                # Remove leading "  " separator if present
                if rest.startswith("  "):
                    rest = rest.strip()
                current_test["doc"] = rest
                collecting_doc = True

            elif collecting_doc and stripped.startswith("..."):
                # Continuation line for [Documentation]
                cont = stripped[3:].strip()
                if cont:
                    current_test["doc"] = (current_test["doc"] + " " + cont).strip()

            elif low.startswith("[tags]"):
                tags_raw = stripped[6:].strip()
                current_test["tags"] = [t.strip() for t in tags_raw.split() if t.strip()]
                collecting_doc = False

            else:
                collecting_doc = False

    # Flush last test
    if current_test is not None:
        tests.append(current_test)

    return suite_doc, tests


# ── test_list file parser ──────────────────────────────────────────────────────

# Category descriptions for well-known test_list names
_TEST_LIST_DESCRIPTIONS = {
    "QEMU_CI":          "QEMU 模擬環境 CI 測試 — SSH/IPMI 連線、Redfish 基礎、應用程式錯誤檢查",
    "CT_basic_run":     "完整基礎測試 — Redfish、REST、IPMI、電源、清單、憑證、BMC 傾印",
    "HW_CI":            "硬體 CI 測試 — 電源管理、Redfish 完整流程、系統開機時間",
    "HW_CI_DEV":        "硬體開發 CI — 含額外硬體特定測試案例",
    "HW_CI_NETWORK":    "網路功能 CI 測試 — 網路設定、路由、DNS 驗證",
    "BMC_WEB_CI":       "BMC Web GUI CI — 介面操作、健康狀態、事件日誌",
    "WEBUI_CI":         "Web UI 完整 CI — 瀏覽器操作與 Web 介面驗證",
}


def _parse_test_list(path: Path) -> Optional[dict]:
    """
    Parse a test_list file, returning a dict:
      { name, description, includes, count }
    Returns None for binary/invalid files.
    """
    if path.is_dir():
        return None
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return None

    lines = text.splitlines()
    description = _TEST_LIST_DESCRIPTIONS.get(path.name, "")
    first_comment = ""
    includes: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            comment = stripped[1:].strip()
            if comment and not first_comment:
                first_comment = comment
        elif stripped.startswith("--include"):
            tag = stripped.replace("--include", "").strip()
            if tag:
                includes.append(tag)

    if not includes:
        return None

    # Use curated description, fall back to first comment, then filename
    desc = description or first_comment or path.name

    return {
        "name":        path.name,
        "description": desc,
        "includes":    includes,
        "count":       len(includes),
    }


# ── Tree scanner ───────────────────────────────────────────────────────────────

def _build_tree(base: Path, current: Path, depth: int = 0) -> list[dict]:
    """
    Recursively build a JSON-serialisable tree of .robot files and directories.
    Each node:
      { "name": str, "path": str (relative to base), "type": "dir"|"file", "children": [...] }
    """
    if depth > 10:  # guard against deep symlink cycles
        return []

    nodes = []
    try:
        entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return []

    for entry in entries:
        if entry.name.startswith('.') or entry.name.startswith('__'):
            continue

        rel = str(entry.relative_to(base))

        if entry.is_dir():
            children = _build_tree(base, entry, depth + 1)
            # Only include dirs that eventually contain .robot files
            if children:
                nodes.append({
                    "name":     entry.name,
                    "path":     rel,
                    "type":     "dir",
                    "children": children,
                })
        elif entry.is_file() and entry.suffix == '.robot':
            nodes.append({
                "name":     entry.name,
                "path":     rel,
                "type":     "file",
                "children": [],
            })

    return nodes


# ── Category display names ────────────────────────────────────────────────────

_CATEGORY_DISPLAY = {
    "redfish":    ("🔴", "Redfish",    "Redfish API 測試 — 帳號、電源、韌體、清單等"),
    "ipmi":       ("🔵", "IPMI",       "IPMI 指令測試 — 使用者、SEL、感測器、電源控制"),
    "network":    ("🌐", "Network",    "網路功能測試 — 介面、路由、DNS、VLAN"),
    "extended":   ("🔧", "Extended",   "進階功能測試 — 開機、程式碼更新、診斷"),
    "pldm":       ("📡", "PLDM",       "PLDM 平台管理測試 — Base、Platform、BIOS 屬性"),
    "gui":        ("🖥",  "GUI",        "BMC Web GUI 測試 — 介面操作與驗證"),
    "openpower":  ("⚡", "OpenPOWER", "OpenPOWER 平台測試 — OPAL、Skiboot"),
    "systest":    ("🧪", "Systest",    "系統測試 — 壓力測試、網路穩定性、開機驗收"),
    "oem":        ("🏭", "OEM",        "OEM 特定測試案例"),
    "ffdc":       ("📋", "FFDC",       "FFDC 日誌收集測試"),
}


def _parse_output_xml(xml_path: Path) -> dict:
    """
    Parse Robot Framework output.xml and return pass/fail counts and elapsed time.
    Returns {"passed": int|None, "failed": int|None, "elapsed_s": float|None}.
    """
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()

        passed = None
        failed = None
        elapsed_s = None

        # Parse pass/fail from total statistics
        stat = root.find(".//statistics/total/stat")
        if stat is not None:
            try:
                passed = int(stat.get("pass", 0))
            except (TypeError, ValueError):
                passed = None
            try:
                failed = int(stat.get("fail", 0))
            except (TypeError, ValueError):
                failed = None

        # Parse elapsed time from suite/status
        # schemaversion >= 5 (RF 5.x+): elapsed is in seconds (float)
        # schemaversion <  5 (RF 4.x):  elapsed was in milliseconds
        schema_ver = int(root.get("schemaversion", "4"))
        suite_status = root.find("suite/status")
        if suite_status is not None:
            elapsed_raw = suite_status.get("elapsed")
            if elapsed_raw is not None:
                try:
                    elapsed_val = float(elapsed_raw)
                    elapsed_s = elapsed_val if schema_ver >= 5 else elapsed_val / 1000.0
                except (TypeError, ValueError):
                    elapsed_s = None

        return {"passed": passed, "failed": failed, "elapsed_s": elapsed_s}

    except Exception:
        return {"passed": None, "failed": None, "elapsed_s": None}


class RobotService:
    """Execute Robot Framework suites and manage reports."""

    # ── Directory scanning ─────────────────────────────────────────────────────

    def list_tree(self, root: Optional[Path] = None) -> list[dict]:
        """Return a nested tree of .robot files under robot_script_dir (or root if given)."""
        base = (root or settings.robot_script_dir).resolve()
        if not base.exists():
            return []
        return _build_tree(base, base)

    def list_suites(self) -> list[dict]:
        """Flat list of all .robot suites (legacy endpoint, kept for backward compat)."""
        base = settings.robot_script_dir
        if not base.exists():
            return []
        suites = []
        for rf in sorted(base.rglob("*.robot")):
            suites.append({
                "name":      rf.stem,
                "path":      str(rf.relative_to(base)),
                "full_path": str(rf),
            })
        return suites

    def list_reports(self) -> list[dict]:
        out_dir = settings.robot_output_dir.resolve()
        if not out_dir.exists():
            return []
        reports = []
        for html in sorted(out_dir.rglob("report.html"), reverse=True):
            ts = datetime.fromtimestamp(html.stat().st_mtime)
            rel_dir = html.parent.relative_to(out_dir)
            stats = _parse_output_xml(html.parent / "output.xml")
            allure_index = html.parent / "allure-report" / "index.html"
            entry = {
                "name":        html.parent.name,
                "report_path": str(rel_dir / "report.html"),
                "log_path":    str(rel_dir / "log.html"),
                "modified":    ts.isoformat(),
                "allure_path": str(rel_dir / "allure-report" / "index.html") if allure_index.exists() else None,
            }
            entry.update(stats)
            reports.append(entry)
        return reports

    def list_categorized(self) -> list[dict]:
        """
        Return .robot test cases grouped by top-level category folder.
        Each category: { name, display_name, icon, description, tests: [...] }
        Each test:     { name, doc, tags, file, suite_doc }
        """
        base = settings.robot_script_dir.resolve()
        if not base.exists():
            return []

        categories: dict[str, dict] = {}

        for robot_file in sorted(base.rglob("*.robot")):
            # Skip non-test files (lib resources, __init__ etc.)
            rel = robot_file.relative_to(base)
            parts = rel.parts

            # Top-level folder = category; files directly in root go to "general"
            category_key = parts[0] if len(parts) > 1 else "general"

            # Skip directories that are purely libraries/data
            if category_key in ("lib", "data", "bin", "docs", "logs"):
                continue

            suite_doc, tests = _parse_robot_file(robot_file)

            if not tests:
                continue

            if category_key not in categories:
                icon, display_name, desc = _CATEGORY_DISPLAY.get(
                    category_key,
                    ("📄", category_key.replace("_", " ").title(), ""),
                )
                categories[category_key] = {
                    "key":          category_key,
                    "display_name": display_name,
                    "icon":         icon,
                    "description":  desc,
                    "tests":        [],
                }

            file_rel = str(rel)
            for test in tests:
                categories[category_key]["tests"].append({
                    "name":      test["name"],
                    "doc":       test["doc"],
                    "tags":      test["tags"],
                    "file":      file_rel,
                    "suite_doc": suite_doc,
                })

        # Sort categories by key, put well-known ones first
        priority = ["redfish", "ipmi", "network", "extended", "pldm", "gui"]
        result = sorted(
            categories.values(),
            key=lambda c: (priority.index(c["key"]) if c["key"] in priority else 99, c["key"])
        )
        return result

    def list_test_lists(self) -> list[dict]:
        """Return predefined CI test suites from test_lists/ directory."""
        test_lists_dir = settings.robot_script_dir / "test_lists"
        if not test_lists_dir.exists():
            return []

        result = []
        for f in sorted(test_lists_dir.iterdir()):
            parsed = _parse_test_list(f)
            if parsed:
                result.append(parsed)
        return result

    # ── Command builder ────────────────────────────────────────────────────────

    def _build_robot_cmd(
        self,
        suites: list[str],
        variables: dict,
        out_dir: Path,
        include_tags: Optional[list[str]] = None,
        test_names: Optional[list[str]] = None,
    ) -> tuple[bool, str, list[str]]:
        """
        Build the robot command list.
        Returns (ok, error, cmd_list).
        Suites may be file paths (.robot) or directory paths (relative to robot_script_dir).
        include_tags: optional list of --include tag names (for test_list mode).
        """
        # Validate variables first
        ok, err = _validate_variables(variables)
        if not ok:
            return False, err, []

        # Validate include_tags if provided
        if include_tags:
            ok2, err2 = _validate_include_tags(include_tags)
            if not ok2:
                return False, err2, []

        base = settings.robot_script_dir.resolve()
        resolved_suites: list[Path] = []

        for suite in suites:
            ok3, err3, resolved = _resolve_and_validate_suite(suite)
            if not ok3:
                return False, err3, []
            if not resolved.exists():
                return False, f"Suite not found: '{suite}'", []
            resolved_suites.append(resolved)

        cmd = [
            sys.executable, "-m", "robot",
            "--loglevel",  settings.robot_log_level,
            "--outputdir", str(out_dir),
            "--output",    "output.xml",
            "--log",       "log.html",
            "--report",    "report.html",
        ]
        for k, v in variables.items():
            cmd += ["--variable", f"{k}:{v}"]

        if include_tags:
            for tag in include_tags:
                cmd += ["--include", tag]

        if test_names:
            for name in test_names:
                cmd += ["--test", name]

        # Allure listener — generates allure-results/ alongside the Robot outputs
        allure_results = out_dir / "allure-results"
        cmd += ["--listener", f"allure_robotframework;{allure_results}"]

        for path in resolved_suites:
            cmd.append(str(path))

        return True, "", cmd

    @staticmethod
    async def _regenerate_robot_reports(out_dir: Path) -> None:
        """If report.html is missing (e.g. after a forced stop), regenerate it from output.xml."""
        output_xml  = out_dir / "output.xml"
        report_html = out_dir / "report.html"
        if not output_xml.exists() or report_html.exists():
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "robot.rebot",
                "--outputdir", str(out_dir),
                "--output",   "output.xml",
                "--log",      "log.html",
                "--report",   "report.html",
                "--nostatusrc",
                str(output_xml),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=30)
        except Exception:
            pass  # best-effort only

    @staticmethod
    async def _generate_allure_report(out_dir: Path) -> None:
        """Run `allure generate` to produce a static Allure HTML report from allure-results/."""
        allure_results = out_dir / "allure-results"
        allure_report  = out_dir / "allure-report"
        if not allure_results.exists():
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "allure", "generate", str(allure_results),
                "-o", str(allure_report),
                "--clean",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
        except FileNotFoundError:
            pass  # allure CLI not installed — skip silently

    # ── Synchronous run (used by run_async via executor) ──────────────────────

    def run(
        self,
        suites: list[str],
        variables: Optional[dict] = None,
        dry_run: bool = False,
        include_tags: Optional[list[str]] = None,
        test_names: Optional[list[str]] = None,
    ) -> dict:
        variables = variables or {}
        include_tags = include_tags or []
        test_names = test_names or []

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = settings.robot_output_dir / ts

        ok, err, cmd = self._build_robot_cmd(suites, variables, out_dir, include_tags, test_names)
        if not ok:
            return {"ok": False, "error": err}

        command_str = shlex.join(cmd)

        if dry_run:
            return {
                "ok":      True,
                "dry_run": True,
                "command": command_str,
            }

        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = subprocess.run(
                cmd,            # list — avoids shell injection; shell=False (default)
                capture_output=True,
                text=True,
                timeout=settings.robot_run_timeout,
            )
            # Best-effort Allure generation (sync subprocess, short-lived)
            allure_results = out_dir / "allure-results"
            if allure_results.exists():
                try:
                    subprocess.run(
                        ["allure", "generate", str(allure_results),
                         "-o", str(out_dir / "allure-report"), "--clean"],
                        capture_output=True, timeout=settings.robot_allure_timeout,
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    pass
            return {
                "ok":         result.returncode == 0,
                "returncode": result.returncode,
                "stdout":     result.stdout[-4000:],
                "stderr":     result.stderr[-2000:],
                "report_dir": str(out_dir),
                "command":    command_str,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Robot run timed out (600 s)"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def run_async(
        self,
        suites: list[str],
        variables: Optional[dict] = None,
        dry_run: bool = False,
        include_tags: Optional[list[str]] = None,
        test_names: Optional[list[str]] = None,
    ) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.run(suites, variables, dry_run, include_tags, test_names)
        )

    # ── Async streaming run ────────────────────────────────────────────────────

    async def start_streaming_run(
        self,
        suites: list[str],
        variables: Optional[dict] = None,
        include_tags: Optional[list[str]] = None,
        test_names: Optional[list[str]] = None,
    ) -> tuple[bool, str, str, str]:
        """
        Start a Robot run as an async subprocess and register it for WS log streaming.
        Returns (ok, error_message, run_id, command_string).
        """
        variables = variables or {}
        include_tags = include_tags or []
        test_names = test_names or []

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = ts.split("_")[1]  # HHMMSS — WebSocket / _active_runs key
        out_dir = settings.robot_output_dir / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        ok, err, cmd = self._build_robot_cmd(suites, variables, out_dir, include_tags, test_names)
        if not ok:
            return False, err, "", ""

        cmd_str = shlex.join(cmd)

        # Launch subprocess non-blocking
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        log_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        _active_runs[run_id] = {
            "process":   proc,
            "log_queue": log_queue,
            "out_dir":   str(out_dir),
            "command":   cmd_str,
        }

        # Background reader task feeds queue
        asyncio.create_task(self._feed_log_queue(run_id, proc, log_queue))

        return True, "", run_id, cmd_str

    async def _feed_log_queue(
        self,
        run_id: str,
        proc: asyncio.subprocess.Process,
        queue: asyncio.Queue,
    ):
        """Read stdout line-by-line and push into the log queue."""
        assert proc.stdout is not None
        try:
            async for line in proc.stdout:
                await queue.put(line.decode(errors="replace"))
        finally:
            await proc.wait()
            await queue.put(None)  # sentinel — signals process stdout ended

            # Generate reports; frontend waits for allure_done before showing reports
            run_info = _active_runs.get(run_id)
            if run_info:
                out_dir = Path(run_info["out_dir"])
                await self._regenerate_robot_reports(out_dir)  # rebot if report.html missing
                await self._generate_allure_report(out_dir)
            await queue.put({"allure_done": True})  # sentinel — signals allure complete

            # Clean up run entry after a grace period
            await asyncio.sleep(settings.robot_cleanup_grace_period)
            _active_runs.pop(run_id, None)

    def get_run_info(self, run_id: str) -> Optional[dict]:
        return _active_runs.get(run_id)

    async def stream_logs_to_websocket(self, run_id: str, websocket) -> None:
        """Push log queue entries to the given WebSocket until stream ends."""
        import json as _json

        info = _active_runs.get(run_id)
        if not info:
            await websocket.send_text(
                _json.dumps({"error": f"Unknown run_id: {run_id}"})
            )
            return

        queue: asyncio.Queue = info["log_queue"]
        proc: asyncio.subprocess.Process = info["process"]

        while True:
            line = await queue.get()
            if line is None:
                # Process stdout ended — notify frontend allure is generating
                rc = proc.returncode if proc.returncode is not None else -1
                await websocket.send_text(
                    _json.dumps({"generating_allure": True, "returncode": rc})
                )
                continue
            if isinstance(line, dict) and line.get("allure_done"):
                # Allure done — send final status so frontend loads reports
                rc = proc.returncode if proc.returncode is not None else -1
                await websocket.send_text(
                    _json.dumps({"returncode": rc, "done": True})
                )
                break
            await websocket.send_text(line)


robot_service = RobotService()
