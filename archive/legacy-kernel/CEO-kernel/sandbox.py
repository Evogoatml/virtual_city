#!/usr/bin/env python3
"""
Sandbox Manager
Isolates tool execution in restricted environments.
Tries: Docker (with SDK) → Firejail → bwrap → restricted subprocess
"""

import os
import shutil
import subprocess
import tempfile
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    killed: bool = False
    kill_reason: str = ""


class SandboxManager:
    """Manages sandboxed execution with resource bounds."""

    def __init__(self, default_timeout: int = 60):
        self.default_timeout = default_timeout
        self.backend = self._detect_backend()
        self.output_dir = "/tmp/bot-scans"
        os.makedirs(self.output_dir, exist_ok=True)

    def _detect_backend(self) -> str:
        # Check Docker binary + Python SDK
        if shutil.which("docker"):
            try:
                import docker as _docker
                # Quick connectivity test
                _docker.from_env().version()
                return "docker"
            except Exception:
                pass  # Docker binary exists but SDK missing or daemon down

        if shutil.which("firejail"):
            return "firejail"
        if shutil.which("bwrap"):
            return "bwrap"
        return "restricted"

    def execute(
        self,
        command: str,
        timeout: int = 60,
        memory_mb: int = 512,
        network: bool = False,
        allowed_paths: Optional[list] = None,
    ) -> SandboxResult:
        """Execute command in sandbox."""
        if self.backend == "docker":
            return self._docker_run(command, timeout, memory_mb, network)
        elif self.backend == "firejail":
            return self._firejail_run(command, timeout, memory_mb, network)
        elif self.backend == "bwrap":
            return self._bwrap_run(command, timeout, network)
        else:
            return self._restricted_run(command, timeout)

    def _docker_run(
        self, command: str, timeout: int, memory_mb: int, network: bool
    ) -> SandboxResult:
        try:
            import docker
            client = docker.from_env()
            net_mode = "bridge" if network else "none"
            tmpdir = tempfile.mkdtemp(prefix="bot_run_", dir=self.output_dir)

            container = client.containers.run(
                image="parrotsec/core",
                command=command,
                network_mode=net_mode,
                mem_limit=f"{memory_mb}m",
                cpu_quota=100000,
                detach=True,
                remove=False,
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["NET_RAW", "NET_BIND_SERVICE"] if network else [],
                volumes={tmpdir: {"bind": "/output", "mode": "rw"}},
            )

            start = time.time()
            try:
                result = container.wait(timeout=timeout)
                logs = container.logs().decode(errors="replace")
                duration = int((time.time() - start) * 1000)
                exit_code = result.get("StatusCode", -1)
                container.remove(force=True)
                return SandboxResult(
                    exit_code=exit_code,
                    stdout=logs,
                    stderr="",
                    duration_ms=duration,
                )
            except Exception:
                container.kill()
                container.remove(force=True)
                return SandboxResult(
                    exit_code=-1,
                    stdout="",
                    stderr="Sandbox timeout",
                    duration_ms=int((time.time() - start) * 1000),
                    killed=True,
                    kill_reason="timeout",
                )
        except Exception as e:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=0,
                killed=True,
                kill_reason="docker_error",
            )

    def _firejail_run(
        self, command: str, timeout: int, memory_mb: int, network: bool
    ) -> SandboxResult:
        net_flag = "--net=eth0" if network else "--net=none"
        cmd = [
            "firejail",
            "--quiet",
            "--private",
            net_flag,
            f"--rlimit-as={memory_mb}m",
            f"--rlimit-cpu={timeout}",
            f"--timeout=00:00:{timeout}",
            "--whitelist=/tmp/bot-scans",
            "--caps.drop=all",
            "--seccomp",
            "--noroot",
            "--",
            "sh", "-c", command,
        ]
        return self._run_subprocess(cmd, timeout)

    def _bwrap_run(self, command: str, timeout: int, network: bool) -> SandboxResult:
        """Full filesystem sandbox: read-only root, writable /tmp only."""
        cmd = [
            "bwrap",
            "--ro-bind", "/", "/",
            "--tmpfs", "/tmp",
            "--tmpfs", "/var/tmp",
            "--dev", "/dev",
            "--proc", "/proc",
            "--die-with-parent",
            "--new-session",
            "--cap-drop", "ALL",
        ]
        if not network:
            cmd.append("--unshare-net")
        cmd.extend(["--", "sh", "-c", command])
        return self._run_subprocess(cmd, timeout)

    def _restricted_run(self, command: str, timeout: int) -> SandboxResult:
        """Fallback with no real sandbox — restricted subprocess only."""
        return self._run_subprocess(["sh", "-c", command], timeout)

    def _run_subprocess(self, cmd: list, timeout: int) -> SandboxResult:
        start = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            duration = int((time.time() - start) * 1000)
            return SandboxResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_ms=duration,
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr="Sandbox timeout",
                duration_ms=int((time.time() - start) * 1000),
                killed=True,
                kill_reason="timeout",
            )
        except Exception as e:
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration_ms=0,
                killed=True,
                kill_reason="exception",
            )



