"""Every `columns=` projection must name a column that actually exists.

This test exists because of a real outage. Migration 0046 renamed
`scans.score` to `scans.risk_score`, and four `db.select(...)` call sites kept
asking PostgREST for `score`. Every one of them returned a 400, which the
error middleware turns into "Upstream data store error", which the dashboard
shows as a page that will not load. The agents page and the attack-paths page
were down until someone opened the browser and noticed.

None of the existing tests could have caught it. They all run against an
in-memory fake that returns whatever dict the fixture was written with, so a
projection naming a column that no longer exists is indistinguishable from one
that does. The only source of truth for "does this column exist" is the
migration set, so that is what this reads.

The failure mode to watch for is the parser quietly learning less than the
migrations say -- a schema missing half its columns would turn this into a test
that fails on correct code, and the fix people reach for then is deletion. So
`test_the_migration_set_parses_into_a_believable_schema` pins a handful of
columns 0046 is known to have moved: if the builder stops understanding the
DDL, that test fails first and says so.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[4]
_MIGRATIONS = _REPO / "backend" / "infra" / "migrations"
_API_SOURCE = _REPO / "backend" / "api" / "aevrin_api"

# Tables PostgREST serves that this repository does not create: Supabase owns
# them. Naming them explicitly keeps an unknown table an error rather than a
# silent pass, which is how a typo'd table name would otherwise slip through.
_EXTERNAL_TABLES: frozenset[str] = frozenset()

# Words that begin a table-level constraint rather than a column definition.
_CONSTRAINT_STARTERS = frozenset(
    {"primary", "unique", "foreign", "check", "constraint", "exclude", "like"}
)


def _strip_sql_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _split_top_level(body: str) -> list[str]:
    """Split on commas that sit outside any parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _table_body(sql: str, open_paren: int) -> str:
    depth = 0
    for index in range(open_paren, len(sql)):
        if sql[index] == "(":
            depth += 1
        elif sql[index] == ")":
            depth -= 1
            if depth == 0:
                return sql[open_paren + 1 : index]
    raise AssertionError("unbalanced parentheses in a create table statement")


_CREATE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?(?:public\.)?(\w+)\s*\(", re.IGNORECASE
)
_DROP_TABLE = re.compile(
    r"drop\s+table\s+(?:if\s+exists\s+)?(?:public\.)?(\w+)", re.IGNORECASE
)
# One `alter table` can carry several comma-separated clauses, so the table
# name and the clauses are matched separately. Matching them as one pattern
# silently sees only the first clause, which is how this test first reported
# `scans.mcp_tools_declared` as undefined when 0040 plainly adds it.
_ALTER = re.compile(r"alter\s+table\s+(?:public\.)?(\w+)\s+(.*?);", re.IGNORECASE | re.DOTALL)
_ADD_COLUMN = re.compile(r"^add\s+column\s+(?:if\s+not\s+exists\s+)?(\w+)", re.IGNORECASE)
_RENAME_COLUMN = re.compile(r"^rename\s+column\s+(\w+)\s+to\s+(\w+)", re.IGNORECASE)
_DROP_COLUMN = re.compile(r"^drop\s+column\s+(?:if\s+exists\s+)?(\w+)", re.IGNORECASE)


