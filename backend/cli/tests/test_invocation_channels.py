"""The surfaces a scan can arrive through, and the one rule they all share.

`InvocationChannel` records who asked. It must never change what was found:
the same server scanned from a laptop, a CI job or an agent produces the same
findings, the same grade and the same policy. These tests pin the recording,
and pin that the MCP surface reads its verdict from the pipeline rather than
forming its own.
"""

from __future__ import annotations

import pytest
from aevrin_scanner_core.models import InvocationChannel

from aevrin_cli.channel import current_channel, running_in_ci

_CI_ENV_VARS = ("CI", "CONTINUOUS_INTEGRATION", "BUILD_NUMBER", "GITHUB_ACTIONS")


@pytest.fixture(autouse=True)
def _no_ambient_ci(monkeypatch):
    """This suite itself usually runs in CI, so the environment has to be
    cleared or every assertion below passes for the wrong reason."""
    for var in _CI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_a_developer_shell_reports_the_cli_channel() -> None:
    assert running_in_ci() is False
    assert current_channel() is InvocationChannel.CLI


@pytest.mark.parametrize("var", _CI_ENV_VARS)
def test_any_ci_system_reports_the_ci_channel(monkeypatch, var: str) -> None:
    """Detected from the generic variables every CI system sets, rather than a
    list of vendor names, so a runner nobody here has heard of still reports
    itself correctly."""
    monkeypatch.setenv(var, "true")
    assert current_channel() is InvocationChannel.CI


@pytest.mark.parametrize("value", ["", "0", "false", "FALSE", "no", "off"])
def test_ci_set_to_a_falsey_value_is_not_ci(monkeypatch, value: str) -> None:
    """Some shells and runners export CI=false to mean "not CI". Treating that
    as CI would be worse than not checking at all, because it would mislabel
    every scan on those machines."""
    monkeypatch.setenv("CI", value)
    assert current_channel() is InvocationChannel.CLI


class TestMcpServerSurface:
    """Aevrin exposed as an MCP server, so an agent can scan before installing."""

    @staticmethod
    def _module():
        return pytest.importorskip(
            "aevrin_cli.mcp_server",
            reason="needs the optional MCP extra: pip install 'aevrin[mcp]'",
        )

    def test_it_exposes_exactly_one_tool(self) -> None:
        """One tool, because there is one question worth asking an agent to
        ask. A surface that grew a second scanner would be the duplication
        ADR-033 exists to prevent."""
        mod = self._module()
        assert mod.mcp is not None
        assert callable(mod.scan_mcp_server) or hasattr(mod.scan_mcp_server, "fn")

    @pytest.mark.parametrize(
        ("grade", "expected"),
        [("A", "ALLOW"), ("B", "ALLOW"), ("C", "REQUIRE_APPROVAL"),
         ("D", "REQUIRE_APPROVAL"), ("F", "BLOCK")],
    )
    def test_policy_comes_from_the_shared_table(self, grade: str, expected: str) -> None:
        assert self._module()._policy_value(grade) == expected

    @pytest.mark.parametrize("grade", [None, "", "Z", "unknown"])
    def test_an_absent_or_unrecognised_grade_never_allows(self, grade) -> None:
        """The single most important line in this file.

        A missing grade means nothing was established, and a letter this build
        has never seen means the same thing. Either must send a human to look;
        neither may raise, and neither may become ALLOW - a model reading
        "ALLOW" from a scan that assessed nothing is exactly the failure the
        product exists to prevent.
        """
        assert self._module()._policy_value(grade) == "REQUIRE_APPROVAL"

    def test_an_incomplete_scan_says_so_in_words_not_just_a_null(self) -> None:
        """The consumer here is a language model, which reads prose more
        reliably than it reads a null field. `summary` has to state the
        conclusion outright."""
        mod = self._module()

        class _Stage:
            error = "the package could not be installed"

        class _Scan:
            from aevrin_scanner_core.models import ScanStatus as _S

            status = _S.INCOMPLETE
            grade = None
            risk_score = None

            def __init__(self) -> None:
                self.stages = [_Stage()]
                self.findings: list = []
                self.mcp_tools_declared: list = []

        summary = mod._summarise(_Scan())
        assert "INCOMPLETE" in summary
        assert "not be treated as safe" in summary
        assert "the package could not be installed" in summary
