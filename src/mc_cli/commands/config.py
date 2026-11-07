"""`mc-cli config ...` — view/edit settings and manage .minecraft roots."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from mc_cli.config.manager import (
    DEFAULTS,
    add_mc_dir,
    clear_workspace,
    config_file,
    get,
    get_mc_dir,
    list_mc_dirs,
    load_config,
    remove_mc_dir,
    reset_config,
    save_config,
    save_mc_dir,
)
from mc_cli.utils.console import console, log_error, log_info, log_success, log_warn

config_app = typer.Typer(help="View and edit mc-cli settings.", no_args_is_help=True)
root_app = typer.Typer(help="Manage known .minecraft directories.", no_args_is_help=True)
config_app.add_typer(root_app, name="root")


@config_app.command("show")
def show() -> None:
    """Show the current configuration and where it is stored."""
    data = load_config()
    table = Table(title="mc-cli configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    for key in DEFAULTS:
        if key == "shared":
            value = ", ".join(f"{k}={'on' if v else 'off'}" for k, v in data["shared"].items())
        else:
            value = str(data.get(key))
        table.add_row(key, value)
    console.print(table)
    log_info(f"Config file: {config_file()}")


@config_app.command("set")
def set_value(
    key: str = typer.Argument(..., help="backup_keep | java_path | animations | shared.*"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Change one setting."""
    key = key.strip()
    data = load_config()
    if key == "backup_keep":
        try:
            number = int(value)
        except ValueError:
            log_error("backup_keep must be an integer")
            raise typer.Exit(1)
        if number < 1:
            log_error("backup_keep must be at least 1")
            raise typer.Exit(1)
        data[key] = number
    elif key == "java_path":
        path = Path(value.strip('"').strip("'"))
        if not path.is_file():
            log_error(f"Java executable not found: {path}")
            raise typer.Exit(1)
        data[key] = str(path)
    elif key == "animations":
        data[key] = value.strip().lower() in {"1", "true", "yes", "on"}
    elif key.startswith("shared."):
        kind = key.split(".", 1)[1]
        if kind not in {"mods", "saves", "resourcepacks"}:
            log_error("shared.* must be shared.mods, shared.saves or shared.resourcepacks")
            raise typer.Exit(1)
        data["shared"][kind] = value.strip().lower() in {"1", "true", "yes", "on"}
    else:
        log_error(f"Unknown key: {key}")
        log_info(
            "Known keys: backup_keep, java_path, animations, "
            "shared.mods, shared.saves, shared.resourcepacks"
        )
        raise typer.Exit(1)
    save_config(data)
    shown = data["shared"][key.split(".", 1)[1]] if key.startswith("shared.") else data[key]
    log_success(f"{key} = {shown}")


@config_app.command("reset")
def reset(yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Delete the config file and restore defaults."""
    if not yes and not typer.confirm(f"Reset {config_file()}?", default=False):
        log_info("Cancelled.")
        return
    reset_config()
    log_success("Configuration reset.")


# ================= .minecraft 根目录 =================

def _show_roots() -> None:
    roots = list_mc_dirs()
    active = get_mc_dir()
    table = Table(title=".minecraft directories")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("", width=2)
    table.add_column("Path", style="green")
    table.add_column("Valid", style="yellow")
    for index, path in enumerate(roots, start=1):
        valid = "yes" if (path / "versions").is_dir() else "missing versions/"
        table.add_row(str(index), "*" if active and path.resolve() == active.resolve() else "", str(path), valid)
    console.print(table)


@root_app.command("list")
def root_list() -> None:
    """List known .minecraft directories."""
    _show_roots()


def _resolve_root(token: str) -> Path:
    roots = list_mc_dirs()
    if token.isdigit():
        index = int(token)
        if not 1 <= index <= len(roots):
            log_error(f"No root #{index} (see `mc-cli config root list`).")
            raise typer.Exit(1)
        return roots[index - 1]
    path = Path(token.strip().strip('"').strip("'")).expanduser()
    if not path.is_dir():
        log_error(f"Not a directory: {path}")
        raise typer.Exit(1)
    return path.resolve()


@root_app.command("add")
def root_add(
    path: str = typer.Argument(..., help="Path to a .minecraft folder"),
    use: bool = typer.Option(False, "--use", help="Also make it the active root"),
) -> None:
    """Register a .minecraft directory (it must contain versions/)."""
    target = Path(path.strip().strip('"').strip("'")).expanduser()
    if not target.is_dir():
        log_error(f"Not a directory: {target}")
        raise typer.Exit(1)
    if not (target / "versions").is_dir():
        log_error(f"{target} does not contain a 'versions' folder.")
        raise typer.Exit(1)
    target = target.resolve()
    if add_mc_dir(target):
        log_success(f"Registered: {target}")
    else:
        log_info("Already registered.")
    if use or not get_mc_dir():
        save_mc_dir(target)
        clear_workspace()
        log_success(f"Active .minecraft: {target}")


@root_app.command("use")
def root_use(target: str = typer.Argument(..., help="Index from `root list` or a path")) -> None:
    """Switch the active .minecraft directory."""
    path = _resolve_root(target)
    if not (path / "versions").is_dir():
        log_error(f"{path} does not contain a 'versions' folder.")
        raise typer.Exit(1)
    save_mc_dir(path)
    clear_workspace()
    log_success(f"Active .minecraft: {path}")


@root_app.command("remove")
def root_remove(target: str = typer.Argument(..., help="Index from `root list` or a path")) -> None:
    """Forget a .minecraft directory (nothing is deleted)."""
    path = _resolve_root(target)
    if remove_mc_dir(path):
        log_success(f"Removed: {path}")
    else:
        log_warn(f"Not registered: {path}")
