from aevrin_scanner_core.adapters.bandit import BANDIT_IMAGE, BanditAdapter


def test_bandit_uses_published_immutable_image() -> None:
    assert BANDIT_IMAGE == (
        "ghcr.io/pycqa/bandit/bandit@"
        "sha256:3fd754dc770eacef5aeff3ed3e43f821f1c0eb18194fa0061c83b3e03a16b33f"
    )
    assert BanditAdapter().build_spec("/tmp/source").image == BANDIT_IMAGE
