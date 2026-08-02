"""Adapter contract every scanner implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..models import Finding, ToolName
from ..runner import DockerRunSpec, run_container


class ScannerAdapter(ABC):
    tool: ToolName

    @abstractmethod
    def build_spec(self, target_dir: str) -> DockerRunSpec:
        """target_dir is a host path to the cloned repo / extracted config,
        already isolated in a scan-scoped temp directory."""

    @abstractmethod
    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:
        """Normalize raw tool JSON into shared Finding models."""

    def run(self, scan_id: UUID, target_dir: str) -> list[Finding]:
        spec = self.build_spec(target_dir)
        stdout, _stderr, _code = run_container(self.tool.value, spec)
        return self.parse_output(scan_id, stdout)
