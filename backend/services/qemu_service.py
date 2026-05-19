"""
QEMU Service — asyncio-based process management with structured launch params.
"""
import asyncio
import os
import pty
import shlex
import signal
import subprocess
import tempfile
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.core.config import settings


# ── Preset definitions (mirrors boot-qemu.sh logic) ──────────────────────────

# Default host-side ports (matching real QEMU run command)
# Guest ports are fixed; host ports are configurable by the user.
DEFAULT_HOST_SSH   = 2222
DEFAULT_HOST_HTTPS = 2443
DEFAULT_HOST_IPMI  = 2623

PRESETS: dict[str, dict] = {
    "ast2700-default": {
        "label": "ast2700-default (aarch64)",
        "machine": "ast2700a1-evb",
        "memory": "1G",
        "binary": str(settings.qemu_binary),
        "image": "obmc-phosphor-image-ast2700-default.static.mtd",       # symlink — always points to latest build
        "extra_args": "-serial mon:stdio -serial null -display none",
        "host_ssh_port":   DEFAULT_HOST_SSH,
        "host_https_port": DEFAULT_HOST_HTTPS,
        "host_ipmi_port":  DEFAULT_HOST_IPMI,
    },
    "romulus": {
        "label": "romulus (arm)",
        "machine": "romulus-bmc",
        "memory": "256M",
        "binary": str(settings.upstream_workspace / "tmp/sysroots/x86_64-linux/usr/bin/qemu-system-arm"),
        "image": "obmc-phosphor-image-romulus.static.mtd",  # symlink
        "extra_args": "-nographic",
        "host_ssh_port":   DEFAULT_HOST_SSH,
        "host_https_port": DEFAULT_HOST_HTTPS,
        "host_ipmi_port":  DEFAULT_HOST_IPMI,
    },
}


# ── Session dataclass ─────────────────────────────────────────────────────────

@dataclass
class QemuSession:
    pid: int
    machine: str
    image: str
    command: str                                        # full assembled command
    tmp_drive: Optional[str] = None                    # /tmp copy of the image
    docker_container_name: Optional[str] = None        # set when running in Docker
    started_at: datetime = field(default_factory=datetime.utcnow)
    log_lines: list[str] = field(default_factory=list)
    process: Optional[asyncio.subprocess.Process] = None
    master_fd: Optional[int] = None                    # PTY master file descriptor

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None


# ── Symlink-preferred image names (no date tag) ──────────────────────────────

# These symlinks are maintained by bitbake and always point to the latest build.
_PREFERRED_SYMLINKS = {
    "obmc-phosphor-image-ast2700-default.static.mtd",
    "obmc-phosphor-image-romulus.static.mtd",
}


# ── Launch request params ─────────────────────────────────────────────────────

@dataclass
class LaunchParams:
    machine: str
    image: str                  # filename relative to qemu_image_dir
    memory: str = "1G"
    binary: Optional[str] = None
    extra_args: str = ""
    dry_run: bool = False
    use_nic: bool = True        # attach NIC with port forwarding
    # Host-side port mapping (guest ports are fixed: 22/443/623)
    host_ssh_port:   int = DEFAULT_HOST_SSH
    host_https_port: int = DEFAULT_HOST_HTTPS
    host_ipmi_port:  int = DEFAULT_HOST_IPMI
    # Docker mode
    use_docker: bool = True
    docker_image: str = "crops/poky:ubuntu-22.04"
    docker_container_name: str = "qemu-portal-session"


# ── QEMU Service ──────────────────────────────────────────────────────────────

