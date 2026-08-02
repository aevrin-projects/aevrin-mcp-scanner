"""Adapter contract every scanner implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..models import Finding, ToolName
from ..runner import (
    DockerRunSpec,
    LocalCommandSpec,
    get_executor_mode,
    run_container,
    run_local_command,
)


class ScannerAdapter(ABC):
    tool: ToolName

    @abstractmethod
    def build_spec(self, target_dir: str) -> DockerRunSpec:
        """target_dir is a host path to the cloned repo / extracted config,
        already isolated in a scan-scoped temp directory."""

    def build_local_command(self, target_dir: str) -> LocalCommandSpec:
        """Subprocess-mode equivalent of build_spec — only required for
        adapters that support AEVRIN_EXECUTOR=subprocess. Adapters without a
        practical non-Docker binary (see mcp_context_protector.py) leave this
        unimplemented; that mode simply isn't offered for them."""
        raise NotImplementedError(
            f"{self.tool.value} has no subprocess-mode command — Docker-only"
        )

    @abstractmethod
    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        """Normalize raw tool JSON into shared Finding models."""

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        if get_executor_mode() == "subprocess":
            spec = self.build_local_command(target_dir)
            stdout, _stderr, _code = run_local_command(self.tool.value, spec, target_dir)
        else:
            docker_spec = self.build_spec(target_dir)
            stdout, _stderr, _code = run_container(self.tool.value, docker_spec)
        return self.parse_output(scan_id, stdout)
