"""The rule catalogue: every rule a finding can carry says what it means.

A rule id with no plain-language text would render a finding whose first
line, on the dashboard, is empty: the reader with no security background
gets nothing, which is who the plain text is for.
"""

from __future__ import annotations

from aevrin_scanner_core.mcp.catalog import RULE_CATALOG


def test_every_rule_has_all_four_plain_answers() -> None:
    for rule in RULE_CATALOG.values():
        assert rule.plain is not None, rule.id
        for answer in (rule.plain.problem, rule.plain.why, rule.plain.could_happen, rule.plain.fix):
            assert answer.strip(), rule.id


def test_plain_text_avoids_the_jargon_it_replaces() -> None:
    jargon = ("attack surface", "blast radius", "privilege", "arbitrary", "exfiltrat", "enumerat")
    for rule in RULE_CATALOG.values():
        assert rule.plain is not None
        plain = rule.plain
        text = f"{plain.problem} {plain.why} {plain.could_happen} {plain.fix}".lower()
        for word in jargon:
            assert word not in text, (rule.id, word)


def test_plain_text_uses_no_em_dash() -> None:
    for rule in RULE_CATALOG.values():
        assert rule.plain is not None
        assert "\u2014" not in repr(rule.plain), rule.id
