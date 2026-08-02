from importlib.metadata import version as pkg_version

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
    assert "--version" in result.stdout


def test_no_args_shows_help_not_a_crash():
    result = runner.invoke(app, [])
    assert "Usage:" in result.stdout
