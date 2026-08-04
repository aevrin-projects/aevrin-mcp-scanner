from ..models import ToolName
from .bandit import BanditAdapter
from .base import ScannerAdapter
from .gitleaks import GitleaksAdapter
from .mcp_shield import McpShieldAdapter
from .osv_scanner import OsvScannerAdapter
from .scorecard import ScorecardAdapter
from .semgrep import SemgrepAdapter
from .trivy import TrivyAdapter
from .trufflehog import TruffleHogAdapter

# Lets a caller re-run the *specific* scanner that flagged a finding against
# patched code, without re-running the whole pipeline — used by the auto-fix
# flow (apps/api/src/aevrin_api/autofix.py) to confirm a generated patch
# actually clears the finding before anything is opened as a PR.
ADAPTER_BY_TOOL: dict[ToolName, type[ScannerAdapter]] = {
    ToolName.SEMGREP: SemgrepAdapter,
    ToolName.BANDIT: BanditAdapter,
    ToolName.GITLEAKS: GitleaksAdapter,
    ToolName.TRUFFLEHOG: TruffleHogAdapter,
}

__all__ = [
    "ADAPTER_BY_TOOL",
    "BanditAdapter",
    "GitleaksAdapter",
    "McpShieldAdapter",
    "OsvScannerAdapter",
    "ScannerAdapter",
    "ScorecardAdapter",
    "SemgrepAdapter",
    "TrivyAdapter",
    "TruffleHogAdapter",
]
