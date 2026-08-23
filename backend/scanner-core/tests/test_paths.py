from aevrin_scanner_core.execution.paths import relative_to_mount


def test_strips_mount_prefix():
    assert relative_to_mount("/src/app.py") == "app.py"


def test_strips_nested_mount_prefix():
    assert relative_to_mount("/src/pkg/sub/module.py") == "pkg/sub/module.py"


def test_leaves_already_relative_paths_alone():
    assert relative_to_mount("app.py") == "app.py"


def test_bare_mount_root_becomes_dot():
    assert relative_to_mount("/src") == "."


def test_none_stays_none():
    assert relative_to_mount(None) is None
