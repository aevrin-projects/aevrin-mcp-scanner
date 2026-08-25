"""Packing a local folder so the server can scan it.

Every scanner is installed in the API image, which is why a repository scan
started from the website needs nothing locally. A folder on this machine had
no way to reach it, so scanning one meant installing Docker and the whole tool
set here instead. This is the sending half of closing that gap.

What goes in matters as much as that it works. The folder on disk is not the
project: a 62 MB directory was 27 MB of source, 14 MB of .git history, and
21 MB of build output and virtualenvs. Uploading all of it would be slow, and
would send things nobody meant to share.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - fixed argv, no shell
import tarfile
import tempfile

# Kept in step with the API's own ceiling (services/source_upload.py).
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024

# Never uploaded, whatever the folder looks like. Version-control history,
# dependency trees, build output, and virtualenvs: none of it is the source
# under review, and .git in particular carries every deleted secret that was
# ever committed.
ALWAYS_EXCLUDED = frozenset(
    {
        ".git", ".hg", ".svn",
        "node_modules", "bower_components", "vendor",
        ".venv", "venv", "env", "virtualenv", "__pycache__", ".tox", ".nox",
        "dist", "build", "out", "target", ".next", ".nuxt", ".output",
        ".terraform", ".serverless", ".gradle", ".m2",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache",
        ".idea", ".vscode", ".DS_Store",
        "coverage", "htmlcov", ".nyc_output",
    }
)

# Compiled and packaged artefacts. A scanner has nothing useful to say about
# them and they dominate the byte count.
EXCLUDED_SUFFIXES = (
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".class", ".jar", ".war",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".flac",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".bin", ".onnx", ".pt", ".pth", ".safetensors", ".gguf", ".ckpt",
    ".sqlite", ".db", ".pack", ".idx",
)

# A single source file this large is generated, vendored, or a data blob.
MAX_FILE_BYTES = 4 * 1024 * 1024


class ArchiveTooLarge(Exception):
    pass


def _git_tracked_files(root: str) -> list[str] | None:
    """The project as git sees it: tracked files plus untracked ones that are
    not ignored. That is a far better definition of "my source" than any
    denylist, because it is the one the developer already curated.

    None when this is not a git repository, or git is not installed.
    """
    try:
        proc = subprocess.run(  # nosec B603 B607
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
    return names or None


def _walked_files(root: str) -> list[str]:
    """Fallback for a folder that is not a git repository."""
    collected: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Pruned in place so os.walk never descends into them at all.
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_EXCLUDED and not d.startswith(".git")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            collected.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return collected


def _keep(root: str, relative: str) -> bool:
    if any(part in ALWAYS_EXCLUDED for part in relative.split("/")):
        return False
    if relative.lower().endswith(EXCLUDED_SUFFIXES):
        return False
    full = os.path.join(root, relative)
    try:
        # Symlinks are skipped rather than followed: the target may sit
        # outside the folder entirely, and sending it would upload a file
        # nobody chose to include.
        if os.path.islink(full) or not os.path.isfile(full):
            return False
        return os.path.getsize(full) <= MAX_FILE_BYTES
    except OSError:
        return False


def build_source_archive(root: str) -> tuple[str, int, int]:
    """Writes a .tar.gz of `root` and returns (path, file_count, byte_size).

    The caller owns the file and must delete it.
    """
    root = os.path.abspath(root)
    names = _git_tracked_files(root) or _walked_files(root)
    keep = sorted({n for n in names if _keep(root, n)})

    fd, path = tempfile.mkstemp(suffix=".tar.gz", prefix="aevrin-source-")
    os.close(fd)
    try:
        with tarfile.open(path, "w:gz") as tar:
            for relative in keep:
                # arcname without a leading directory: the server scans what
                # it extracts, and an absolute or machine-specific prefix
                # would show up in every finding location.
                tar.add(os.path.join(root, relative), arcname=relative, recursive=False)

        size = os.path.getsize(path)
        if size > MAX_ARCHIVE_BYTES:
            raise ArchiveTooLarge(
                f"the folder packs to {size // (1024 * 1024)} MB, over the "
                f"{MAX_ARCHIVE_BYTES // (1024 * 1024)} MB limit. Scan a subdirectory, "
                "or run without --remote to scan locally."
            )
    except BaseException:
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    return path, len(keep), size