class QemuService:
    """Async QEMU process lifecycle manager."""

    def __init__(self):
        self._session: Optional[QemuSession] = None
        self._log_subscribers: list[asyncio.Queue] = []

    # ── Status ────────────────────────────────────────────────────

    def status(self) -> dict:
        if self._session is None or not self._session.is_alive():
            return {"running": False}
        s = self._session
        return {
            "running": True,
            "pid": s.pid,
            "machine": s.machine,
            "image": s.image,
            "command": s.command,
            "started_at": s.started_at.isoformat(),
        }

    # ── Image list ────────────────────────────────────────────────

    def list_images(self) -> list[str]:
        """Dynamically scan all deploy image subdirectories under the parent build directory.

        Lists preferred symlink names from any machine under build/ (e.g., ast2700-default and romulus).
        """
        build_dir = settings.upstream_workspace.parent  # /home/andyeh/workspace/openbmc/build
        if not build_dir.exists():
            return []

        results: list[str] = []

        # Scan build/*/tmp/deploy/images/* for preferred symlinks
        # This resolves to directories like build/ast2700-default/tmp/deploy/images/ast2700-default
        for deploy_dir in build_dir.glob("*/tmp/deploy/images/*"):
            if not deploy_dir.is_dir():
                continue
            for name in _PREFERRED_SYMLINKS:
                p = deploy_dir / name
                if p.exists() and name not in results:
                    results.append(name)

        # Fallback: scan for non-symlink files without date tags in those directories
        import re
        _date_tag = re.compile(r'\d{14}')
        for deploy_dir in build_dir.glob("*/tmp/deploy/images/*"):
            if not deploy_dir.is_dir():
                continue
            for f in deploy_dir.iterdir():
                if f.is_symlink():
                    continue
                if f.suffix not in (".img", ".qcow2", ".flash", ".mtd"):
                    continue
                if _date_tag.search(f.name):
                    continue
                if f.name not in results:
                    results.append(f.name)

        return sorted(results)

    def _resolve_image_path(self, image_name: str) -> Optional[Path]:
        """Find the absolute path of an image name under any build/*/tmp/deploy/images/* folder."""
        build_dir = settings.upstream_workspace.parent
        for deploy_dir in build_dir.glob("*/tmp/deploy/images/*"):
            if not deploy_dir.is_dir():
                continue
            p = deploy_dir / image_name
            if p.exists():
                return p
        return None

    # ── Preset list ───────────────────────────────────────────────

    def list_presets(self) -> list[dict]:
        return [{"id": k, **v} for k, v in PRESETS.items()]

    # ── Command builder ───────────────────────────────────────────

    def _to_container_path(self, host_path: str) -> str:
        """Convert a host absolute path to container path under /workdir.

        Mount: /home/andyeh/workspace/openbmc  →  /workdir
        e.g.  /home/andyeh/workspace/openbmc/build/ast2700-default/tmp/...
              → /workdir/build/ast2700-default/tmp/...
        """
        openbmc_root = str(settings.upstream_workspace.parent.parent)
        return host_path.replace(openbmc_root, "/workdir", 1)

    def _qemu_args(self, params: LaunchParams, drive_path: str) -> list[str]:
        """Return the QEMU argument list (without the binary itself)."""
        args = ["-m", params.memory, "-machine", params.machine]
        args += ["-drive", f"file={drive_path},if=mtd,format=raw"]
        if params.use_nic:
            net_fwd = (
                f"hostfwd=tcp::{params.host_ssh_port}-:22,"
                f"hostfwd=tcp::{params.host_https_port}-:443,"
                f"hostfwd=udp::{params.host_ipmi_port}-:623"
            )
            args += ["-net", "nic,netdev=net0"]
            args += ["-netdev", f"user,id=net0,{net_fwd}"]
        if params.extra_args:
            args += shlex.split(params.extra_args)
        return args

    def build_command(self, params: LaunchParams, drive_path: str) -> list[str]:
        """Assemble direct QEMU command (host execution)."""
        binary = params.binary or str(settings.qemu_binary)
        return [binary] + self._qemu_args(params, drive_path)

    def build_docker_command(self, params: LaunchParams, host_image_path: Path, tty: bool = False) -> list[str]:
        """Assemble 'docker run' command that runs QEMU inside a container.

        Volume mount: /home/andyeh/workspace/openbmc → /workdir
        Ports:  host:{ssh,https,ipmi}  →  container:{ssh,https,ipmi}
        Entrypoint: QEMU binary (path converted to container path)
        """
        openbmc_root = str(settings.upstream_workspace.parent.parent)
        binary = params.binary or str(settings.qemu_binary)
        container_binary = self._to_container_path(binary)
        container_image  = self._to_container_path(str(host_image_path))

        # Dynamically get current host user UID and GID to avoid permission issues
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gid = os.getgid() if hasattr(os, "getgid") else 1000

        docker_cmd = [
            "docker", "run", "--rm",
            "--name", params.docker_container_name,
            "-u", f"{uid}:{gid}",
            "-p", f"{params.host_ssh_port}:{params.host_ssh_port}",
            "-p", f"{params.host_https_port}:{params.host_https_port}",
            "-p", f"{params.host_ipmi_port}:{params.host_ipmi_port}/udp",
            "-v", f"{openbmc_root}:/workdir",
            "-it" if tty else "-i",
            "--entrypoint", container_binary,
            params.docker_image,
        ]
        docker_cmd += self._qemu_args(params, container_image)
        return docker_cmd

    def command_preview(self, params: LaunchParams) -> dict:
        """Return assembled command string without executing or copying image."""
        image_path = self._resolve_image_path(params.image) or (settings.qemu_image_dir / params.image)
        if params.use_docker:
            cmd = self.build_docker_command(params, image_path, tty=True)
        else:
            cmd = self.build_command(params, str(image_path))
        return {
            "command": shlex.join(cmd),
            "command_list": cmd,
            "image_path": str(image_path),
        }

    # ── Launch ────────────────────────────────────────────────────

    async def launch(self, params: LaunchParams) -> dict:
        """Launch QEMU — either directly on host or inside Docker container."""
        if self._session and self._session.is_alive():
            return {"ok": False, "error": "QEMU is already running"}

        image_path = self._resolve_image_path(params.image)
        if not image_path or not image_path.exists():
            return {"ok": False, "error": f"Image not found: {params.image}"}

        # ── Dry-run ────────────────────────────────────────────────────────────
        if params.dry_run:
            if params.use_docker:
                cmd = self.build_docker_command(params, image_path, tty=True)
            else:
                cmd = self.build_command(params, str(image_path))
            return {
                "ok": True,
                "dry_run": True,
                "mode": "docker" if params.use_docker else "host",
                "command": shlex.join(cmd),
                "command_list": cmd,
                "image_path": str(image_path),
            }

        # ── Docker mode ────────────────────────────────────────────────────────
        if params.use_docker:
            # Force remove any conflicting container with the same name before starting
            try:
                subprocess.run(
                    ["docker", "rm", "-f", params.docker_container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            except Exception:
                pass

            # Open PTY master/slave pair to simulate a real terminal TTY
            master_fd, slave_fd = pty.openpty()
            cmd = self.build_docker_command(params, image_path, tty=True)
            cmd_str = shlex.join(cmd)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                )
            except FileNotFoundError:
                os.close(master_fd)
                os.close(slave_fd)
                return {"ok": False, "error": "docker not found — is Docker installed?"}
            except Exception as exc:
                os.close(master_fd)
                os.close(slave_fd)
                return {"ok": False, "error": str(exc)}
            finally:
                # Close slave FD in parent process; master FD is kept open to read/write
                os.close(slave_fd)

            self._session = QemuSession(
                pid=proc.pid,
                machine=params.machine,
                image=params.image,
                command=cmd_str,
                docker_container_name=params.docker_container_name,
                process=proc,
                master_fd=master_fd,
            )
            asyncio.create_task(self._read_stdout(self._session))
            return {"ok": True, "pid": proc.pid, "command": cmd_str, "mode": "docker"}

        # ── Host mode: copy image to /tmp to protect original ──────────────────
        tmp_path = f"/tmp/qemu-{params.machine}-{image_path.name}"
        cmd = self.build_command(params, tmp_path)
        cmd_str = shlex.join(cmd)
        try:
            shutil.copy2(str(image_path), tmp_path)
        except Exception as e:
            return {"ok": False, "error": f"Failed to copy image to /tmp: {e}"}

        # Open PTY master/slave pair to simulate a real terminal TTY
        master_fd, slave_fd = pty.openpty()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
            )
        except FileNotFoundError:
            os.close(master_fd)
            os.close(slave_fd)
            os.unlink(tmp_path)
            return {"ok": False, "error": f"QEMU binary not found: {cmd[0]}"}
        except Exception as exc:
            os.close(master_fd)
            os.close(slave_fd)
            os.unlink(tmp_path)
            return {"ok": False, "error": str(exc)}
        finally:
            os.close(slave_fd)

        self._session = QemuSession(
            pid=proc.pid,
            machine=params.machine,
            image=params.image,
            command=cmd_str,
            tmp_drive=tmp_path,
            process=proc,
            master_fd=master_fd,
        )
        asyncio.create_task(self._read_stdout(self._session))
        return {"ok": True, "pid": proc.pid, "command": cmd_str, "mode": "host"}

    # ── Stop ──────────────────────────────────────────────────────

    def stop(self) -> dict:
        if not self._session or not self._session.is_alive():
            return {"ok": False, "error": "No running QEMU session"}
        try:
            if self._session.docker_container_name:
                # Docker mode: gracefully stop the named container
                subprocess.run(
                    ["docker", "stop", self._session.docker_container_name],
                    timeout=15, check=False,
                )
            else:
                # Host mode: kill the entire process group
                pgid = os.getpgid(self._session.process.pid)
                os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        finally:
            if self._session.master_fd is not None:
                try:
                    os.close(self._session.master_fd)
                except OSError:
                    pass
            if self._session.tmp_drive and Path(self._session.tmp_drive).exists():
                try:
                    os.unlink(self._session.tmp_drive)
                except OSError:
                    pass
            self._session = None
        return {"ok": True}

    # ── Log streaming ─────────────────────────────────────────────

    async def _read_stdout(self, session: QemuSession):
        """Background task: read process stdout from PTY master and fan-out to all subscribers."""
        loop = asyncio.get_running_loop()
        try:
            while session.is_alive() and session.master_fd is not None:
                # Read chunks from the PTY master. Since os.read can block, run in executor.
                data = await loop.run_in_executor(None, lambda: os.read(session.master_fd, 4096))
                if not data:
                    break
                text = data.decode("utf-8", errors="replace")
                session.log_lines.append(text)
                
                # Fan out to all connected WebSocket queues
                dead = []
                for q in self._log_subscribers:
                    try:
                        q.put_nowait(text)
                    except asyncio.QueueFull:
                        dead.append(q)
                for q in dead:
                    self._log_subscribers.remove(q)
        except OSError:
            pass
        except Exception:
            pass

    def get_log_history(self) -> list[str]:
        if not self._session:
            return []
        return list(self._session.log_lines)

    async def stream_logs(self, websocket):
        """Stream live QEMU logs to/from a WebSocket client (Bidirectional Terminal)."""
        if not self._session:
            await websocket.send_text("[ERROR] No running QEMU session\r\n")
            return

        # Send existing history buffer first
        for line in self._session.log_lines:
            await websocket.send_text(line)

        # ── Task 1: Read keyboard inputs from WS and write to QEMU's PTY master ─
        async def ws_reader():
            try:
                while self._session and self._session.is_alive():
                    data = await websocket.receive_text()
                    if self._session.master_fd is not None:
                        # Write raw keyboard input directly to the PTY master
                        os.write(self._session.master_fd, data.encode('utf-8'))
            except Exception:
                pass

        # ── Task 2: Broadcast live serial output to WS ─────────────────────────
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._log_subscribers.append(q)

        reader_task = asyncio.create_task(ws_reader())
        try:
            while self._session and self._session.is_alive():
                try:
                    line = await asyncio.wait_for(q.get(), timeout=1.0)
                    await websocket.send_text(line)
                except asyncio.TimeoutError:
                    continue
        finally:
            reader_task.cancel()
            if q in self._log_subscribers:
                self._log_subscribers.remove(q)


qemu_service = QemuService()
