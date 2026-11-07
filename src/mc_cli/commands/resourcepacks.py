"""`mc-cli resourcepack ...` — manage resource packs and options.txt."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import typer
from rich.table import Table

from mc_cli.commands._common import confirm, require_workspace
from mc_cli.downloader import modrinth
from mc_cli.downloader.general import DownloadError
from mc_cli.utils.console import console, log_error, log_info, log_success, log_warn

resourcepack_app = typer.Typer(help="Manage resource packs.", no_args_is_help=True)


def _packs_dir(workspace: Path) -> Path:
    from mc_cli.core.shared import resource_dir

    return resource_dir(workspace, "resourcepacks")


def _entries(workspace: Path) -> list[Path]:
    directory = _packs_dir(workspace)
    entries = [p for p in directory.iterdir() if p.is_dir() or p.suffix.lower() == ".zip"]
    return sorted(entries, key=lambda p: p.name.lower())


def _find_entry(workspace: Path, name: str) -> Path | None:
    wanted = name.strip().strip('"').strip("'").lower()
    for entry in _entries(workspace):
        candidates = {entry.name.lower(), entry.stem.lower()}
        if wanted in candidates or any(wanted in c for c in candidates):
            return entry
    return None


# ================= options.txt =================

def options_path(workspace: Path) -> Path:
    return Path(workspace) / "options.txt"


def read_options(workspace: Path) -> list[str]:
    path = options_path(workspace)
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def enabled_packs(workspace: Path) -> list[str]:
    for line in read_options(workspace):
        if line.startswith("resourcePacks:"):
            raw = line[len("resourcePacks:"):].strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return []
            return [str(item) for item in data] if isinstance(data, list) else []
    return []


def set_enabled_packs(workspace: Path, packs: list[str]) -> None:
    path = options_path(workspace)
    lines = read_options(workspace)
    value = json.dumps(packs, separators=(",", ":"))
    new_line = f"resourcePacks:{value}"
    replaced = False
    output: list[str] = []
    for line in lines:
        if line.startswith("resourcePacks:"):
            output.append(new_line)
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _is_enabled(workspace: Path, entry: Path) -> bool:
    current = enabled_packs(workspace)
    return f"file/{entry.name}" in current or entry.name in current


def _set_enabled(workspace: Path, entry: Path, enable: bool) -> bool:
    current = enabled_packs(workspace)
    key = f"file/{entry.name}"
    legacy = entry.name
    present = key in current or legacy in current
    if enable and not present:
        current.append(key)
        set_enabled_packs(workspace, current)
        return True
    if not enable and present:
        set_enabled_packs(workspace, [p for p in current if p not in {key, legacy}])
        return True
    return False


def _validate_pack(path: Path) -> str:
    if not path.is_file():
        return f"file not found: {path}"
    if path.suffix.lower() != ".zip":
        return "resource packs must be .zip archives"
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        return "not a valid zip archive"
    if "pack.mcmeta" in names:
        return ""
    if any(name.endswith("/pack.mcmeta") and name.count("/") == 1 for name in names):
        return ""
    return "the archive does not contain a pack.mcmeta at its root"


@resourcepack_app.command("list")
def list_packs() -> None:
    """List installed resource packs and the enabled ones."""
    workspace, _ = require_workspace()
    entries = _entries(workspace)
    if not entries:
        log_warn("No resource packs installed. Use `mc-cli resourcepack import <zip>`.")
        return
    table = Table(title="Resource packs")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Size", style="yellow", justify="right")
    table.add_column("Enabled", style="white")
    for index, entry in enumerate(entries, start=1):
        size = (
            sum(p.stat().st_size for p in entry.rglob("*") if p.is_file())
            if entry.is_dir()
            else entry.stat().st_size
        )
        table.add_row(
            str(index),
            entry.name,
            "folder" if entry.is_dir() else "zip",
            f"{size / (1024 * 1024):.2f} MB",
            "*" if _is_enabled(workspace, entry) else "",
        )
    console.print(table)


@resourcepack_app.command("import")
def import_pack(
    zip_path: Path = typer.Argument(..., help="Local resource pack .zip"),
    no_enable: bool = typer.Option(False, "--no-enable", help="Copy without enabling"),
) -> None:
    """Import a local resource pack and enable it."""
    workspace, _ = require_workspace()
    problem = _validate_pack(zip_path)
    if problem:
        log_error(problem)
        raise typer.Exit(1)
    target = _packs_dir(workspace) / zip_path.name
    shutil.copy2(zip_path, target)
    log_success(f"Imported {target.name}")
    if not no_enable and _set_enabled(workspace, target, True):
        log_success(f"Enabled {target.name}")


@resourcepack_app.command("enable")
def enable(name: str = typer.Argument(..., help="Pack name (or part of it)")) -> None:
    """Enable an installed resource pack."""
    workspace, _ = require_workspace()
    entry = _find_entry(workspace, name)
    if not entry:
        log_error(f"No resource pack matched '{name}'.")
        raise typer.Exit(1)
    if _set_enabled(workspace, entry, True):
        log_success(f"Enabled {entry.name}")
    else:
        log_info(f"{entry.name} is already enabled.")


@resourcepack_app.command("disable")
def disable(name: str = typer.Argument(..., help="Pack name (or part of it)")) -> None:
    """Disable an installed resource pack."""
    workspace, _ = require_workspace()
    entry = _find_entry(workspace, name)
    if not entry:
        log_error(f"No resource pack matched '{name}'.")
        raise typer.Exit(1)
    if _set_enabled(workspace, entry, False):
        log_success(f"Disabled {entry.name}")
    else:
        log_info(f"{entry.name} is already disabled.")


@resourcepack_app.command("delete")
def delete(name: str = typer.Argument(..., help="Pack name"), yes: bool = typer.Option(False, "--yes", "-y")) -> None:
    """Delete a resource pack (with confirmation)."""
    workspace, _ = require_workspace()
    entry = _find_entry(workspace, name)
    if not entry:
        log_error(f"No resource pack matched '{name}'.")
        raise typer.Exit(1)
    if not confirm(f"Delete resource pack '{entry.name}'?", yes):
        log_info("Cancelled.")
        return
    _set_enabled(workspace, entry, False)
    if entry.is_dir():
        shutil.rmtree(entry)
    else:
        entry.unlink()
    log_success(f"Deleted {entry.name}")


@resourcepack_app.command("install")
def install(slug: str = typer.Argument(..., help="Modrinth project slug")):
    """Install a resource pack from Modrinth."""
    workspace, info = require_workspace()
    try:
        project = modrinth.get_project(slug)
        versions = modrinth.get_versions(slug, info.mc_version, None)
        version = modrinth.pick_version(versions) or modrinth.pick_version(
            modrinth.get_versions(slug, None, None)
        )
        if not version:
            log_error(f"No downloadable version for {slug}.")
            raise typer.Exit(1)
        path = modrinth.download_version(version, _packs_dir(workspace))
    except (modrinth.ModrinthError, DownloadError) as exc:
        log_error(f"Install failed: {exc}")
        raise typer.Exit(1)
    log_success(f"Installed {project.get('title', slug)} -> {path.name}")
    if _set_enabled(workspace, Path(path), True):
        log_success(f"Enabled {path.name}")
