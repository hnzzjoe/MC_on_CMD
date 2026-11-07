"""File download helpers with progress, atomic writes and checksum checks."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import requests

from mc_cli.utils.console import (
    get_download_progress,
    log_info,
    log_success,
    log_warn,
)

USER_AGENT = "mc-cli/0.1.0 (+https://github.com/)"
CHUNK_SIZE = 64 * 1024


class DownloadError(RuntimeError):
    pass


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha512_of(path: Path) -> str:
    digest = hashlib.sha512()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_valid(path: Path, expected_size: int | None, expected_sha1: str | None) -> bool:
    if not path.is_file():
        return False
    if expected_size and path.stat().st_size != expected_size:
        return False
    if expected_sha1:
        return sha1_of(path) == expected_sha1.lower()
    return True


def download_file(
    url: str,
    dest: Path,
    *,
    expected_size: int | None = None,
    expected_sha1: str | None = None,
    description: str | None = None,
    skip_if_valid: bool = True,
    quiet: bool = False,
) -> Path:
    """Download ``url`` to ``dest`` atomically.

    Existing files are kept when they already match the expected size/hash.
    ``quiet`` suppresses per-file logging/progress (used for bulk downloads).
    """
    dest = Path(dest)
    if skip_if_valid and _looks_valid(dest, expected_size, expected_sha1):
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.unlink(missing_ok=True)

    label = description or dest.name
    if not quiet:
        log_info(f"Connecting to server for {label}...")
    try:
        with requests.get(
            url, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or expected_size or 0)
            if quiet:
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            fh.write(chunk)
            else:
                with get_download_progress() as progress:
                    task = progress.add_task(label, total=total or None)
                    with open(tmp, "wb") as fh:
                        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                            if not chunk:
                                continue
                            fh.write(chunk)
                            progress.update(task, advance=len(chunk))

        if expected_size and tmp.stat().st_size != expected_size:
            raise DownloadError(
                f"size mismatch for {label}: got {tmp.stat().st_size}, expected {expected_size}"
            )
        if expected_sha1 and sha1_of(tmp) != expected_sha1.lower():
            raise DownloadError(f"checksum mismatch for {label}")

        os.replace(tmp, dest)
        if not quiet:
            log_success(f"Saved: {dest.name}")
        return dest
    except KeyboardInterrupt:
        if not quiet:
            log_warn("Download cancelled by user.")
        tmp.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, DownloadError):
            raise
        raise DownloadError(f"failed to download {label}: {exc}") from exc
