"""Disposable-container execution.

Every scanner runs in its own `docker run --rm` invocation with resource and
time limits. Failures are isolated per tool: a crashing container raises
ToolExecutionError, which the orchestrator (apps/api) catches per-adapter so
one broken scanner never takes down the rest of the scan.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field


class ToolExecutionError(Exception):
    def __init__(self, tool: str, message: str, stdout: str = "", stderr: str = ""):
        self.tool = tool
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f"{tool}: {message}")


@dataclass
class DockerRunSpec:
    image: str
    args: list[str]
    # host_path -> (container_path, read_only)
    mounts: dict[str, tuple[str, bool]] = field(default_factory=dict)
    network_enabled: bool = False
    timeout_s: int = 120
    mem_limit: str = "768m"
    cpus: str = "1.0"
    workdir: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    # Some tools (semgrep, trivy, osv-scanner...) exit non-zero when findings
    # are present — that's not an execution failure. Adapters declare which
    # exit codes are "ran successfully" vs. "actually crashed".
    ok_exit_codes: tuple[int, ...] = (0,)


def run_container(tool: str, spec: DockerRunSpec) -> tuple[str, str, int]:
    """Runs one scanner container to completion. Returns (stdout, stderr, exit_code).

    Raises ToolExecutionError on timeout, docker-launch failure, or an exit
    code the adapter didn't declare as acceptable.
    """
    cmd = [
        "docker",
        "run",
        "--rm",
        "--memory",
        spec.mem_limit,
        "--cpus",
        spec.cpus,
        "--pids-limit",
        "256",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
    ]
    cmd += ["--network", "bridge" if spec.network_enabled else "none"]
    for host_path, (container_path, read_only) in spec.mounts.items():
        mount_flag = f"{host_path}:{container_path}" + (":ro" if read_only else "")
        cmd += ["-v", mount_flag]
    if spec.workdir:
        cmd += ["-w", spec.workdir]
    for key, value in spec.env.items():
        cmd += ["-e", f"{key}={value}"]
    cmd += [spec.image, *spec.args]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=spec.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(
            tool, f"timed out after {spec.timeout_s}s: {shlex.join(cmd)}"
        ) from exc
    except FileNotFoundError as exc:
        raise ToolExecutionError(tool, "docker CLI not found on host") from exc

    if proc.returncode not in spec.ok_exit_codes:
        raise ToolExecutionError(
            tool,
            f"exited {proc.returncode} (expected one of {spec.ok_exit_codes})",
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    return proc.stdout, proc.stderr, proc.returncode
