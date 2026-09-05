"""Manifest-driven supply chain: AS-008, AS-015, AS-016.

These read files in the clone rather than querying a registry, so the bound
is real: a transitive dependency's own install script lives in that
package's registry metadata, not here. AS-014 is what says so.
"""

from __future__ import annotations

import json
from uuid import uuid4

from aevrin_scanner_core.mcp.supply_chain import (
    check_compromised_packages,
    check_install_scripts,
    read_dependencies,
    run_supply_chain_rules,
)
from aevrin_scanner_core.models import Severity


def _write(tmp_path, name: str, content: str) -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")


def test_reads_npm_dependencies_with_their_scope(tmp_path):
    _write(
        tmp_path,
        "package.json",
        json.dumps({"dependencies": {"axios": "1.14.1"}, "devDependencies": {"jest": "29.0.0"}}),
    )
    by_name = {d.name: d for d in read_dependencies(str(tmp_path))}
    assert by_name["axios"].scope == "production"
    assert by_name["jest"].scope == "development"


def test_reads_pinned_python_requirements(tmp_path):
    _write(tmp_path, "requirements.txt", "httpx==0.27.0\n# a comment\nfastapi>=0.115\n")
    names = {d.name for d in read_dependencies(str(tmp_path))}
    # Only the pinned one: an unpinned range has no version to match an
    # advisory against, and guessing one would be worse than reporting none.
    assert names == {"httpx"}


def test_a_known_compromised_version_is_critical(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"dependencies": {"axios": "1.14.1"}}))
    findings = check_compromised_packages(uuid4(), read_dependencies(str(tmp_path)))
    assert findings
    assert findings[0].rule_id == "AS-008"
    assert findings[0].severity == Severity.CRITICAL
    assert any("axios@1.14.1" in line for line in findings[0].evidence)


def test_a_clean_version_of_a_tracked_package_is_not_flagged(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"dependencies": {"axios": "1.7.2"}}))
    assert check_compromised_packages(uuid4(), read_dependencies(str(tmp_path))) == []


def test_an_install_script_is_reported(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"scripts": {"postinstall": "node ./setup.js"}}))
    findings = [f for f in check_install_scripts(uuid4(), str(tmp_path)) if f.rule_id == "AS-015"]
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM


def test_an_install_script_that_fetches_and_executes_is_higher_severity(tmp_path):
    # `node -e` rather than the more obvious `curl … | bash`: endpoint
    # protection on some developer machines refuses to let *any* process read
    # a file containing that exact string, which makes the test fail for a
    # reason that has nothing to do with the rule. The unreadable-manifest
    # path below is what covers that case honestly.
    _write(
        tmp_path,
        "package.json",
        json.dumps({"scripts": {"preinstall": "node -e \"require('./p.js')\""}}),
    )
    findings = [f for f in check_install_scripts(uuid4(), str(tmp_path)) if f.rule_id == "AS-015"]
    assert findings[0].severity == Severity.HIGH
    assert any("node -e" in line for line in findings[0].evidence)


def test_a_project_with_no_lifecycle_scripts_is_clean(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"scripts": {"build": "tsc", "test": "jest"}}))
    assert check_install_scripts(uuid4(), str(tmp_path)) == []


def test_a_known_ioc_package_is_flagged(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"dependencies": {"plain-crypto-js": "1.0.0"}}))
    findings, _ = run_supply_chain_rules(uuid4(), str(tmp_path))
    ioc = [f for f in findings if f.rule_id == "AS-016"]
    assert ioc
    assert ioc[0].severity == Severity.CRITICAL


def test_a_repository_with_no_manifests_produces_nothing_rather_than_failing(tmp_path):
    (tmp_path / "README.md").write_text("hello")
    findings, dependencies = run_supply_chain_rules(uuid4(), str(tmp_path))
    assert findings == []
    assert dependencies == []


def test_an_unreadable_manifest_is_reported_as_missing_coverage(tmp_path, monkeypatch):
    """A manifest that cannot be opened must never be skipped in silence.

    Reproduced live on Windows: endpoint protection refuses to open a
    package.json whose install script contains `curl ... | bash`, which is
    precisely the manifest these rules exist to read. Dropping it quietly
    turned the most dangerous file in the tree into a clean result.
    """
    _write(tmp_path, "package.json", json.dumps({"dependencies": {"axios": "1.14.1"}}))

    real_open = open

    def refuse(path, *args, **kwargs):
        if str(path).endswith("package.json"):
            raise OSError(22, "Invalid argument")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", refuse)
    findings, dependencies = run_supply_chain_rules(uuid4(), str(tmp_path))

    assert dependencies == []
    unreadable = [f for f in findings if f.title == "Manifest Unreadable"]
    assert len(unreadable) == 1
    assert "not a clean result" in unreadable[0].description
    assert any("package.json" in line for line in unreadable[0].evidence)
