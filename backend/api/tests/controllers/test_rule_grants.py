"""Each rule is shown with the access it produced, read from discovery's own
evidence rather than guessed from the rule's wording."""

from __future__ import annotations

import asyncio

from aevrin_api.controllers import agent_controller

from .test_agent_tenant_isolation import MINE, StrictDb, snapshot_row


def _row() -> dict:
    row = snapshot_row(MINE, "MY-BOX")
    row["snapshot"]["permissions"] = [
        {"rule": "Bash(npm run *)", "effect": "allow", "scope": "project", "source_path": "/p/.claude/settings.json"},
        {"rule": "Bash(npm run *)", "effect": "allow", "scope": "user", "source_path": "/u/.claude/settings.json"},
        {"rule": "Task", "effect": "allow", "scope": "user", "source_path": "/u/.claude/settings.json"},
        {"rule": "sandbox_mode = workspace-write", "effect": "deny", "scope": "user", "source_path": "/u/.codex/config.toml"},
        {"rule": "approval_policy = never", "effect": "allow", "scope": "user", "source_path": "/u/.codex/config.toml"},
    ]
    row["snapshot"]["capabilities"] = [
        {
            "capability": "shell",
            "level": "limited",
            "evidence": [
                {"detail": "permissions.allow: Bash(npm run *)", "source_path": "/p/.claude/settings.json", "scope": "project"},
                {"detail": "sandbox_mode = workspace-write", "source_path": "/u/.codex/config.toml", "scope": "user"},
                {"detail": "approval_policy = never, so no command is put to a human", "source_path": "/u/.codex/config.toml", "scope": "user"},
            ],
        },
        {
            "capability": "filesystem_write",
            "level": "limited",
            "evidence": [
                {"detail": "sandbox_mode = workspace-write", "source_path": "/u/.codex/config.toml", "scope": "user"},
            ],
        },
    ]
    return row


def _grants() -> dict[tuple[str, str], list[str]]:
    row = _row()
    agent = asyncio.run(agent_controller.get_agent(row["id"], MINE, StrictDb([row])))
    return {(p.rule, p.source_path): [g.capability.value for g in p.grants] for p in agent.permissions}


def test_a_rule_is_linked_to_the_access_it_produced_in_its_own_file() -> None:
    grants = _grants()
    assert grants[("Bash(npm run *)", "/p/.claude/settings.json")] == ["shell"]
    # The same words in another file are a different rule: discovery did
    # not record that one as evidence, so it is not credited with the access.
    assert grants[("Bash(npm run *)", "/u/.claude/settings.json")] == []


def test_a_rule_that_touches_no_measured_access_links_to_nothing() -> None:
    assert _grants()[("Task", "/u/.claude/settings.json")] == []


def test_codex_setting_lines_are_linked_too() -> None:
    grants = _grants()
    assert grants[("sandbox_mode = workspace-write", "/u/.codex/config.toml")] == ["shell", "filesystem_write"]
    assert grants[("approval_policy = never", "/u/.codex/config.toml")] == ["shell"]


def test_the_permissions_page_uses_the_same_links() -> None:
    row = _row()
    listed = asyncio.run(agent_controller.list_permissions(MINE, StrictDb([row])))
    by_rule = {(p.rule, p.source_path): [g.capability.value for g in p.grants] for p in listed}
    assert by_rule == _grants()
