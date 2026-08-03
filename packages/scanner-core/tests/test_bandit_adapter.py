from uuid import uuid4

from aevrin_scanner_core.adapters.bandit import BANDIT_IMAGE, BanditAdapter


def test_bandit_uses_published_immutable_image() -> None:
    assert BANDIT_IMAGE == (
        "ghcr.io/pycqa/bandit/bandit@"
        "sha256:3fd754dc770eacef5aeff3ed3e43f821f1c0eb18194fa0061c83b3e03a16b33f"
    )
    spec = BanditAdapter().build_spec("/tmp/source")
    assert spec.image == BANDIT_IMAGE
    assert spec.args[0] == "-q"


def test_bandit_parser_tolerates_progress_preamble() -> None:
    output = 'Working... 100%\n{"errors": [], "metrics": {}, "results": []}\n'
    assert BanditAdapter().parse_output(uuid4(), output) == []
