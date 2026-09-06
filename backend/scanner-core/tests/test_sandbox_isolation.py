"""The container an untrusted MCP server runs inside.

Scanning a server means starting it, and starting it means executing code
published by a stranger - npm runs that stranger's `preinstall` and
`postinstall` scripts before a single tool has been enumerated. The API
process holds the Supabase service-role key, which bypasses RLS and is
therefore the entire tenancy boundary, so every assertion here is about one
question: what is a compromise of the scanned server actually worth?

These are unit assertions on the argv handed to `docker run`. They cannot
prove the kernel enforces any of it - only that Aevrin asks for it, every
time, and that a future edit which quietly drops a flag fails loudly rather
than silently widening the blast radius.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from aevrin_scanner_core.execution.runner import DockerRunSpec, ToolExecutionError
from aevrin_scanner_core.mcp import tooltrust


class _Recorder:
    """Captures the argv `run_container` builds, without running Docker."""

    def __init__(self, stdout: str = '{"schema_version":"1.0","policies":[]}') -> None:
        self.cmd: list[str] = []
        self.stdout = stdout

    def __call__(self, cmd, **kwargs):
        self.cmd = list(cmd)

        class _Proc:
            returncode = 0

        proc = _Proc()
        proc.stdout = self.stdout  # type: ignore[attr-defined]
        proc.stderr = ""  # type: ignore[attr-defined]
        return proc


@pytest.fixture
def argv(monkeypatch) -> list[str]:
    recorder = _Recorder()
    monkeypatch.setattr("aevrin_scanner_core.execution.runner.subprocess.run", recorder)
    tooltrust.scan_live_server("npx -y @scope/demo", scan_id=uuid4())
    return recorder.cmd


def test_the_container_inherits_no_aevrin_environment(argv: list[str]) -> None:
    """The one that matters most. `-e` is an explicit allow-list, so the
    service-role key, the provider-key encryption key and any AWS credential
    in the API process are simply not present to be stolen."""
    passed = {argv[i + 1].split("=", 1)[0] for i, a in enumerate(argv) if a == "-e"}
    assert passed <= {"HOME", "NPM_CONFIG_CACHE", "NO_COLOR"}
    for forbidden in ("SUPABASE", "AWS_", "RAZORPAY", "FERNET", "GITHUB_TOKEN", "OPENAI"):
        assert not any(forbidden in a for a in argv)


def test_the_container_is_disposable_and_unprivileged(argv: list[str]) -> None:
    joined = " ".join(argv)
    assert "--rm" in argv
    assert "--read-only" in argv
    assert ["--cap-drop", "ALL"] == [argv[argv.index("--cap-drop")], argv[argv.index("--cap-drop") + 1]]
    assert "no-new-privileges" in joined
    # Not root, even inside a container that is thrown away.
    assert argv[argv.index("--user") + 1] == "10002:10002"


def test_resource_ceilings_are_declared(argv: list[str]) -> None:
    """A hostile server that cannot exfiltrate can still try to exhaust the
    host. Memory, CPU and pid limits make that a bounded nuisance."""
    for flag in ("--memory", "--cpus", "--pids-limit"):
        assert flag in argv, f"{flag} missing"


def test_writable_space_is_tmpfs_and_dies_with_the_container(argv: list[str]) -> None:
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "--tmpfs"]
    assert mounts, "a read-only rootfs needs writable scratch or npx cannot install"
    for mount in mounts:
        assert "nosuid" in mount, f"{mount} should refuse setuid binaries"
        assert "size=" in mount, f"{mount} should be bounded"


def test_nothing_from_the_host_is_mounted_in(argv: list[str]) -> None:
    """No bind mounts at all. There is no repository to share with this
    container - it fetches the package itself - so a mount could only ever
    expose something that should not be exposed."""
    assert "--mount" not in argv


def test_the_engine_image_and_version_are_pinned(argv: list[str]) -> None:
    """A security result that cannot name the engine that produced it cannot
    be supported, and `latest` would silently change findings between scans."""
    assert tooltrust.SCANNER_IMAGE in argv
    assert ":" in tooltrust.SCANNER_IMAGE, "the image must carry an explicit tag"
    assert tooltrust.SCANNER_VERSION


def test_a_hard_timeout_is_enforced_by_the_caller(monkeypatch) -> None:
    """A server that hangs must not hang the scan. The timeout is passed to
    `subprocess.run`, so it is enforced against the container rather than
    depending on the server's own good behaviour."""
    seen: dict[str, object] = {}

    def fake(cmd, **kwargs):
        seen.update(kwargs)

        class _Proc:
            returncode = 0
            stdout = '{"schema_version":"1.0","policies":[]}'
            stderr = ""

        return _Proc()

    monkeypatch.setattr("aevrin_scanner_core.execution.runner.subprocess.run", fake)
    tooltrust.scan_live_server("npx -y @scope/demo", scan_id=uuid4())
    assert seen["timeout"] == tooltrust.LAUNCH_TIMEOUT_S
    assert seen.get("shell") in (None, False), "argv is a list; never a shell string"


def test_a_launch_failure_is_raised_not_swallowed(monkeypatch) -> None:
    """An unavailable sandbox is an unavailable scan, never a scan performed
    without one."""

    def fake(cmd, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr("aevrin_scanner_core.execution.runner.subprocess.run", fake)
    with pytest.raises(tooltrust.ServerLaunchError):
        tooltrust.scan_live_server("npx -y @scope/demo", scan_id=uuid4())


def test_an_unparseable_command_never_reaches_docker(monkeypatch) -> None:
    called = False

    def fake(cmd, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("aevrin_scanner_core.execution.runner.subprocess.run", fake)
    with pytest.raises(tooltrust.ServerLaunchError):
        tooltrust.scan_live_server('npx -y "unterminated', scan_id=uuid4())
    assert not called


def test_network_is_on_because_the_package_must_be_fetched(argv: list[str]) -> None:
    """Documenting the residual exposure rather than pretending it away: the
    container has to reach the registry. Containment comes from it holding no
    credentials, plus IMDSv2's hop limit on the deployed host."""
    assert argv[argv.index("--network") + 1] == "bridge"


def test_the_spec_defaults_stay_closed() -> None:
    """A caller that forgets to harden gets the closed defaults.

    `read_only_rootfs` is deliberately not asserted here: it defaults off
    because the only caller needing it opts in explicitly (asserted above),
    and a default that broke every other container would be worse. Network,
    environment and mounts are the ones that must start empty.
    """
    spec = DockerRunSpec(image="x", args=[])
    assert spec.network_enabled is False
    assert spec.env == {}
    assert spec.mounts == {}
    assert spec.tmpfs == {}
    assert spec.user is None


def test_tool_execution_errors_do_not_leak_credential_shaped_text() -> None:
    """Stage errors are persisted and shown to users."""
    error = ToolExecutionError("mcp-scanner", "failed", stderr="api_key=super-secret-value")
    assert "super-secret-value" not in str(error)
    assert "[REDACTED]" in str(error)
