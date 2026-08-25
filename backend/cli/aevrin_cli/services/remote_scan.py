"""Running a local-folder scan on the Aevrin server rather than on this machine.

The server image carries every scanner, so this needs no Docker here and no
scanner binaries installed. It sends the source, waits, and returns the same
Scan model a local run produces, so everything downstream renders identically.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import httpx
from aevrin_scanner_core import Scan

from .auth import api_url as get_api_url
from .auth import load_api_key
from .source_archive import build_source_archive

# The scan runs on a shared instance behind a worker slot, so the wait covers
# queueing as well as scanning.
POLL_INTERVAL_S = 3
MAX_WAIT_S = 900


class RemoteScanError(Exception):
    pass


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))[:400]
    except ValueError:
        return response.text[:400]


def run_remote_scan(
    folder: str,
    on_progress: Callable[[str], None],
) -> Scan:
    """Uploads `folder` and blocks until the server's scan finishes."""
    api_key = load_api_key()
    if not api_key:
        raise RemoteScanError("Not logged in. Run `aevrin login` first, or scan without --remote.")

    api_url = get_api_url()
    on_progress("packing the folder")
    archive_path, file_count, size = build_source_archive(folder)
    on_progress(f"uploading {file_count} files ({size / 1024 / 1024:.1f} MB)")

    try:
        with open(archive_path, "rb") as handle:
            response = httpx.post(
                f"{api_url}/scans/upload",
                headers={"X-API-Key": api_key},
                files={"archive": ("source.tar.gz", handle, "application/gzip")},
                data={"target_label": os.path.abspath(folder)},
                timeout=300,
            )
    except httpx.HTTPError as exc:
        raise RemoteScanError(f"Could not reach {api_url}: {exc}") from exc
    finally:
        # The archive is a copy of the source; it does not linger on disk
        # whether the upload worked or not.
        try:
            os.remove(archive_path)
        except OSError:
            pass

    if response.status_code >= 400:
        raise RemoteScanError(f"Server refused the scan ({response.status_code}): {_detail(response)}")

    scan_id = response.json()["id"]
    on_progress("scanning on the server")
    return _await_result(api_url, api_key, scan_id)


def _await_result(api_url: str, api_key: str, scan_id: str) -> Scan:
    deadline = time.monotonic() + MAX_WAIT_S
    headers = {"X-API-Key": api_key}

    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_S)
        try:
            response = httpx.get(f"{api_url}/scans/{scan_id}", headers=headers, timeout=30)
        except httpx.HTTPError:
            # A blip mid-scan is not a failed scan; the result is durable on
            # the server either way, so keep waiting rather than discarding it.
            continue
        if response.status_code >= 400:
            raise RemoteScanError(f"Could not read the scan ({response.status_code}): {_detail(response)}")

        row = response.json()
        if row.get("status") in ("completed", "incomplete", "failed"):
            return _fetch_full_scan(api_url, headers, scan_id, row)

    raise RemoteScanError(
        f"The scan did not finish within {MAX_WAIT_S // 60} minutes. It is still running on the "
        f"server; see it at {api_url.replace('api.', '')}/scans/{scan_id}"
    )


def _fetch_full_scan(api_url: str, headers: dict[str, str], scan_id: str, row: dict) -> Scan:
    findings = httpx.get(f"{api_url}/scans/{scan_id}/findings", headers=headers, timeout=60)
    stages = httpx.get(f"{api_url}/scans/{scan_id}/stages", headers=headers, timeout=30)
    if findings.status_code >= 400:
        raise RemoteScanError(f"Could not read the findings ({findings.status_code})")

    payload = dict(row)
    payload["findings"] = findings.json()
    # ScanStageOut omits scan_id -- it is already implied by the URL the
    # stages were fetched from -- while the shared ScanStage model requires
    # it. Filled back in here rather than widening the API response, which
    # would put the same id on every row of every stage list.
    payload["stages"] = [
        {**stage, "scan_id": scan_id} for stage in (stages.json() if stages.status_code < 400 else [])
    ]
    # Validated through the shared model, so a server that changes shape fails
    # loudly here rather than rendering a half-empty report.
    return Scan.model_validate(payload)
