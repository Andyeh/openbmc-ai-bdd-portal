"""
Robot Framework API Router
"""
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from backend.services.robot_service import robot_service

router = APIRouter(prefix="/api/robot", tags=["Robot"])


class RunRequest(BaseModel):
    suite_path: str
    extra_vars: Optional[dict] = None


@router.get("/suites")
def list_suites():
    return {"suites": robot_service.list_suites()}


@router.get("/reports")
def list_reports():
    return {"reports": robot_service.list_reports()}


@router.post("/run")
async def run_suite(req: RunRequest):
    result = await robot_service.run_async(req.suite_path, req.extra_vars)
    return result
