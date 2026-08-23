from __future__ import annotations

from aevrin_scanner_core.adapters.osv_scanner import OsvScannerAdapter
from aevrin_scanner_core.adapters.trufflehog import TruffleHogAdapter
from aevrin_scanner_core.execution.runner import (
    DockerRunSpec,
    ToolExecutionError,
    run_container,
    sanitized_subprocess_env,
)


def test_subprocess_environment_drops_application_secrets(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "database-secret")
    monkeypatch.setenv("DEFECTDOJO_API_KEY", "dojo-secret")

    result = sanitized_subprocess_env({"GITHUB_AUTH_TOKEN": "scanner-specific"})

    assert result["PATH"] == "/usr/bin"
    assert result["GITHUB_AUTH_TOKEN"] == "scanner-specific"
    assert "SUPABASE_SERVICE_ROLE_KEY" not in result
    assert "DEFECTDOJO_API_KEY" not in result


def test_tool_error_redacts_likely_secret_values() -> None:
    error = ToolExecutionError(
        "scanner",
        "failed",
        stderr="authorization: bearer-value API_KEY=another-value ordinary diagnostic",
    )

    assert "bearer-value" not in str(error)
    assert "another-value" not in str(error)
    assert "ordinary diagnostic" in str(error)


def test_docker_runner_uses_windows_safe_mount_and_resource_defaults(monkeypatch, tmp_path) -> None:
    captured: list[str] = []

    class _Result:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(command, **kwargs):
        captured.extend(command)
        return _Result()

    monkeypatch.setattr("aevrin_scanner_core.execution.runner.subprocess.run", fake_run)
    spec = DockerRunSpec(
        image="scanner:version",
        args=["scan", "/src"],
        mounts={str(tmp_path): ("/src", True)},
    )

    run_container("scanner", spec)

    mount = captured[captured.index("--mount") + 1]
    assert mount == f"type=bind,source={tmp_path},target=/src,readonly"
    assert captured[captured.index("--memory") + 1] == "2g"
    assert captured[captured.index("--cpus") + 1] == "2.0"


def test_dependency_scan_is_recursive_for_monorepos(tmp_path) -> None:
    docker_args = OsvScannerAdapter().build_spec(str(tmp_path)).args
    local_args = OsvScannerAdapter().build_local_command(str(tmp_path)).args

    assert "--recursive" in docker_args
    assert "--recursive" in local_args


def test_trufflehog_skips_generated_binaries(tmp_path) -> None:
    docker_args = TruffleHogAdapter().build_spec(str(tmp_path)).args
    local_args = TruffleHogAdapter().build_local_command(str(tmp_path)).args

    assert "--force-skip-binaries" in docker_args
    assert "--force-skip-binaries" in local_args
