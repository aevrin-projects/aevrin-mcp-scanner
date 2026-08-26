from importlib.metadata import version as pkg_version

from helpers import plain
from typer.testing import CliRunner

from aevrin_cli.main import app

runner = CliRunner()


def test_top_level_version_flag_works():
    # Regression test: --version previously wasn't registered at all
    # (only the `version` subcommand existed), so this exited 2 with
    # "No such option: --version".
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == pkg_version("aevrin")


def test_version_subcommand_still_works():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == pkg_version("aevrin")


def test_help_still_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--version" in plain(result.stdout)


def test_no_args_shows_help_not_a_crash():
    result = runner.invoke(app, [])
    assert "Usage:" in plain(result.stdout)


def test_false_positive_triage_requires_reason_before_auth_lookup():
    result = runner.invoke(app, ["findings", "triage", "finding-id", "false_positive"])
    assert result.exit_code == 2
    assert "require --reason" in plain(result.stderr)


def test_an_unknown_triage_status_is_rejected_before_any_network_call():
    """A typo used to be answered by the API's own validation document --
    several hundred characters of JSON about uuid_parsing and value_error --
    which does not tell anyone they wrote "fixxed". Rejecting it here also
    keeps a mistyped status from spending a request and an API key."""
    result = runner.invoke(app, ["findings", "triage", "finding-id", "fixxed"])
    assert result.exit_code == 2
    message = plain(result.stderr)
    assert "Invalid status 'fixxed'" in message
    # Names the alternatives, rather than leaving someone to guess them.
    assert "open, fixed, false_positive" in message


def test_the_accepted_statuses_are_the_ones_the_api_validates():
    """Restating the list would let the CLI accept a status the server
    rejects, which is the failure this check exists to prevent."""
    from aevrin_scanner_core import TriageStatus

    from aevrin_cli.main import TRIAGE_STATUSES

    assert set(TRIAGE_STATUSES) == {s.value for s in TriageStatus}


def test_the_hook_snippet_needs_no_shell_quoting_to_survive(capsys):
    r"""It used to emit `python3 'C:\path\hook_script.py'` as one shell
    string. cmd.exe does not treat POSIX single quotes as quoting, so it
    passed them through as part of the filename and every Windows install got
    a hook that never ran -- silently, since a hook that fails to start looks
    exactly like a hook that decided not to object.

    Exec form hands the path over as an argument, so no shell parses it.

    Calls the snippet builder rather than `hook setup`, which logs in first:
    with no stored hook credential that starts a real device-authorisation
    flow and polls until the code expires. As a test it took ten minutes and
    its result depended on whether the machine running it happened to be
    logged in.
    """
    import json
    import sys
    from pathlib import Path

    from aevrin_cli.main import print_hook_settings_snippet

    print_hook_settings_snippet()

    snippet = json.loads(capsys.readouterr().out)
    entries = snippet["hooks"]["PreToolUse"]
    assert [e["matcher"] for e in entries] == ["Bash", "Write"]

    for entry in entries:
        hook = entry["hooks"][0]
        # The interpreter is named outright, not looked up on PATH. `python3`
        # on Windows is usually the Microsoft Store stub, which opens the
        # Store rather than running the script.
        assert hook["command"] == sys.executable
        assert len(hook["args"]) == 1
        script = Path(hook["args"][0])
        assert script.is_file(), "the snippet points at a script that ships with this package"
        assert script.name == "hook_script.py"
        # The path arrives whole, with no quoting for a shell to misread.
        assert "'" not in hook["args"][0]
        assert hook["timeout"] == 8
