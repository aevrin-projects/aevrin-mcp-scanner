"""Rules the migrations and the data layer must keep, checked from source.

Both exist because of real exposures that every other test missed:

* Five `security definer` functions (the admin user list among them) kept
  Postgres's default EXECUTE grant to PUBLIC, so PostgREST served them to
  anyone holding the anon key that ships in the frontend (fixed in 0051).
* The admin dashboard read the registry with `limit=10000`, but PostgREST
  returns at most `MAX_ROWS` rows per response and says nothing when it
  truncates, so it showed 1,000 of 18,000 listings.
"""

from __future__ import annotations

import re
from pathlib import Path

from aevrin_api.db import MAX_ROWS

API_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = API_ROOT.parent / "infra" / "migrations"
SOURCE = API_ROOT / "aevrin_api"

# Definer functions any caller may execute, and why that is safe: each
# answers only about the caller, through auth.uid().
CALLABLE_BY_ANYONE = {
    "is_org_member": "RLS policies call it; answers whether the caller is a member",
    "my_org": "RLS helper; returns the caller's own workspace",
}
# Definer functions signed-in users may execute: each checks the caller
# itself, or does nothing a user could misuse.
CALLABLE_WHEN_SIGNED_IN = {
    "org_member_emails": "checks the caller's own membership before answering",
    "increment_listing_views": "bumps a public view counter",
}

_CREATE = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+public\.(\w+)\s*\((.*?)\$(\w*)\$(.*?)\$\3\$",
    re.IGNORECASE | re.DOTALL,
)
_REVOKE = re.compile(
    r"revoke\s+(?:all|execute)(?:\s+privileges)?\s+on\s+function\s+public\.(\w+)\s*\([^)]*\)\s+from\s+([^;]+);",
    re.IGNORECASE,
)


def _definer_functions() -> dict[str, str]:
    """name -> first migration defining it, for every `security definer`
    function that can be called (a trigger function cannot be)."""
    found: dict[str, str] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = path.read_text(encoding="utf-8")
        for match in _CREATE.finditer(sql):
            name, header = match.group(1), match.group(2)
            if not re.search(r"security\s+definer", header, re.IGNORECASE):
                continue
            if re.search(r"returns\s+trigger", header, re.IGNORECASE):
                continue
            found.setdefault(name.lower(), path.name)
    return found


def _revoked_roles() -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    for path in MIGRATIONS.glob("*.sql"):
        for name, targets in _REVOKE.findall(path.read_text(encoding="utf-8")):
            roles.setdefault(name.lower(), set()).update(
                role.strip().lower() for role in targets.split(",")
            )
    return roles


def test_the_migration_parser_sees_the_definer_functions() -> None:
    """Guards the guard: a regex that matched nothing would pass every rule."""
    functions = _definer_functions()
    assert {"lookup_account_by_email", "admin_delete_user", "scan_diff", "admin_analytics"} <= set(
        functions
    )


def test_every_definer_function_revokes_public_access() -> None:
    """A `security definer` function runs with its owner's rights and sees
    every row. Unless its migration revokes the default grant, PostgREST
    serves it over /rest/v1/rpc to anyone with the anon key."""
    revoked = _revoked_roles()
    problems = []
    for name, migration in sorted(_definer_functions().items()):
        if name in CALLABLE_BY_ANYONE:
            continue
        need = {"public", "anon"}
        if name not in CALLABLE_WHEN_SIGNED_IN:
            need.add("authenticated")
        missing = need - revoked.get(name, set())
        if missing:
            problems.append(f"{name} ({migration}) is still executable by {sorted(missing)}")
    assert not problems, (
        "Add `revoke all on function public.<name>(<args>) from public, anon, authenticated;` "
        "and `grant execute ... to service_role;` (see SECURITY.md):\n" + "\n".join(problems)
    )


def test_no_read_asks_for_more_rows_than_postgrest_returns() -> None:
    """A `limit` above MAX_ROWS is silently cut to MAX_ROWS. Read every row
    with `select_all`, or count with `db.count`."""
    over = []
    for path in SOURCE.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            for value in re.findall(r"\blimit\s*=\s*([\d_]+)\b", code):
                if int(value.replace("_", "")) > MAX_ROWS:
                    over.append(f"{path.relative_to(API_ROOT)}:{number}: limit={value}")
    assert not over, "\n".join(over)
