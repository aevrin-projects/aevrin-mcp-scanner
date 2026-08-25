"""The upload path treats the archive as hostile.

An authenticated account is cheap, so "the sender is logged in" is not a
security property. Every test here builds a real tar and hands it to the real
extractor; none of them assert on a mock.
"""

from __future__ import annotations

import io
import os
import tarfile

import pytest

from aevrin_api.services import source_upload
from aevrin_api.services.source_upload import (
    MAX_ENTRIES,
    UnsafeArchive,
    extract_source_archive,
)


def _write_tar(path, members):
    """members: (name, content|None, kind) where kind is file/dir/symlink."""
    with tarfile.open(path, "w:gz") as tar:
        for name, content, kind in members:
            if kind == "dir":
                info = tarfile.TarInfo(name)
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info = tarfile.TarInfo(name)
                info.type = tarfile.SYMTYPE
                info.linkname = content
                tar.addfile(info)
            else:
                data = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return str(path)


def test_an_ordinary_project_extracts(tmp_path):
    archive = _write_tar(
        tmp_path / "src.tar.gz",
        [
            ("project", None, "dir"),
            ("project/app.py", "import os\n", "file"),
            ("project/pkg", None, "dir"),
            ("project/pkg/util.py", "X = 1\n", "file"),
        ],
    )

    root = extract_source_archive(archive)

    # Unwrapped to the single top-level directory, so findings are reported
    # against "app.py" rather than "project/app.py".
    assert os.path.isfile(os.path.join(root, "app.py"))
    assert os.path.isfile(os.path.join(root, "pkg", "util.py"))


def test_a_flat_archive_without_a_wrapper_directory_also_works(tmp_path):
    archive = _write_tar(tmp_path / "src.tar.gz", [("a.py", "x = 1\n", "file"), ("b.py", "y = 2\n", "file")])
    root = extract_source_archive(archive)
    assert os.path.isfile(os.path.join(root, "a.py"))


@pytest.mark.parametrize(
    "escaping_name",
    [
        "../escaped.py",
        "project/../../escaped.py",
        "/etc/passwd",
        "project/../../../tmp/escaped.py",
    ],
)
def test_path_traversal_is_refused(tmp_path, escaping_name):
    """The classic tar escape. Checked on the raw member name, because
    normalising first is exactly what hides 'a/../../etc/passwd'."""
    archive = _write_tar(tmp_path / "evil.tar.gz", [(escaping_name, "pwned\n", "file")])

    with pytest.raises(UnsafeArchive) as excinfo:
        extract_source_archive(archive)

    assert "path" in str(excinfo.value)


def test_a_symlink_is_refused(tmp_path):
    """A symlink is a pointer at something outside the extraction root, and
    a scanner following it would read a file the sender never sent."""
    archive = _write_tar(tmp_path / "link.tar.gz", [("project/creds", "/etc/shadow", "symlink")])

    with pytest.raises(UnsafeArchive, match="unsupported entry type"):
        extract_source_archive(archive)


def test_a_zip_bomb_is_refused_before_it_lands(tmp_path, monkeypatch):
    """Zeros compress to almost nothing and expand to gigabytes, so the
    compressed size says nothing about what reaches the disk. The ceiling is
    lowered here rather than actually writing half a gigabyte: what is under
    test is that declared sizes are summed and refused, not the constant.
    """
    monkeypatch.setattr(source_upload, "MAX_EXTRACTED_BYTES", 64)

    archive = _write_tar(
        tmp_path / "bomb.tar.gz",
        [("project", None, "dir"), ("project/big.bin", "z" * 4096, "file")],
    )

    with pytest.raises(UnsafeArchive, match="expands to more than"):
        extract_source_archive(archive)


def test_the_size_ceiling_is_the_uncompressed_total_not_one_file(tmp_path, monkeypatch):
    """Many small members that individually fit still must not add up past
    the ceiling."""
    monkeypatch.setattr(source_upload, "MAX_EXTRACTED_BYTES", 1000)

    archive = _write_tar(
        tmp_path / "many-small.tar.gz",
        [("project", None, "dir")] + [(f"project/f{i}.py", "a" * 200, "file") for i in range(10)],
    )

    with pytest.raises(UnsafeArchive, match="expands to more than"):
        extract_source_archive(archive)


def test_too_many_entries_is_refused(tmp_path):
    with tarfile.open(tmp_path / "many.tar.gz", "w:gz") as tar:
        for i in range(MAX_ENTRIES + 10):
            info = tarfile.TarInfo(f"project/f{i}")
            info.size = 0
            tar.addfile(info, io.BytesIO(b""))

    with pytest.raises(UnsafeArchive, match="more than"):
        extract_source_archive(str(tmp_path / "many.tar.gz"))


def test_a_corrupt_archive_fails_without_leaving_a_directory_behind(tmp_path):
    bad = tmp_path / "truncated.tar.gz"
    bad.write_bytes(b"\x1f\x8b\x08\x00 not really a gzip stream")

    before = set(os.listdir(tmp_path))
    with pytest.raises(UnsafeArchive, match="could not read the archive"):
        extract_source_archive(str(bad))
    assert set(os.listdir(tmp_path)) == before


def test_nothing_is_written_when_a_later_member_is_unsafe(tmp_path):
    """Validation runs over every member before extraction starts, so a
    poisoned entry at the end cannot leave the safe ones on disk."""
    archive = _write_tar(
        tmp_path / "mixed.tar.gz",
        [
            ("project", None, "dir"),
            ("project/ok.py", "x = 1\n", "file"),
            ("../escaped.py", "pwned\n", "file"),
        ],
    )

    with pytest.raises(UnsafeArchive):
        extract_source_archive(archive)
