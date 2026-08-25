"""Unpacking an uploaded source archive so the server can scan a folder that
only exists on someone's machine.

Dashboard scans work because the API image carries every scanner; a local
folder simply never reaches it. This is the missing half: the CLI sends the
folder, the server scans it with the full tool set, and the person needs no
Docker and no scanner binaries locally.

The archive is untrusted input. It arrives over the network from an
authenticated account, which is not the same as being safe: an account is
cheap and a malicious tar is free. Everything here assumes the sender is
hostile and the extraction is the attack surface, not the scanning.
"""

from __future__ import annotations

import logging
import os
import shutil
import tarfile
import tempfile

logger = logging.getLogger("aevrin.source_upload")

# Compressed bytes accepted over the wire. Generous for source, far below what
# would let one request fill the instance's 30 GB root volume.
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024

# Uncompressed ceiling, enforced while unpacking. A tar of 64 MB of zeros
# expands to gigabytes; the compressed size alone says nothing about what
# lands on disk.
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024

MAX_ENTRIES = 60_000


class UnsafeArchive(Exception):
    """Rejected before anything was written. The message is shown to the
    sender, so it says what was wrong without echoing attacker-controlled
    paths back into a log line or a response."""


def _reject(reason: str) -> None:
    raise UnsafeArchive(reason)


def _assert_safe_members(archive: tarfile.TarFile) -> None:
    """Checked in full before a single byte is written.

    tarfile's own `filter="data"` covers most of this on 3.12 and recent
    3.11, and it is still applied below. This runs first anyway: the limits
    on count and total size are ours rather than the filter's, and a
    rejection here happens before any partial extraction exists to clean up.
    """
    total = 0
    for entries, member in enumerate(archive.getmembers(), start=1):
        if entries > MAX_ENTRIES:
            _reject(f"archive has more than {MAX_ENTRIES} entries")

        name = member.name
        # Absolute paths and parent traversal both escape the destination.
        # Checked on the raw name rather than after normalisation, because
        # normalising first is what hides "a/../../etc/passwd".
        if name.startswith(("/", "\\")) or os.path.isabs(name):
            _reject("archive contains an absolute path")
        if any(part == ".." for part in name.replace("\\", "/").split("/")):
            _reject("archive contains a parent-directory path")
        if ":" in name.split("/")[0] and len(name.split(":")[0]) == 1:
            _reject("archive contains a drive-letter path")

        # Only ordinary files and directories. A symlink or hardlink is a way
        # to point at something outside the extraction root, and a device or
        # FIFO has no business in a source tree at all.
        if not (member.isfile() or member.isdir()):
            _reject(f"archive contains an unsupported entry type ({name.rsplit('/', 1)[-1][:40]!r})")

        total += max(member.size, 0)
        if total > MAX_EXTRACTED_BYTES:
            _reject(f"archive expands to more than {MAX_EXTRACTED_BYTES // (1024 * 1024)} MB")


def extract_source_archive(archive_path: str) -> str:
    """Unpacks a .tar.gz into a fresh temp directory and returns its path.

    The caller owns the directory and must remove it; scanning is the only
    thing that should happen inside it, and nothing in it is ever executed.
    """
    dest = tempfile.mkdtemp(prefix="aevrin-upload-")
    try:
        # Two passes, on purpose: validate every member first, then extract.
        # A single pass that extracts as it validates leaves the safe members
        # on disk when a poisoned one appears later in the archive.
        with tarfile.open(archive_path, "r:gz") as archive:
            _assert_safe_members(archive)
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(dest, filter="data")  # nosec B202 - members validated above
    except UnsafeArchive:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    except (tarfile.TarError, OSError, EOFError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise UnsafeArchive(f"could not read the archive: {type(exc).__name__}") from exc

    # A single top-level directory is what `tar czf - my-project` produces.
    # Scanning its parent would report every path with that prefix, which is
    # noise in every finding location.
    entries = os.listdir(dest)
    if len(entries) == 1:
        only = os.path.join(dest, entries[0])
        if os.path.isdir(only):
            return only
    return dest
