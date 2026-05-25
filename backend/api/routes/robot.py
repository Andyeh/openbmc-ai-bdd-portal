"""
Robot Framework API Router — tree scan, safe batch execution, WebSocket log streaming.
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, field_validator
from typing import Optional
import re

from backend.services.robot_service import robot_service
from backend.core.config import settings

router = APIRouter(prefix="/api/robot", tags=["Robot"])

# ── Allow-list validation (mirrors service layer) ────────────────────────────
_VAR_KEY_RE    = re.compile(r'^[A-Z][A-Z0-9_]{0,63}$')
_VAR_VAL_DANGEROUS = re.compile(r'[;&|`$()<>!\\\n\r]')
_TAG_RE        = re.compile(r'^[A-Za-z][A-Za-z0-9_\-]{0,127}$')


# ── Request models ────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    """Run one or more Robot suites (files or directories, relative to robot_script_dir)."""
    suites:       list[str]
    variables:    dict[str, str] = {}
    dry_run:      bool = False
    include_tags: list[str] = []
    test_names:   list[str] = []

    @field_validator("suites")
    @classmethod
    def validate_suites(cls, suites: list[str]) -> list[str]:
        if not suites:
            raise ValueError("suites must contain at least one path.")
        return suites

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, variables: dict[str, str]) -> dict[str, str]:
        for key in variables:
            if not _VAR_KEY_RE.match(key):
                raise ValueError(
                    f"Invalid variable key '{key}'. Use UPPER_SNAKE_CASE."
                )
        return variables

    @field_validator("include_tags")
    @classmethod
    def validate_include_tags(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if not _TAG_RE.match(tag):
                raise ValueError(f"Invalid include tag '{tag}'.")
        return tags


class StreamRunRequest(BaseModel):
    """Start a streaming run (returns run_id for WebSocket consumption)."""
    suites:       list[str]
    variables:    dict[str, str] = {}
    include_tags: list[str] = []
    test_names:   list[str] = []

    @field_validator("suites")
    @classmethod
    def validate_suites(cls, suites: list[str]) -> list[str]:
        if not suites:
            raise ValueError("suites must not be empty.")
        for s in suites:
            if ".." in s or (s.startswith("/") and s != "/"):
                raise ValueError(f"Invalid suite path: '{s}'")
        return suites

    @field_validator("variables")
    @classmethod
    def validate_variables(cls, variables: dict[str, str]) -> dict[str, str]:
        for key, val in variables.items():
            if not _VAR_KEY_RE.match(key):
                raise ValueError(f"Invalid variable key '{key}'.")
            if _VAR_VAL_DANGEROUS.search(str(val)):
                raise ValueError(f"Variable value for '{key}' contains disallowed chars.")
        return variables

    @field_validator("include_tags")
    @classmethod
    def validate_include_tags(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if not _TAG_RE.match(tag):
                raise ValueError(f"Invalid include tag '{tag}'.")
        return tags


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/tree")
def get_tree(root: Optional[str] = None):
    """Return a hierarchical tree of .robot files grouped by directory.

    root: optional path override (for testing non-existent or alternate directories).
    """
    from pathlib import Path as _Path
    override = _Path(root) if root is not None else None
    return {"tree": robot_service.list_tree(root=override)}


@router.get("/suites")
def list_suites():
    """Return a flat list of all .robot suites (legacy)."""
    return {"suites": robot_service.list_suites()}


@router.get("/categorized")
def get_categorized():
    """Return .robot test cases grouped by category with descriptions."""
    return {
        "categories": robot_service.list_categorized(),
        "robot_dir":  str(settings.robot_script_dir),
    }


@router.get("/test-lists")
def get_test_lists():
    """Return predefined CI test suites from test_lists/ directory."""
    return {
        "test_lists": robot_service.list_test_lists(),
        "robot_dir":  str(settings.robot_script_dir),
    }


@router.get("/reports")
def list_reports():
    return {"reports": robot_service.list_reports()}


@router.post("/run")
async def run_suites(req: RunRequest):
    """
    Execute one or more Robot suites synchronously (or dry-run to preview command).
    Validates paths and variable values; rejects path traversal and shell injection.
    Supports include_tags for test_list-style filtering.
    """
    result = await robot_service.run_async(
        suites=req.suites,
        variables=req.variables,
        dry_run=req.dry_run,
        include_tags=req.include_tags,
        test_names=req.test_names,
    )
    if not result.get("ok"):
        err = result.get("error", "")
        for keyword in ("traversal", "disallowed", "invalid"):
            if keyword in err.lower():
                raise HTTPException(status_code=400, detail=err)
    return result


@router.post("/stream-run")
async def start_stream_run(req: StreamRunRequest):
    """
    Start a Robot run as an async subprocess and return a run_id.
    Connect to /api/robot/ws/logs/{run_id} to receive live stdout.
    Supports include_tags for test_list-style filtering.
    """
    ok, err, run_id = await robot_service.start_streaming_run(
        suites=req.suites,
        variables=req.variables,
        include_tags=req.include_tags,
        test_names=req.test_names,
    )
    if not ok:
        if any(k in err.lower() for k in ("traversal", "disallowed", "invalid")):
            raise HTTPException(status_code=400, detail=err)
        raise HTTPException(status_code=500, detail=err)
    return {"ok": True, "run_id": run_id}


@router.get("/run/{run_id}/status")
def get_run_status(run_id: str):
    """Check if a streaming run is still active."""
    info = robot_service.get_run_info(run_id)
    if not info:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    proc = info["process"]
    return {
        "active":  proc.returncode is None,
        "run_id":  run_id,
        "command": info.get("command", ""),
        "out_dir": info.get("out_dir", ""),
    }


@router.websocket("/ws/logs/{run_id}")
async def robot_log_stream(websocket: WebSocket, run_id: str):
    """WebSocket: streams live stdout from a running Robot test identified by run_id."""
    await websocket.accept()
    try:
        await robot_service.stream_logs_to_websocket(run_id, websocket)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
