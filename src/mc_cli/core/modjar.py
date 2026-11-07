"""Read mod metadata out of local jar files (Fabric / Forge / NeoForge / Quilt)."""
from __future__ import annotations

import json
import re
import tomllib
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ModMeta:
    mod_id: str
    name: str
    version: str = ""
    loader: str = "unknown"
    depends: dict[str, str] = field(default_factory=dict)


def _read_member(zf: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        return zf.read(name)
    except KeyError:
        return None


def _from_fabric(zf: zipfile.ZipFile) -> ModMeta | None:
    raw = _read_member(zf, "fabric.mod.json")
    if not raw:
        return None
    data = json.loads(raw.decode("utf-8", errors="replace"))
    depends = data.get("depends") or {}
    if isinstance(depends, dict):
        depends = {str(k): str(v) for k, v in depends.items()}
    else:
        depends = {}
    return ModMeta(
        mod_id=str(data.get("id") or "?"),
        name=str(data.get("name") or data.get("id") or "?"),
        version=str(data.get("version") or ""),
        loader="Fabric",
        depends=depends,
    )


def _from_quilt(zf: zipfile.ZipFile) -> ModMeta | None:
    raw = _read_member(zf, "quilt.mod.json")
    if not raw:
        return None
    data = json.loads(raw.decode("utf-8", errors="replace"))
    loader = data.get("quilt_loader") or {}
    metadata = loader.get("metadata") or {}
    depends = loader.get("depends") or []
    dep_map: dict[str, str] = {}
    for dep in depends if isinstance(depends, list) else []:
        if isinstance(dep, dict) and dep.get("id"):
            dep_map[str(dep["id"])] = str(dep.get("version") or "*")
    return ModMeta(
        mod_id=str(loader.get("id") or "?"),
        name=str(metadata.get("name") or loader.get("id") or "?"),
        version=str(loader.get("version") or ""),
        loader="Quilt",
        depends=dep_map,
    )


def _from_forge_toml(zf: zipfile.ZipFile) -> ModMeta | None:
    raw = None
    for candidate in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        raw = _read_member(zf, candidate)
        if raw:
            break
    if not raw:
        return None
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="replace"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    mods = data.get("mods") or []
    if not isinstance(mods, list) or not mods:
        return None
    first = mods[0] if isinstance(mods[0], dict) else {}
    dependencies = {}
    for dep in data.get("dependencies") or []:
        if isinstance(dep, dict):
            for mod_id, entries in dep.items():
                if isinstance(entries, list) and entries:
                    entry = entries[0] if isinstance(entries[0], dict) else {}
                    dependencies[str(mod_id)] = str(entry.get("versionRange") or "*")
    loader = "NeoForge" if "neoforge" in str(data.get("modLoader", "")).lower() else "Forge"
    return ModMeta(
        mod_id=str(first.get("modId") or "?"),
        name=str(first.get("displayName") or first.get("modId") or "?"),
        version=str(first.get("version") or ""),
        loader=loader,
        depends=dependencies,
    )


def _from_mcmod_info(zf: zipfile.ZipFile) -> ModMeta | None:
    raw = _read_member(zf, "mcmod.info")
    if not raw:
        return None
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    entry = data[0] if isinstance(data, list) and data else data
    if not isinstance(entry, dict):
        return None
    return ModMeta(
        mod_id=str(entry.get("modid") or "?"),
        name=str(entry.get("name") or entry.get("modid") or "?"),
        version=str(entry.get("version") or ""),
        loader="Forge",
    )


def read_mod_metadata(path: Path) -> ModMeta | None:
    """Best-effort metadata for a jar (returns None when it is not a mod jar)."""
    try:
        with zipfile.ZipFile(path) as zf:
            for reader in (_from_fabric, _from_quilt, _from_forge_toml, _from_mcmod_info):
                try:
                    meta = reader(zf)
                except (json.JSONDecodeError, KeyError, ValueError, zipfile.BadZipFile):
                    meta = None
                if meta and meta.mod_id and meta.mod_id != "?":
                    return meta
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def looks_like_mod_jar(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    markers = {
        "fabric.mod.json",
        "quilt.mod.json",
        "META-INF/mods.toml",
        "META-INF/neoforge.mods.toml",
        "mcmod.info",
    }
    return bool(names & markers)


def normalize_version(version: str) -> str:
    return re.sub(r"^[vV]", "", version.strip())
