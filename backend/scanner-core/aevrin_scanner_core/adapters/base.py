"""Adapter contract every scanner implements."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from uuid import UUID

from ..execution.runner import (
    DockerRunSpec,
    LocalCommandSpec,
    ToolExecutionError,
    get_executor_mode,
    run_container,
    run_local_command,
)
from ..models import Finding, ToolName


class ScannerAdapter(ABC):
    tool: ToolName

    @abstractmethod
    def build_spec(self, target_dir: str) -> DockerRunSpec:
        """target_dir is a host path to the cloned repo / extracted config,
        already isolated in a scan-scoped temp directory."""

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        """Subprocess-mode equivalent of build_spec: only required for
        adapters that support AEVRIN_EXECUTOR=subprocess."""
        raise NotImplementedError(
            f"{self.tool.value} has no subprocess-mode command, Docker-only"
        )

    @abstractmethod
    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        """Normalize raw tool JSON into shared Finding models."""

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        if get_executor_mode() == "subprocess":
            spec = self.build_local_command(target_dir)
            stdout, stderr, _code = run_local_command(self.tool.value, spec, target_dir)
        else:
            docker_spec = self.build_spec(target_dir)
            stdout, stderr, _code = run_container(self.tool.value, docker_spec)
        try:
            return self.parse_output(scan_id, stdout)
        except json.JSONDecodeError as exc:
            detail = f"returned invalid JSON output ({exc.msg} at character {exc.pos})"
            if stderr.strip():
                detail += "; review scanner stderr in the stage error"
            raise ToolExecutionError(
                self.tool.value,
                detail,
                stdout=stdout,
                stderr=stderr,
            ) from exc
