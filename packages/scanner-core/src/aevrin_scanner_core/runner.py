"""Two execution backends for the same scanner adapters.

`run_container` runs each tool in its own disposable `docker run --rm`
container — the default, and what local/self-hosted deployments use.

`run_local_command` runs the tool as a plain subprocess against a binary
installed directly in the host image. This exists because Railway (and
similar PaaS runtimes) run non-privileged containers with no
Docker-in-Docker support — `docker run` simply isn't available there. When
Docker isn't an option, every scanner binary is baked into apps/api's own
Dockerfile at build time instead (see apps/api/Dockerfile), and each
adapter's `build_local_command()` runs it directly against a temp-directory
clone. This mode never installs dependencies from or executes code out of
the scanned repo — only the fixed set of static-analysis binaries run, same
as in Docker mode, just without container-level isolation. Select the mode
via the `AEVRIN_EXECUTOR` env var (`docker`, the default, or `subprocess`).

Both backends isolate failures per tool: a crashing scanner raises
ToolExecutionError, which the orchestrator (apps/api) catches per-adapter so
one broken scanner never takes down the rest of the scan.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field


def get_executor_mode() -> str:
    mode = os.environ.get("AEVRIN_EXECUTOR", "docker").lower()
    if mode not in ("docker", "subprocess"):
        raise ValueError(f"AEVRIN_EXECUTOR must be 'docker' or 'subprocess', got {mode!r}")
    return mode


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


@dataclass
class LocalCommandSpec:
    binary: str
    args: list[str]
    cwd: str | None = None  # defaults to the target dir at call time
    timeout_s: int = 120
    env: dict[str, str] = field(default_factory=dict)
    ok_exit_codes: tuple[int, ...] = (0,)


def _resource_limits() -> None:  # pragma: no cover - exercised only on Linux/macOS at runtime
    """preexec_fn: caps what a scanner subprocess can consume, since there's
    no per-tool container ceiling in this mode. Deliberately does NOT set
    RLIMIT_AS (virtual address space) — confirmed live that it kills
    gitleaks (and likely other Go binaries using WASM runtimes like
    wazero/go-re2, which reserve large virtual address space unrelated to
    actual physical memory use). Real memory protection here comes from
    Railway's own container-level cgroup limit (RSS-based, not virtual) —
    RLIMIT_CPU/NPROC plus the subprocess timeout are what's safe to enforce
    at this layer."""
    import resource

    resource.setrlimit(resource.RLIMIT_NPROC, (512, 512))
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))


def run_local_command(tool: str, spec: LocalCommandSpec, target_dir: str) -> tuple[str, str, int]:
    """Runs one scanner as a plain subprocess (Railway / non-Docker mode).
    Returns (stdout, stderr, exit_code); raises ToolExecutionError the same
    way run_container does, so callers don't need to know which mode ran."""
    cmd = [spec.binary, *spec.args]
    env = {**os.environ, **spec.env}
    try:
        proc = subprocess.run(
            cmd,
            cwd=spec.cwd or target_dir,
            capture_output=True,
            text=True,
            timeout=spec.timeout_s,
            env=env,
            check=False,
            preexec_fn=_resource_limits if os.name == "posix" else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolExecutionError(
            tool, f"timed out after {spec.timeout_s}s: {shlex.join(cmd)}"
        ) from exc
    except FileNotFoundError as exc:
        raise ToolExecutionError(tool, f"binary '{spec.binary}' not found on host") from exc

    if proc.returncode not in spec.ok_exit_codes:
        raise ToolExecutionError(
            tool,
            f"exited {proc.returncode} (expected one of {spec.ok_exit_codes})",
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    return proc.stdout, proc.stderr, proc.returncode
