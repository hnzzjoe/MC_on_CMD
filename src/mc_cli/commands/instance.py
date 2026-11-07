"""`mc-cli instance ...` — manage Minecraft instances (version folders)."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from mc_cli.config.manager import (
    clear_workspace,
    get_mc_dir,
    get_workspace,
    save_mc_dir,
    save_workspace,
)
from mc_cli.core import instance as instances
from mc_cli.core.mojang import MojangError, install_fabric, install_vanilla, list_versions
from mc_cli.core.scanner import MCInstance, scan_instances
from mc_cli.utils.console import console, log_error, log_info, log_success, log_warn

instance_app = typer.Typer(help="Manage Minecraft instances (versions).", no_args_is_help=True)


def require_root() -> Path:
    root = get_mc_dir()
    if not root:
        log_error("No .minecraft directory configured. Run `mc-cli config root add <path>` first.")
        raise typer.Exit(1)
    if not (root / "versions").is_dir():
        log_error(f"{root} does not contain a 'versions' folder.")
        raise typer.Exit(1)
    return root


def find_instance(name: str) -> MCInstance:
    root = require_root()
    wanted = name.strip().lower()
    for inst in scan_instances(root).instances:
        if inst.folder_name.lower() == wanted:
            return inst
    log_error(f"Instance not found: {name}")
    raise typer.Exit(1)


def active_name() -> str | None:
    workspace = get_workspace()
    return workspace.name if workspace else None


@instance_app.command("list")
def list_instances() -> None:
    """List every instance under the active .minecraft."""
    root = require_root()
    result = scan_instances(root)
    if not result.instances:
        log_warn(f"No instances found in {root / 'versions'}.")
    else:
        active = active_name()
        table = Table(title=f"Instances in {root}")
        table.add_column("", style="bright_black", width=2)
        table.add_column("Folder", style="green")
        table.add_column("MC Version", style="magenta")
        table.add_column("Loader", style="yellow")
        table.add_column("Loader Version", style="blue")
        for inst in result.instances:
            mark = "*" if inst.folder_name == active else ""
            table.add_row(
                mark,
                inst.folder_name,
                inst.mc_version,
                inst.loader_type,
                inst.loader_version or "-",
            )
        console.print(table)
        if active:
            log_info(f"Active instance: {active}")
    for error in result.errors:
        log_warn(f"Skipped {error.path.name}: {error.message}")


@instance_app.command("use")
def use_instance(name: str = typer.Argument(..., help="Instance folder name")) -> None:
    """Select the active instance (no need to use `start` first)."""
    inst = find_instance(name)
    save_workspace(inst.path)
    root = inst.path.parent.parent
    if get_mc_dir() != root:
        save_mc_dir(root)
    log_success(f"Active instance: {inst.folder_name} (MC {inst.mc_version}, {inst.loader_type})")


@instance_app.command("current")
def current_instance() -> None:
    """Show the active .minecraft / instance."""
    root = get_mc_dir()
    workspace = get_workspace()
    log_info(f".minecraft: {root or '(not configured)'}")
    log_info(f"Instance  : {workspace.name if workspace else '(none)'}")


@instance_app.command("versions")
def available_versions(
    limit: int = typer.Option(20, "--limit", "-n", help="How many versions to show"),
    snapshots: bool = typer.Option(False, "--snapshots", help="Include snapshots"),
) -> None:
    """List Minecraft versions available from Mojang."""
    try:
        versions = list_versions(None if snapshots else "release", limit)
    except MojangError as exc:
        log_error(f"Could not fetch the version manifest: {exc}")
        raise typer.Exit(1)
    table = Table(title="Minecraft versions")
    table.add_column("Id", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Released", style="cyan")
    for item in versions:
        table.add_row(item.get("id", "?"), item.get("type", "?"), str(item.get("releaseTime", ""))[:10])
    console.print(table)


@instance_app.command("create")
def create_instance(
    name: str = typer.Argument(..., help="New instance folder name"),
    version: str = typer.Option(..., "--version", "-v", help="Minecraft version, e.g. 1.21.1"),
    loader: str = typer.Option("vanilla", "--loader", "-l", help="vanilla or fabric"),
    loader_version: str = typer.Option("", "--loader-version", help="Fabric loader version (latest by default)"),
) -> None:
    """Create an instance from the Mojang version manifest (or Fabric meta)."""
    root = require_root()
    versions_dir = root / "versions"
    try:
        name = instances.validate_instance_name(name, versions_dir)
    except ValueError as exc:
        log_error(str(exc))
        raise typer.Exit(1)

    try:
        if loader.lower() == "vanilla":
            log_info(f"Installing vanilla {version} as '{name}'...")
            path = install_vanilla(name, version, root)
        elif loader.lower() == "fabric":
            log_info(f"Installing Fabric {version} as '{name}'...")
            path = install_fabric(name, version, root, loader_version or None)
        else:
            log_error(f"Unsupported loader: {loader}. Only vanilla and fabric can be created automatically.")
            raise typer.Exit(1)
    except MojangError as exc:
        log_error(f"Instance creation failed: {exc}")
        raise typer.Exit(1)
    except OSError as exc:
        log_error(f"Instance creation failed: {exc}")
        raise typer.Exit(1)

    save_workspace(path)
    log_success(f"Instance '{name}' created at {path}")


@instance_app.command("clone")
def clone(
    source: str = typer.Argument(..., help="Instance to copy"),
    new_name: str = typer.Argument(..., help="Name of the copy"),
    with_data: bool = typer.Option(False, "--with-data", help="Also copy mods/config/shaderpacks"),
) -> None:
    """Clone an instance (libraries/assets are shared, so only the profile is copied)."""
    src = find_instance(source)
    try:
        target = instances.clone_instance(src.path, new_name, with_data=with_data)
    except (ValueError, OSError) as exc:
        log_error(f"Clone failed: {exc}")
        raise typer.Exit(1)
    log_success(f"Cloned '{src.folder_name}' -> '{target.name}'")


@instance_app.command("rename")
def rename(
    old: str = typer.Argument(..., help="Current instance name"),
    new: str = typer.Argument(..., help="New instance name"),
) -> None:
    """Rename an instance folder and its version json."""
    inst = find_instance(old)
    try:
        target = instances.rename_instance(inst.path, new)
    except (ValueError, OSError) as exc:
        log_error(f"Rename failed: {exc}")
        raise typer.Exit(1)
    workspace = get_workspace()
    if workspace and workspace.resolve() == inst.path.resolve():
        save_workspace(target)
    log_success(f"Renamed '{inst.folder_name}' -> '{target.name}'")


@instance_app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Instance to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask for confirmation"),
) -> None:
    """Delete an instance and everything inside it (mods, saves, config)."""
    inst = find_instance(name)
    if not yes:
        answer = typer.confirm(f"Delete '{inst.folder_name}' including its mods/saves/config?", default=False)
        if not answer:
            log_info("Cancelled.")
            return
    try:
        instances.delete_instance(inst.path)
    except (ValueError, OSError) as exc:
        log_error(f"Delete failed: {exc}")
        raise typer.Exit(1)
    workspace = get_workspace()
    if workspace and workspace.resolve() == inst.path.resolve():
        clear_workspace()
    log_success(f"Deleted '{inst.folder_name}'")
