"""
Robot Framework Service — run .robot scripts and collect results.
"""
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.core.config import settings


class RobotService:
    """Execute Robot Framework suites and manage reports."""

    def list_suites(self) -> list[dict]:
        base = settings.robot_script_dir
        if not base.exists():
            return []
        suites = []
        for rf in sorted(base.rglob("*.robot")):
            suites.append({
                "name": rf.stem,
                "path": str(rf.relative_to(base)),
                "full_path": str(rf),
            })
        return suites

    def list_reports(self) -> list[dict]:
        out_dir = settings.robot_output_dir
        if not out_dir.exists():
            return []
        reports = []
        for html in sorted(out_dir.rglob("report.html"), reverse=True):
            ts = datetime.fromtimestamp(html.stat().st_mtime)
            reports.append({
                "name": html.parent.name,
                "report_path": str(html),
                "log_path": str(html.parent / "log.html"),
                "modified": ts.isoformat(),
            })
        return reports

    def run(self, suite_path: str, extra_vars: Optional[dict] = None) -> dict:
        full_path = settings.robot_script_dir / suite_path
        if not full_path.exists():
            return {"ok": False, "error": f"Suite not found: {full_path}"}

        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out_dir = settings.robot_output_dir / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "python", "-m", "robot",
            "--loglevel", settings.robot_log_level,
            "--outputdir", str(out_dir),
            "--output", "output.xml",
            "--log", "log.html",
            "--report", "report.html",
        ]
        if extra_vars:
            for k, v in extra_vars.items():
                cmd += ["--variable", f"{k}:{v}"]
        cmd.append(str(full_path))

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-2000:],
                "report_dir": str(out_dir),
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "Robot run timed out (600 s)"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def run_async(self, suite_path: str, extra_vars: Optional[dict] = None) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.run(suite_path, extra_vars))


robot_service = RobotService()
