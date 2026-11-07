"""Mojang / Fabric version metadata: install vanilla and Fabric profiles."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from mc_cli.config.manager import cache_dir
from mc_cli.core.instance import instance_json, write_json
from mc_cli.downloader.general import USER_AGENT, download_file
from mc_cli.utils.console import log_info, log_warn

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_META = "https://meta.fabricmc.net/v2"
MANIFEST_TTL = 6 * 3600


class MojangError(RuntimeError):
    pass


def _get_json(url: str) -> Any:
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        raise MojangError(f"request failed: {exc}") from exc
    except ValueError as exc:
        raise MojangError(f"invalid JSON from {url}") from exc


def get_manifest(force: bool = False) -> dict[str, Any]:
    """Version manifest, cached for a few hours under the config dir."""
    cache_file = cache_dir() / "version_manifest_v2.json"
    if not force and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("fetched", 0)) < MANIFEST_TTL:
                return cached["data"]
        except (OSError, ValueError, KeyError):
            pass

    log_info("Fetching Minecraft version manifest...")
    data = _get_json(MANIFEST_URL)
    try:
        cache_file.write_text(
            json.dumps({"fetched": time.time(), "data": data}), encoding="utf-8"
        )
    except OSError:
        pass
    return data


def list_versions(release_type: str | None = "release", limit: int | None = None) -> list[dict[str, Any]]:
    versions = get_manifest().get("versions") or []
    if release_type:
        versions = [v for v in versions if v.get("type") == release_type]
    return versions[:limit] if limit else versions


def get_version_meta(version_id: str) -> dict[str, Any]:
    for entry in get_manifest().get("versions") or []:
        if entry.get("id") == version_id:
            return _get_json(entry["url"])
    raise MojangError(f"unknown Minecraft version: {version_id}")


def install_vanilla(
    name: str,
    version_id: str,
    mc_dir: Path,
    *,
    download_client: bool = True,
) -> Path:
    """Create a vanilla profile folder ``versions/<name>``."""
    meta = get_version_meta(version_id)
    version_dir = Path(mc_dir) / "versions" / name
    version_dir.mkdir(parents=True, exist_ok=True)

    data = dict(meta)
    data["id"] = name
    data.setdefault("clientVersion", version_id)
    write_json(instance_json(version_dir), data)

    client = (meta.get("downloads") or {}).get("client") or {}
    if download_client and client.get("url"):
        try:
            download_file(
                client["url"],
                version_dir / f"{name}.jar",
                expected_size=client.get("size"),
                expected_sha1=client.get("sha1"),
                description=f"client {version_id}.jar",
            )
        except Exception as exc:
            log_warn(f"Could not download the client jar: {exc}")
    return version_dir


def list_fabric_loaders(mc_version: str) -> list[str]:
    data = _get_json(f"{FABRIC_META}/versions/loader/{mc_version}")
    return [str(item.get("loader", {}).get("version")) for item in data if item.get("loader")]


def install_fabric(
    name: str,
    mc_version: str,
    mc_dir: Path,
    loader_version: str | None = None,
) -> Path:
    """Create a Fabric profile, ensuring the vanilla parent profile exists."""
    mc_dir = Path(mc_dir)
    vanilla_dir = mc_dir / "versions" / mc_version
    if not instance_json(vanilla_dir).is_file():
        log_info(f"Downloading vanilla profile {mc_version} (parent of the Fabric profile)...")
        install_vanilla(mc_version, mc_version, mc_dir, download_client=True)

    if not loader_version:
        loaders = list_fabric_loaders(mc_version)
        if not loaders:
            raise MojangError(f"no Fabric loader available for Minecraft {mc_version}")
        loader_version = loaders[0]

    profile = _get_json(f"{FABRIC_META}/versions/loader/{mc_version}/{loader_version}/profile/json")
    profile["id"] = name
    profile["inheritsFrom"] = mc_version

    version_dir = mc_dir / "versions" / name
    version_dir.mkdir(parents=True, exist_ok=True)
    write_json(instance_json(version_dir), profile)
    return version_dir
