"""mcp-context-protector adapter — backup rug-pull pinning, used only when
mcp-scan (snyk-agent-scan) itself fails, per Section 3's "alternative/backup"
framing.

CLI flags confirmed live via --help against aevrin/mcp-context-protector:local
(installed from github.com/trailofbits/mcp-context-protector, no PyPI
release exists under that name). Not yet run end-to-end against a live
server — its `--review-server` / server-config-file flow expects an
interactive approve/reject loop; the exact non-interactive JSON shape needs
confirmation in Phase 7.

Cost note (flagged, not silently absorbed): this image is 8.64GB — it pulls
in torch, CUDA packages, transformers, and llamafirewall as hard
dependencies of the package itself, none of which this project asked for.
That is much too heavy to spin up as a disposable per-scan container. Keep
this wired as the documented fallback only (invoked when the primary
mcp-scan adapter raises ToolExecutionError), not as a default pipeline step.
"""

from __future__ import annotations

import json
from uuid import UUID

from ..models import Finding, ToolName
from ..runner import DockerRunSpec
from .base import ScannerAdapter
from .mcp_scan import McpScanInspectResult

IMAGE = "aevrin/mcp-context-protector:local"


class McpContextProtectorAdapter(ScannerAdapter):
    tool = ToolName.MCP_CONTEXT_PROTECTOR

    def __init__(self, config_path_in_container: str = "/scan/mcp.json"):
        self.config_path_in_container = config_path_in_container

    def build_spec(self, target_dir: str) -> DockerRunSpec:
        return DockerRunSpec(
            image=IMAGE,
            args=[
                "--wrap-mcp-json",
                self.config_path_in_container,
                "--server-config-file",
                "/scan/.mcp-context-protector-servers.json",
            ],
            mounts={target_dir: ("/scan", False)},  # writes its server-config db into the mount
            network_enabled=True,
            timeout_s=120,
            mem_limit="2g",  # torch import alone needs headroom beyond our other tools' 768m default
            ok_exit_codes=(0,),
        )

    def inspect_signatures(self, target_dir: str) -> list[McpScanInspectResult]:
        import os

        from ..runner import run_container

        spec = self.build_spec(target_dir)
        run_container(self.tool.value, spec)
        db_path = os.path.join(target_dir, ".mcp-context-protector-servers.json")
        results: list[McpScanInspectResult] = []
        if os.path.exists(db_path):
            with open(db_path) as f:
                db = json.load(f)
            for server_name, entry in db.items():
                results.append(
                    McpScanInspectResult(
                        server_name=server_name,
                        signature=entry.get("tools") or entry,
                        error=None,
                    )
                )
            os.remove(db_path)
        return results

    def parse_output(self, scan_id: UUID, stdout: str) -> list[Finding]:  # pragma: no cover
        raise NotImplementedError("use inspect_signatures(); this adapter doesn't emit Findings directly")
