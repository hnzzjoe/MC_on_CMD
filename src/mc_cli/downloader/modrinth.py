"""Thin Modrinth API client used by the mod / shader / resourcepack commands."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import requests

from mc_cli.downloader.general import USER_AGENT, DownloadError, download_file, sha1_of
from mc_cli.utils.console import log_info, log_warn

BASE = "https://api.modrinth.com/v2"
TIMEOUT = 20
LOADER_ALIASES = {
    "vanilla": "vanilla",
    "fabric": "fabric",
    "quilt": "quilt",
    "forge": "forge",
    "neoforge": "neoforge",
}


class ModrinthError(RuntimeError):
    pass


def _request(method: str, path: str, **kwargs) -> Any:
    url = path if path.startswith("http") else f"{BASE}{path}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        if status == 404:
            raise ModrinthError("not found (404)") from exc
        raise ModrinthError(f"HTTP {status}: {exc}") from exc
    except requests.RequestException as exc:
        raise ModrinthError(f"network error: {exc}") from exc
    except ValueError as exc:
        raise ModrinthError("invalid JSON response") from exc


def search(
    query: str,
    page: int = 1,
    limit: int = 5,
    project_type: str = "mod",
) -> dict[str, Any]:
    offset = max(page - 1, 0) * limit
    params = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "index": "relevance",
    }
    if project_type:
        params["facets"] = json.dumps([[f"project_type:{project_type}"]])
    return _request("GET", "/search", params=params)


def get_project(slug: str) -> dict[str, Any]:
    return _request("GET", f"/project/{slug}")


def get_versions(
    slug: str,
    mc_version: str | None = None,
    loader: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, str] = {}
    if mc_version:
        params["game_versions"] = json.dumps([mc_version])
    if loader and loader.lower() not in {"", "vanilla"}:
        params["loaders"] = json.dumps([loader.lower()])
    versions = _request("GET", f"/project/{slug}/version", params=params or None)
    return versions if isinstance(versions, list) else []


def get_version(version_id: str) -> dict[str, Any]:
    return _request("GET", f"/version/{version_id}")


def pick_file(version: dict[str, Any]) -> dict[str, Any] | None:
    files = version.get("files") or []
    for file in files:
        if file.get("primary"):
            return file
    return files[0] if files else None


def pick_version(versions: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """API returns newest first; prefer a release, fall back to the newest."""
    versions = list(versions)
    if not versions:
        return None
    for version in versions:
        if version.get("version_type") == "release":
            return version
    return versions[0]


def download_version(version: dict[str, Any], dest_dir: Path) -> Path:
    file = pick_file(version)
    if not file:
        raise ModrinthError("version has no downloadable file")
    hashes = file.get("hashes") or {}
    return download_file(
        file["url"],
        Path(dest_dir) / file["filename"],
        expected_size=file.get("size"),
        expected_sha1=hashes.get("sha1"),
        description=file["filename"],
    )


def _hashes_in(directory: Path) -> dict[str, Path]:
    """sha1 -> path for every jar (and disabled jar) already installed."""
    result: dict[str, Path] = {}
    if not directory.is_dir():
        return result
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in {".jar", ".disabled"}:
            try:
                result[sha1_of(path)] = path
            except OSError:
                continue
    return result


def resolve_dependency(dependency: dict[str, Any], mc_version: str, loader: str) -> dict[str, Any] | None:
    """Turn a ``dependencies`` entry into a concrete version document."""
    version_id = dependency.get("version_id")
    if version_id:
        try:
            return get_version(str(version_id))
        except ModrinthError:
            return None
    project_id = dependency.get("project_id")
    if not project_id:
        return None
    try:
        versions = get_versions(str(project_id), mc_version, loader)
    except ModrinthError:
        return None
    return pick_version(versions)


def install_project(
    slug: str,
    mc_version: str,
    loader: str,
    dest_dir: Path,
    *,
    max_depth: int = 5,
    include_optional: bool = False,
    _depth: int = 0,
    _visited: set[str] | None = None,
    _hashes: dict[str, Path] | None = None,
) -> list[Path]:
    """Install a mod and (recursively) its required dependencies.

    Returns the list of files that were downloaded.
    """
    if loader.lower() == "vanilla":
        raise ModrinthError("Vanilla instances do not support mods; install a loader first")
    if _depth > max_depth:
        log_warn(f"Dependency depth limit ({max_depth}) reached at {slug}, stopping here.")
        return []

    visited = _visited if _visited is not None else set()
    installed_hashes = _hashes if _hashes is not None else _hashes_in(Path(dest_dir))
    downloaded: list[Path] = []

    project = get_project(slug)
    project_id = project.get("id", slug)
    if project_id in visited:
        return downloaded
    visited.add(project_id)

    versions = get_versions(slug, mc_version, loader)
    version = pick_version(versions)
    if not version:
        log_warn(
            f"No {loader} build of {slug} for MC {mc_version}; skipping."
        )
        return downloaded

    file = pick_file(version)
    if not file:
        log_warn(f"{slug} has no downloadable file; skipping.")
        return downloaded

    file_hash = (file.get("hashes") or {}).get("sha1")
    if file_hash and file_hash in installed_hashes:
        log_info(f"{project.get('title', slug)} is already installed, skipping.")
        return downloaded

    target_dir = Path(dest_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = download_version(version, target_dir)
    downloaded.append(path)
    if file_hash:
        installed_hashes[file_hash] = path

    dependencies = [
        dep
        for dep in version.get("dependencies") or []
        if dep.get("dependency_type") == "required"
        or (include_optional and dep.get("dependency_type") == "optional")
    ]
    if dependencies:
        log_info(f"{project.get('title', slug)}: installing {len(dependencies)} dependencies...")
    for number, dep in enumerate(dependencies, start=1):
        dep_version = resolve_dependency(dep, mc_version, loader)
        if not dep_version:
            log_warn(f"[{number}/{len(dependencies)}] dependency could not be resolved; skipped.")
            continue
        dep_project = dep_version.get("project_id")
        if dep_project in visited:
            continue
        dep_slug = dep_project or dep.get("project_id")
        if not dep_slug:
            continue
        log_info(f"[{number}/{len(dependencies)}] installing dependency {dep_slug}")
        try:
            downloaded.extend(
                install_project(
                    str(dep_slug),
                    mc_version,
                    loader,
                    target_dir,
                    max_depth=max_depth,
                    include_optional=include_optional,
                    _depth=_depth + 1,
                    _visited=visited,
                    _hashes=installed_hashes,
                )
            )
        except (ModrinthError, DownloadError) as exc:
            log_warn(f"Failed to install dependency {dep.get('project_id')}: {exc}")

    return downloaded


def check_updates(jars: list[Path], mc_version: str, loader: str) -> dict[str, dict[str, Any]]:
    """POST /version_files/update: map local sha1 -> latest compatible version."""
    hashes = []
    for jar in jars:
        try:
            hashes.append(sha1_of(jar))
        except OSError:
            continue
    if not hashes:
        return {}
    payload = {
        "hashes": hashes,
        "algorithm": "sha1",
        "loaders": [loader.lower()] if loader and loader.lower() != "vanilla" else [],
        "game_versions": [mc_version] if mc_version else [],
    }
    data = _request("POST", "/version_files/update", json=payload)
    return data if isinstance(data, dict) else {}


def fetch_and_download_modrinth(
    slug: str,
    mc_version: str,
    loader: str,
    dest_dir: Path,
    *,
    description: str | None = None,
) -> Path | None:
    """Download the newest compatible version of one project (no dependencies).

    Kept as a small convenience wrapper used by the shader loader installer.
    """
    if loader.lower() == "vanilla":
        log_warn("Vanilla instances cannot load mods; skipping.")
        return None
    versions = get_versions(slug, mc_version, loader)
    version = pick_version(versions)
    if not version:
        log_warn(f"No compatible {loader} build of {slug} for MC {mc_version}.")
        return None
    try:
        return download_version(version, Path(dest_dir))
    except (ModrinthError, DownloadError) as exc:
        log_warn(f"Could not download {slug}: {exc}")
        return None
