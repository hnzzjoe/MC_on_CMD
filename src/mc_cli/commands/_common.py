"""Shared command helpers."""
from __future__ import annotations

from pathlib import Path

import typer

from mc_cli.config.manager import get_workspace
from mc_cli.core.instance import get_instance_info
from mc_cli.core.scanner import MCInstance
from mc_cli.utils.console import log_error, log_warn


def require_workspace() -> tuple[Path, MCInstance]:
    workspace = get_workspace()
    if not workspace:
        log_error("No active instance. Run `mc-cli instance use <name>` first.")
        raise typer.Exit(1)
    info = get_instance_info(workspace)
    if not info:
        log_error(f"Could not parse the active instance: {workspace}")
        raise typer.Exit(1)
    return workspace, info


def require_mods_dir() -> tuple[Path, MCInstance, Path]:
    workspace, info = require_workspace()
    from mc_cli.core.shared import resource_dir

    mods_dir = resource_dir(workspace, "mods")
    return workspace, info, mods_dir


def ensure_loader(info: MCInstance) -> None:
    if info.loader_type.lower() == "vanilla":
        log_error("This instance has no mod loader (vanilla). Install Fabric/Forge first.")
        raise typer.Exit(1)


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.2f} MB"


def confirm(message: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    return typer.confirm(message, default=False)
