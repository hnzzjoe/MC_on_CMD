"""Scan .minecraft/versions/ and describe every instance."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

MC_VERSION_RE = re.compile(r"(?<!\d)(1\.\d+(?:\.\d+)?)(?!\d)")

LOADER_MARKERS = (
    # (library group, artifact, display name)
    ("net.fabricmc", "fabric-loader", "Fabric"),
    ("org.quiltmc", "quilt-loader", "Quilt"),
    ("net.neoforged", "neoforge", "NeoForge"),
    ("net.minecraftforge", "forge", "Forge"),
    ("net.minecraftforge", "fmlloader", "Forge"),
)

MAIN_CLASS_MARKERS = (
    ("net.fabricmc.loader", "Fabric"),
    ("org.quiltmc", "Quilt"),
)

ID_MARKERS = (
    ("fabric-loader", "Fabric"),
    ("quilt-loader", "Quilt"),
    ("neoforge", "NeoForge"),
    ("forge", "Forge"),
)


@dataclass(frozen=True)
class MCInstance:
    folder_name: str
    path: Path
    mc_version: str
    loader_type: str
    loader_version: Optional[str] = None
    json_path: Optional[Path] = None


@dataclass(frozen=True)
class ScanError:
    path: Path
    message: str


@dataclass
class ScanResult:
    """Result of scanning a versions folder; damaged instances are reported."""

    instances: list[MCInstance] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)

    def __iter__(self) -> Iterator[MCInstance]:
        return iter(self.instances)

    def __len__(self) -> int:
        return len(self.instances)

    def __bool__(self) -> bool:
        return bool(self.instances)

    @property
    def ok(self) -> bool:
        return not self.errors


def _mc_version_from_id(version_id: str) -> str | None:
    match = MC_VERSION_RE.search(version_id)
    return match.group(1) if match else None


def _detect_loader(data: dict, folder_name: str) -> tuple[str, str | None]:
    """Return (loader, loader_version) using libraries first, id as fallback."""
    libraries = [lib for lib in (data.get("libraries") or []) if isinstance(lib, dict)]
    for group, artifact, loader in LOADER_MARKERS:
        for lib in libraries:
            parts = str(lib.get("name", "")).split(":")
            if len(parts) >= 2 and parts[0] == group and parts[1] == artifact:
                version = parts[2] if len(parts) > 2 else None
                return loader, version

    main_class = str(data.get("mainClass") or "")
    if "cpw.mods.bootstraplauncher" in main_class:
        # Merged Forge/NeoForge profiles sometimes ship only the FML libraries.
        has_neoforge = any(
            str(lib.get("name", "")).lower().startswith("net.neoforged") for lib in libraries
        )
        return ("NeoForge", None) if has_neoforge else ("Forge", None)
    for marker, loader in MAIN_CLASS_MARKERS:
        if marker in main_class:
            return loader, None

    version_id = str(data.get("id") or folder_name).lower()
    for marker, loader in ID_MARKERS:
        if marker in version_id:
            suffix = version_id.split(marker, 1)[1].lstrip("-_")
            return loader, suffix or None
    return "Vanilla", None


def _resolve_mc_version(data: dict, folder_name: str, loader: str) -> str:
    for key in ("clientVersion", "inheritsFrom"):
        value = data.get(key)
        if value:
            return str(value)
    version_id = str(data.get("id") or folder_name)
    guessed = _mc_version_from_id(version_id)
    if guessed:
        return guessed
    return version_id if loader == "Vanilla" else "Unknown"


def scan_instances(minecraft_dir: Path) -> ScanResult:
    """Scan ``<minecraft_dir>/versions`` and collect valid instances + errors."""
    result = ScanResult()
    versions_dir = Path(minecraft_dir) / "versions"
    if not versions_dir.is_dir():
        result.errors.append(ScanError(versions_dir, "versions folder not found"))
        return result

    try:
        folders = sorted((p for p in versions_dir.iterdir() if p.is_dir()), key=lambda p: p.name.lower())
    except OSError as exc:
        result.errors.append(ScanError(versions_dir, f"cannot list folder: {exc}"))
        return result

    for folder in folders:
        json_path = folder / f"{folder.name}.json"
        if not json_path.is_file():
            result.errors.append(ScanError(folder, f"missing version json ({folder.name}.json)"))
            continue
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            result.errors.append(ScanError(json_path, f"invalid json: {exc}"))
            continue
        except OSError as exc:
            result.errors.append(ScanError(json_path, f"cannot read json: {exc}"))
            continue
        if not isinstance(data, dict):
            result.errors.append(ScanError(json_path, "version json is not an object"))
            continue

        loader, loader_version = _detect_loader(data, folder.name)
        result.instances.append(
            MCInstance(
                folder_name=folder.name,
                path=folder,
                mc_version=_resolve_mc_version(data, folder.name, loader),
                loader_type=loader,
                loader_version=loader_version,
                json_path=json_path,
            )
        )

    result.instances.sort(key=lambda x: x.folder_name.lower())
    return result
