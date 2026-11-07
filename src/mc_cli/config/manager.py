"""Persistent configuration for mc-cli.

Stored as JSON under %APPDATA%\\MCCliTool\\config.json (override the whole
directory with the MCCLI_CONFIG_DIR environment variable, handy for tests).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "MCCliTool"

DEFAULTS: dict[str, Any] = {
    "mc_dir": None,             # active .minecraft root
    "mc_dirs": [],              # additional roots managed by `mc-cli config root`
    "current_workspace": None,  # active instance folder (versions/<name>)
    "java_path": None,
    "backup_keep": 10,
    "animations": True,
    "shared": {"mods": False, "saves": False, "resourcepacks": False},
}

BOOL_KEYS = {"animations"}
INT_KEYS = {"backup_keep"}


def config_dir() -> Path:
    override = os.getenv("MCCLI_CONFIG_DIR")
    if override:
        return Path(override)
    appdata = os.getenv("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".config"
    return base / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"


def cache_dir() -> Path:
    path = config_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config() -> dict[str, Any]:
    """Return the config with defaults filled in. Never raises."""
    data: dict[str, Any] = json.loads(json.dumps(DEFAULTS))
    try:
        raw = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(raw, dict):
        return data
    data.update(raw)
    shared = dict(DEFAULTS["shared"])
    if isinstance(raw.get("shared"), dict):
        shared.update(raw["shared"])
    data["shared"] = shared
    return data


def save_config(data: dict[str, Any]) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def get(key: str, default: Any = None) -> Any:
    return load_config().get(key, DEFAULTS.get(key, default))


def get_bool(key: str, default: bool = False) -> bool:
    value = get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_int(key: str, default: int) -> int:
    try:
        return int(get(key, default))
    except (TypeError, ValueError):
        return default


def set_value(key: str, value: Any) -> None:
    data = load_config()
    data[key] = value
    save_config(data)


def reset_config() -> None:
    """Delete the config file (cache is kept)."""
    try:
        config_file().unlink()
    except FileNotFoundError:
        pass


# ================= .minecraft 目录 =================

def save_mc_dir(mc_dir: Path) -> None:
    data = load_config()
    data["mc_dir"] = str(Path(mc_dir).resolve())
    save_config(data)


def get_mc_dir() -> Path | None:
    raw = get("mc_dir")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_dir() else None


def list_mc_dirs() -> list[Path]:
    """All known roots; the active one first, then the extra saved ones."""
    result: list[Path] = []
    seen: set[str] = set()
    for raw in [get("mc_dir")] + list(get("mc_dirs") or []):
        if not raw:
            continue
        path = Path(raw)
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def add_mc_dir(mc_dir: Path) -> bool:
    """Register an extra root. Returns False when it was already known."""
    path = Path(mc_dir).resolve()
    data = load_config()
    known = {str(Path(p).resolve()).lower() for p in ([data.get("mc_dir")] + list(data.get("mc_dirs") or [])) if p}
    if str(path).lower() in known:
        return False
    dirs = list(data.get("mc_dirs") or [])
    dirs.append(str(path))
    data["mc_dirs"] = dirs
    save_config(data)
    return True


def remove_mc_dir(mc_dir: Path) -> bool:
    target = str(Path(mc_dir).resolve())
    data = load_config()
    dirs = [d for d in (data.get("mc_dirs") or []) if str(Path(d).resolve()) != target]
    changed = len(dirs) != len(data.get("mc_dirs") or [])
    data["mc_dirs"] = dirs
    if data.get("mc_dir") and str(Path(data["mc_dir"]).resolve()) == target:
        data["mc_dir"] = None
        data["current_workspace"] = None
        changed = True
    if changed:
        save_config(data)
    return changed


# ================= 工作区 =================

def save_workspace(workspace_path: Path) -> None:
    data = load_config()
    data["current_workspace"] = str(Path(workspace_path).resolve())
    save_config(data)


def get_workspace() -> Path | None:
    raw = get("current_workspace")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_dir():
        return None
    return path


def clear_workspace() -> None:
    data = load_config()
    data["current_workspace"] = None
    save_config(data)


def auto_detect_minecraft() -> Path | None:
    """Try the standard Windows locations of .minecraft."""
    candidates: list[Path] = []
    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / ".minecraft")
    home = Path.home()
    candidates.extend(
        [
            home / "AppData/Roaming/.minecraft",
            home / "curseforge/minecraft/Instances",
            Path("C:/Program Files (x86)/Minecraft Launcher"),
        ]
    )
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "versions").is_dir():
            return candidate.resolve()
    return None