def _build_schema() -> dict[str, set[str]]:
    """Replay every migration in order and return table -> column names."""
    schema: dict[str, set[str]] = {}
    files = sorted(_MIGRATIONS.glob("*.sql"))
    assert files, "no migrations found; the path above is wrong"

    for path in files:
        sql = _strip_sql_comments(path.read_text(encoding="utf-8"))

        for match in _CREATE.finditer(sql):
            table = match.group(1).lower()
            columns = schema.setdefault(table, set())
            for item in _split_top_level(_table_body(sql, match.end() - 1)):
                first = item.split()[0].lower().strip('"')
                if first not in _CONSTRAINT_STARTERS:
                    columns.add(first)

        for match in _ALTER.finditer(sql):
            columns = schema.setdefault(match.group(1).lower(), set())
            for clause in _split_top_level(match.group(2)):
                if added := _ADD_COLUMN.match(clause):
                    columns.add(added.group(1).lower())
                elif renamed := _RENAME_COLUMN.match(clause):
                    columns.discard(renamed.group(1).lower())
                    columns.add(renamed.group(2).lower())
                elif dropped := _DROP_COLUMN.match(clause):
                    columns.discard(dropped.group(1).lower())
                # Every other clause -- add/drop constraint, enable rls, set
                # default -- leaves the column set alone.

        for match in _DROP_TABLE.finditer(sql):
            schema.pop(match.group(1).lower(), None)

    return schema


def _string_value(node: ast.AST, constants: dict[str, str]) -> str | None:
    """Resolve a literal, a module-level string constant, or a concatenation
    of those. Anything built at runtime returns None and is skipped."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_value(node.left, constants)
        right = _string_value(node.right, constants)
        return None if left is None or right is None else left + right
    if isinstance(node, ast.JoinedStr):
        return None
    return None


def _module_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign) and node.value is not None
            else []
        )
        value = getattr(node, "value", None)
        if value is None:
            continue
        resolved = _string_value(value, constants)
        if resolved is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = resolved
    return constants


def _projections() -> list[tuple[Path, int, str, str]]:
    """Every `.select("table", ..., columns="a,b")` in the API source."""
    found: list[tuple[Path, int, str, str]] = []
    for path in sorted(_API_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "select":
                continue
            if not node.args:
                continue
            table = _string_value(node.args[0], constants)
            columns = next(
                (
                    _string_value(kw.value, constants)
                    for kw in node.keywords
                    if kw.arg == "columns"
                ),
                None,
            )
            if table and columns:
                found.append((path, node.lineno, table, columns))
    return found


def test_the_migration_set_parses_into_a_believable_schema() -> None:
    """A guard on the guard: if the parser silently stopped understanding the
    migrations, every assertion below would pass by knowing nothing."""
    schema = _build_schema()
    assert "scans" in schema
    assert "risk_score" in schema["scans"], "0046 renamed score -> risk_score"
    assert "score" not in schema["scans"], "the old column must be gone"
    assert "grade" in schema["scans"]
    assert {"rule_id", "evidence", "affected_tools"} <= schema["findings"]
    assert "last_risk_score" in schema["hook_cache"]
    assert "current_risk_score" in schema["mcp_listings"]
    assert "code_score" not in schema["mcp_listing_versions"]
    # 0047: the engine replacement.
    assert {"server_command", "scanner_version", "invocation_channel"} <= schema["scans"]
    assert "mcp_capabilities" not in schema["scans"]
    assert "mcp_components" not in schema["scans"]
    assert "rug_pull_signatures" not in schema, "0047 drops the drift table"


def test_every_column_projection_names_a_column_that_exists() -> None:
    schema = _build_schema()
    projections = _projections()
    assert len(projections) > 20, "the AST walk found suspiciously few projections"

    problems: list[str] = []
    for path, lineno, table, columns in projections:
        known = schema.get(table.lower())
        if known is None:
            if table.lower() in _EXTERNAL_TABLES:
                continue
            problems.append(
                f"{path.relative_to(_REPO)}:{lineno} selects from unknown table {table!r}"
            )
            continue
        for column in columns.split(","):
            name = column.strip()
            # PostgREST embedded resources (`listing(id,slug)`) and `*` are not
            # plain column names and are not what this test is guarding.
            if not name or name == "*" or "(" in name or ":" in name:
                continue
            if name.lower() not in known:
                problems.append(
                    f"{path.relative_to(_REPO)}:{lineno} selects {table}.{name}, "
                    "which no migration defines"
                )

    if problems:
        pytest.fail("\n".join(problems))
