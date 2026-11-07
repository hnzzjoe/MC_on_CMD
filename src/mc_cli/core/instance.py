"""Instance helpers shared by commands: lookup, version resolution, CRUD."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from mc_cli.config.manager import get_workspace
from mc_cli.core.scanner import MCInstance, scan_instances

INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def mc_root_of(instance_path: Path) -> Path:
    """``.../.minecraft/versions/<name>`` -> ``.../.minecraft``."""
    return Path(instance_path).resolve().parent.parent


def instance_json(instance_path: Path) -> Path:
    instance_path = Path(instance_path)
    return instance_path / f"{instance_path.name}.json"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def get_instance_info(workspace: Path | None = None) -> MCInstance | None:
    """Find the MCInstance for a workspace folder."""
    ws = Path(workspace) if workspace is not None else get_workspace()
    if not ws or not ws.is_dir():
        return None
    for inst in scan_instances(ws.parent.parent).instances:
        if inst.path.resolve() == ws.resolve():
            return inst
    return None


# ================= 版本 JSON 解析（inheritsFrom 合并） =================

def _library_key(lib: dict[str, Any]) -> tuple[str, str, str, str]:
    """Identity of a library independent of its version (for override)."""
    name = lib.get("name", "")
    extension = "jar"
    if "@" in name:
        name, extension = name.split("@", 1)
    parts = name.split(":")
    group = parts[0] if parts else ""
    artifact = parts[1] if len(parts) > 1 else ""
    classifier = parts[3] if len(parts) > 3 else ""
    return group, artifact, classifier, extension


def _merge_chain(chain: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge child -> parent -> ... into a single version document."""
    merged: dict[str, Any] = {}
    libraries: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for data in reversed(chain):  # base version first, child last (overrides)
        for key, value in data.items():
            if key in {"libraries", "arguments"}:
                continue
            merged[key] = value
        arguments = data.get("arguments")
        if isinstance(arguments, dict):
            target = merged.setdefault("arguments", {"game": [], "jvm": []})
            for kind in ("game", "jvm"):
                if arguments.get(kind):
                    target.setdefault(kind, []).extend(arguments[kind])
        for lib in data.get("libraries") or []:
            if isinstance(lib, dict):
                libraries[_library_key(lib)] = lib

    merged["libraries"] = list(libraries.values())
    return merged


def resolve_version_json(instance_path: Path) -> tuple[dict[str, Any], list[str]]:
    """Resolve an instance json together with all ``inheritsFrom`` parents.

    Returns ``(merged_document, chain)`` where chain[0] is the instance itself
    and the last element is the root (vanilla) profile.
    """
    instance_path = Path(instance_path)
    chain: list[dict[str, Any]] = []
    names: list[str] = []
    visited: set[str] = set()
    current = instance_path

    while current is not None:
        key = str(current.resolve()).lower()
        if key in visited:
            raise ValueError(f"inheritsFrom cycle detected at {current}")
        visited.add(key)

        json_path = instance_json(current)
        if not json_path.is_file():
            raise FileNotFoundError(f"version json not found: {json_path}")
        data = load_json(json_path)
        chain.append(data)
        names.append(current.name)

        parent_id = data.get("inheritsFrom")
        if not parent_id:
            break
        current = current.parent / str(parent_id)

    return _merge_chain(chain), names


def base_version_name(chain: list[str]) -> str:
    """The root profile name, normally the vanilla version id."""
    return chain[-1] if chain else "Unknown"


# ================= 实例 CRUD =================

def validate_instance_name(name: str, versions_dir: Path | None = None) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("instance name must not be empty")
    if name in {".", ".."} or INVALID_NAME_CHARS.search(name):
        raise ValueError(f"invalid instance name: {name!r}")
    if versions_dir is not None and (Path(versions_dir) / name).exists():
        raise ValueError(f"instance already exists: {name}")
    return name


def rename_instance(instance_path: Path, new_name: str) -> Path:
    """Rename the folder, the json file and the ``id`` inside it."""
    instance_path = Path(instance_path).resolve()
    new_name = validate_instance_name(new_name, instance_path.parent)
    if instance_path.name == new_name:
        return instance_path

    old_json = instance_json(instance_path)
    data = load_json(old_json) if old_json.is_file() else {}
    data["id"] = new_name

    target = instance_path.parent / new_name
    instance_path.rename(target)
    try:
        old_json.unlink(missing_ok=True)
    except OSError:
        pass
    write_json(instance_json(target), data)
    return target


def clone_instance(source: Path, new_name: str, with_data: bool = False) -> Path:
    """Clone an instance folder.

    Libraries and assets live in the shared .minecraft root, so only the
    version json (plus optionally mods/config) has to be duplicated.
    """
    source = Path(source).resolve()
    new_name = validate_instance_name(new_name, source.parent)
    target = source.parent / new_name
    target.mkdir(parents=True)
    try:
        data = load_json(instance_json(source))
        data["id"] = new_name
        write_json(instance_json(target), data)
        if with_data:
            for folder in ("mods", "config", "shaderpacks", "resourcepacks"):
                src = source / folder
                if src.is_dir():
                    shutil.copytree(src, target / folder)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def delete_instance(instance_path: Path) -> None:
    """Remove an instance folder (contains its own mods/saves/config)."""
    instance_path = Path(instance_path).resolve()
    if not instance_path.is_dir() or instance_path.parent.name != "versions":
        raise ValueError(f"refusing to delete unexpected path: {instance_path}")
    shutil.rmtree(instance_path)
