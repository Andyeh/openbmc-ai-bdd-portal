"""
QEMU API Router — full launch lifecycle with structured JSON params.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional

from backend.services.qemu_service import (
    qemu_service, LaunchParams,
    DEFAULT_HOST_SSH, DEFAULT_HOST_HTTPS, DEFAULT_HOST_IPMI,
)

router = APIRouter(prefix="/api/qemu", tags=["QEMU"])


# ── Request / Response models ────────────────────────────────────────────────

class LaunchRequest(BaseModel):
    machine: str
    image: str
    memory: str = "1G"
    binary: Optional[str] = None
    extra_args: str = ""
    dry_run: bool = False
    use_nic: bool = True
    host_ssh_port:   int = DEFAULT_HOST_SSH
    host_https_port: int = DEFAULT_HOST_HTTPS
    host_ipmi_port:  int = DEFAULT_HOST_IPMI
    use_docker: bool = True
    docker_image: str = "crops/poky:ubuntu-22.04"
    docker_container_name: str = "qemu-portal-session"

    def to_params(self) -> LaunchParams:
        return LaunchParams(
            machine=self.machine,
            image=self.image,
            memory=self.memory,
            binary=self.binary,
            extra_args=self.extra_args,
            dry_run=self.dry_run,
            use_nic=self.use_nic,
            host_ssh_port=self.host_ssh_port,
            host_https_port=self.host_https_port,
            host_ipmi_port=self.host_ipmi_port,
            use_docker=self.use_docker,
            docker_image=self.docker_image,
            docker_container_name=self.docker_container_name,
        )


class BuildCommandRequest(BaseModel):
    machine: str
    image: str
    memory: str = "1G"
    binary: Optional[str] = None
    extra_args: str = ""
    use_nic: bool = True
    host_ssh_port:   int = DEFAULT_HOST_SSH
    host_https_port: int = DEFAULT_HOST_HTTPS
    host_ipmi_port:  int = DEFAULT_HOST_IPMI
    use_docker: bool = True
    docker_image: str = "crops/poky:ubuntu-22.04"
    docker_container_name: str = "qemu-portal-session"

    def to_params(self) -> LaunchParams:
        return LaunchParams(
            machine=self.machine,
            image=self.image,
            memory=self.memory,
            binary=self.binary,
            extra_args=self.extra_args,
            use_nic=self.use_nic,
            host_ssh_port=self.host_ssh_port,
            host_https_port=self.host_https_port,
            host_ipmi_port=self.host_ipmi_port,
            use_docker=self.use_docker,
            docker_image=self.docker_image,
            docker_container_name=self.docker_container_name,
        )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status")
def get_status():
    return qemu_service.status()


@router.get("/images")
def list_images():
    return {"images": qemu_service.list_images()}


@router.get("/presets")
def list_presets():
    """Return available machine presets (mirrors boot-qemu.sh profiles)."""
    return {"presets": qemu_service.list_presets()}


@router.post("/build-command")
def build_command(req: BuildCommandRequest):
    """Preview the assembled QEMU command without executing it."""
    return qemu_service.command_preview(req.to_params())


@router.post("/launch")
async def launch_qemu(req: LaunchRequest):
    """Launch QEMU asynchronously with structured parameters."""
    return await qemu_service.launch(req.to_params())


@router.post("/stop")
def stop_qemu():
    return qemu_service.stop()


@router.get("/logs")
def get_log_history():
    """Return buffered log lines from the current session."""
    return {"lines": qemu_service.get_log_history()}


@router.websocket("/ws/logs")
async def qemu_log_stream(websocket: WebSocket):
    """WebSocket: streams live QEMU serial console output."""
    await websocket.accept()
    try:
        await qemu_service.stream_logs(websocket)
    except WebSocketDisconnect:
        pass
