"""A stopped Docker daemon should not fail a scanner that is installed.

Every adapter has had a subprocess-mode command for as long as it has had a
container spec, but the choice between them was one global env var defaulting
to "docker". So `aevrin scan` on a laptop with Docker Desktop closed failed
every tool, including ones sitting on PATH, and reported an incomplete scan
it did not need to be.
"""

from __future__ import annotations

import pytest

from aevrin_scanner_core.adapters import BanditAdapter, GitleaksAdapter, SemgrepAdapter
from aevrin_scanner_core.execution import runner
from aevrin_scanner_core.execution.runner import ToolExecutionError, resolve_execution


@pytest.fixture(autouse=True)
def _no_cached_probe(monkeypatch):
    monkeypatch.delenv("AEVRIN_EXECUTOR", raising=False)
    # Guarded on both sides: monkeypatch restores the real function *after*
    # this fixture tears down, so by then the attribute may still be a stub
    # that has no cache to clear.
    _clear()
    yield
    _clear()


def _clear() -> None:
    clear = getattr(runner.docker_available, "cache_clear", None)
    if clear:
        clear()


def _docker(monkeypatch, up: bool):
    monkeypatch.setattr(runner, "docker_available", lambda: up)


def _on_path(monkeypatch, present: set[str]):
    monkeypatch.setattr(runner.shutil, "which", lambda b: f"/usr/bin/{b}" if b in present else None)


def test_docker_running_still_wins(monkeypatch):
    """Unchanged behaviour where Docker works: a container is the isolated way
    to run an untrusted scanner over untrusted source."""
    _docker(monkeypatch, True)
    _on_path(monkeypatch, {"semgrep"})
    assert resolve_execution("semgrep", "semgrep") == "docker"


def test_docker_down_falls_back_to_an_installed_binary(monkeypatch):
    _docker(monkeypatch, False)
    _on_path(monkeypatch, {"semgrep"})
    assert resolve_execution("semgrep", "semgrep") == "subprocess"


def test_docker_down_and_nothing_installed_says_how_to_fix_it(monkeypatch):
    """The old failure named the npipe path Docker could not open. True, and
    useless to someone who just wants the scan to run."""
    _docker(monkeypatch, False)
    _on_path(monkeypatch, set())

    with pytest.raises(ToolExecutionError) as excinfo:
        resolve_execution("semgrep", "semgrep")

    message = str(excinfo.value)
    assert "no Docker daemon" in message
    assert "pip install semgrep" in message


def test_the_fallback_is_decided_per_tool(monkeypatch):
    """One machine can have bandit and not trivy. Deciding globally meant the
    installed one was skipped along with the missing one."""
    _docker(monkeypatch, False)
    _on_path(monkeypatch, {"bandit"})

    assert resolve_execution("bandit", "bandit") == "subprocess"
    with pytest.raises(ToolExecutionError):
        resolve_execution("trivy", "trivy")


@pytest.mark.parametrize("pinned", ["docker", "subprocess"])
def test_an_explicit_mode_pins_it_and_disables_the_fallback(monkeypatch, pinned):
    """The API container sets this: its scanners are baked in and there is no
    Docker inside it to fall back from, so probing for one is wasted work."""
    monkeypatch.setenv("AEVRIN_EXECUTOR", pinned)
    _docker(monkeypatch, False)
    _on_path(monkeypatch, set())
    assert resolve_execution("semgrep", "semgrep") == pinned


def test_an_unknown_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("AEVRIN_EXECUTOR", "podman")
    with pytest.raises(ValueError, match="AEVRIN_EXECUTOR"):
        resolve_execution("semgrep", "semgrep")


@pytest.mark.parametrize(
    ("adapter", "expected"),
    [(SemgrepAdapter, "semgrep"), (BanditAdapter, "bandit"), (GitleaksAdapter, "gitleaks")],
)
def test_local_binary_comes_from_the_command_that_would_run(adapter, expected):
    """Derived rather than declared, so a rename of the binary in
    build_local_command cannot leave the PATH check probing the old name."""
    assert adapter().local_binary() == expected


# --------------------------------------------------------------- false clean


class _FakeProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_a_refused_container_is_never_read_as_a_clean_run(monkeypatch):
    """The worst outcome this scanner can produce.

    `docker run` exits with the status of the command it could not start, and
    osv-scanner and bandit both list 1 as a normal "found something" code. So
    a stopped daemon returned exit 1 with empty stdout, which passed the
    exit-code check, and osv-scanner's parser turns empty output into an empty
    result set. The scan reported no dependency vulnerabilities from a scanner
    that had never run, and scored it 100/100.
    """
    from aevrin_scanner_core.execution.runner import DockerRunSpec, run_container

    daemon_down = (
        "docker: failed to connect to the docker API at "
        "npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct "
        "and if the daemon is running."
    )
    monkeypatch.setattr(
        runner.subprocess, "run", lambda *a, **k: _FakeProc(1, stdout="", stderr=daemon_down)
    )

    spec = DockerRunSpec(image="osv:latest", args=[], ok_exit_codes=(0, 1))
    with pytest.raises(ToolExecutionError) as excinfo:
        run_container("osv-scanner", spec)

    assert "container never started" in str(excinfo.value)


def test_a_real_findings_exit_code_still_counts_as_a_run(monkeypatch):
    """The guard has to key on the daemon message, not on exit 1, or every
    scanner that signals findings that way would start reporting as broken."""
    from aevrin_scanner_core.execution.runner import DockerRunSpec, run_container

    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *a, **k: _FakeProc(1, stdout='{"results": []}', stderr="2 vulnerabilities found"),
    )

    spec = DockerRunSpec(image="osv:latest", args=[], ok_exit_codes=(0, 1))
    stdout, _stderr, code = run_container("osv-scanner", spec)

    assert code == 1
    assert stdout == '{"results": []}'
