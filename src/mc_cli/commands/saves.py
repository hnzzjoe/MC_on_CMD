"""`mc-cli save ...` — list, back up, restore, import and export worlds."""
from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from stat import S_ISLNK

import typer
from rich.table import Table

from mc_cli.commands._common import confirm, require_workspace
from mc_cli.config.manager import get_int
from mc_cli.utils.console import console, log_error, log_info, log_success, log_warn

save_app = typer.Typer(help="Manage worlds (saves) and backups.", no_args_is_help=True)


def _dirs() -> tuple[Path, Path]:
    workspace, _ = require_workspace()
    from mc_cli.core.shared import resource_dir

    saves = resource_dir(workspace, "saves")
    backups = workspace / "backups"
    backups.mkdir(exist_ok=True)
    return saves, backups


def _valid_saves(saves_dir: Path) -> list[Path]:
    return sorted(
        (p for p in saves_dir.iterdir() if p.is_dir() and (p / "level.dat").is_file()),
        key=lambda p: p.name.lower(),
    )


def _backups(backups_dir: Path) -> list[Path]:
    return sorted(backups_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)


# ================= 安全解压 =================

def safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract avoiding path traversal and symlink members."""
    dest = Path(dest).resolve()
    for member in zf.infolist():
        mode = member.external_attr >> 16
        if S_ISLNK(mode):
            continue
        target = (dest / member.filename).resolve()
        if target != dest and dest not in target.parents:
            raise ValueError(f"unsafe path in archive: {member.filename}")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)


def _zip_save(save_path: Path, backup_file: Path) -> None:
    with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in save_path.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, Path(save_path.name) / file_path.relative_to(save_path))


# ================= 列表 =================

@save_app.command("list")
def list_saves() -> None:
    """List the worlds of the active instance."""
    saves_dir, _ = _dirs()
    saves = _valid_saves(saves_dir)
    if not saves:
        log_warn("No valid Minecraft saves found in this instance.")
        return

    table = Table(title=f"Saves in {saves_dir.parent.name}")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Save", style="green")
    table.add_column("Size", style="magenta", justify="right")
    table.add_column("Last modified", style="yellow")
    for index, save in enumerate(saves, start=1):
        size = sum(p.stat().st_size for p in save.rglob("*") if p.is_file())
        mtime = datetime.fromtimestamp(save.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(str(index), save.name, f"{size / (1024 * 1024):.2f} MB", mtime)
    console.print(table)


@save_app.command("list-backups")
def list_backups() -> None:
    """List backups of the active instance."""
    _, backups_dir = _dirs()
    backups = _backups(backups_dir)
    if not backups:
        log_warn("No backups found. Run `mc-cli save backup all` first.")
        return

    table = Table(title=f"Backups in {backups_dir.parent.name}")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("File", style="green")
    table.add_column("Size", style="magenta", justify="right")
    table.add_column("Created", style="yellow")
    for index, backup in enumerate(backups, start=1):
        mtime = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(
            str(index), backup.name, f"{backup.stat().st_size / (1024 * 1024):.2f} MB", mtime
        )
    console.print(table)


# ================= 备份 / 恢复 =================

@save_app.command("backup")
def backup(
    target: str = typer.Argument("all", help="Save name or 'all'"),
) -> None:
    """Back up one save or all saves into backups/."""
    saves_dir, backups_dir = _dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if target.lower() == "all":
        saves = _valid_saves(saves_dir)
        if not saves:
            log_warn("No valid saves to back up.")
            return
        backup_file = backups_dir / f"ALL_SAVES_{timestamp}.zip"
        log_info(f"Backing up {len(saves)} save(s) to {backup_file.name}...")
        try:
            with zipfile.ZipFile(backup_file, "w", zipfile.ZIP_DEFLATED) as zf:
                for save in saves:
                    for file_path in save.rglob("*"):
                        if file_path.is_file():
                            zf.write(file_path, Path(save.name) / file_path.relative_to(save))
        except OSError as exc:
            log_error(f"Backup failed: {exc}")
            raise typer.Exit(1)
        log_success(f"All saves backed up: {backup_file.name}")
        _maybe_clean(backups_dir)
        return

    save_path = saves_dir / target
    if not (save_path / "level.dat").is_file():
        log_error(f"Save not found or invalid: {target}")
        raise typer.Exit(1)
    backup_file = backups_dir / f"{save_path.name}_{timestamp}.zip"
    log_info(f"Backing up '{save_path.name}' to {backup_file.name}...")
    try:
        _zip_save(save_path, backup_file)
    except OSError as exc:
        log_error(f"Backup failed: {exc}")
        raise typer.Exit(1)
    log_success(f"Backed up '{save_path.name}': {backup_file.name}")
    _maybe_clean(backups_dir)


def _restore_into(saves_dir: Path, backups_dir: Path, staging: Path) -> int:
    """Merge a validated staging directory into saves/ (old worlds are kept)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    parked = backups_dir / "overwritten"
    restored = 0
    for candidate in sorted(staging.iterdir()):
        if not candidate.is_dir() or not (candidate / "level.dat").is_file():
            continue
        target = saves_dir / candidate.name
        if target.exists():
            parked.mkdir(parents=True, exist_ok=True)
            destination = parked / f"{candidate.name}-{timestamp}"
            shutil.move(str(target), str(destination))
            log_warn(f"Existing world '{candidate.name}' moved to {destination}")
        shutil.move(str(candidate), str(target))
        restored += 1
    return restored


def _backup_world_name(stem: str) -> str:
    return re.sub(r"_\d{8}_\d{6}$", "", stem)


@save_app.command("restore")
def restore(
    backup_name: str = typer.Argument(..., help="Backup file name"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Restore a backup after validating it in a temporary directory."""
    saves_dir, backups_dir = _dirs()
    backup_file = backups_dir / backup_name
    if not backup_file.is_file():
        log_error(f"Backup not found: {backup_name}")
        raise typer.Exit(1)
    if not confirm(f"Restore '{backup_name}'? Existing worlds are moved aside, not deleted.", yes):
        log_info("Cancelled.")
        return

    staging = Path(tempfile.mkdtemp(prefix="mccli_restore_"))
    try:
        try:
            with zipfile.ZipFile(backup_file) as zf:
                safe_extract(zf, staging)
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            log_error(f"Invalid backup archive: {exc}")
            raise typer.Exit(1)

        roots = [p for p in staging.iterdir() if p.is_dir() and (p / "level.dat").is_file()]
        if not roots:
            if not (staging / "level.dat").is_file():
                log_error("The backup does not contain a valid world (level.dat missing).")
                raise typer.Exit(1)
            # The archive root itself is one world: wrap it in a named folder.
            wrapper = staging / _backup_world_name(backup_file.stem)
            wrapper.mkdir(exist_ok=True)
            for child in list(staging.iterdir()):
                if child != wrapper:
                    shutil.move(str(child), str(wrapper / child.name))

        restored = _restore_into(saves_dir, backups_dir, staging)
        if not restored:
            log_error("Nothing was restored.")
            raise typer.Exit(1)
        log_success(f"Restored {restored} world(s) from {backup_name}.")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# ================= 导入 / 导出 =================

@save_app.command("import")
def import_save(
    zip_path: Path = typer.Argument(..., help="World .zip"),
    name: str = typer.Option("", "--name", help="World folder name (defaults to the archive name)"),
    replace: bool = typer.Option(False, "--replace", help="Replace an existing world with the same name"),
) -> None:
    """Import a world from a zip archive (validated via level.dat)."""
    saves_dir, _ = _dirs()
    if not zip_path.is_file() or zip_path.suffix.lower() != ".zip":
        log_error("Please provide a .zip archive.")
        raise typer.Exit(1)

    staging = Path(tempfile.mkdtemp(prefix="mccli_import_"))
    try:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                safe_extract(zf, staging)
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            log_error(f"Invalid archive: {exc}")
            raise typer.Exit(1)

        if (staging / "level.dat").is_file():
            source = staging
            target_name = name or zip_path.stem
        else:
            candidates = [p for p in staging.iterdir() if p.is_dir() and (p / "level.dat").is_file()]
            if len(candidates) != 1:
                log_error("The archive must contain exactly one world (a folder with level.dat).")
                raise typer.Exit(1)
            source = candidates[0]
            target_name = name or source.name
        target = saves_dir / target_name
        if target.exists():
            if not replace:
                log_error(f"World '{target_name}' already exists (use --replace).")
                raise typer.Exit(1)
            shutil.rmtree(target)
        shutil.move(str(source), str(target))
        log_success(f"Imported world '{target_name}'.")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


@save_app.command("export")
def export_save(
    name: str = typer.Argument(..., help="World name"),
    dest: Path | None = typer.Option(None, "--to", help="Destination file or folder"),
) -> None:
    """Export one world as a zip archive (for sharing)."""
    saves_dir, _ = _dirs()
    save_path = saves_dir / name
    if not (save_path / "level.dat").is_file():
        log_error(f"World not found: {name}")
        raise typer.Exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = Path(dest) if dest else Path.cwd()
    if destination.is_dir() or destination.suffix.lower() != ".zip":
        destination.mkdir(parents=True, exist_ok=True)
        destination = destination / f"{save_path.name}_{timestamp}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _zip_save(save_path, destination)
    except OSError as exc:
        log_error(f"Export failed: {exc}")
        raise typer.Exit(1)
    log_success(f"Exported '{save_path.name}' to {destination}")


# ================= 清理 =================

def _maybe_clean(backups_dir: Path) -> None:
    keep = max(get_int("backup_keep", 10), 1)
    backups = _backups(backups_dir)
    for old in backups[keep:]:
        try:
            old.unlink()
            log_info(f"Removed old backup: {old.name}")
        except OSError:
            pass


@save_app.command("clean")
def clean(
    keep: int | None = typer.Option(None, "--keep", "-k", min=1, help="How many backups to keep"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete old backups, keeping the most recent N."""
    _, backups_dir = _dirs()
    backups = _backups(backups_dir)
    keep_count = keep if keep is not None else max(get_int("backup_keep", 10), 1)
    old = backups[keep_count:]
    if not old:
        log_info(f"Nothing to clean ({len(backups)} backup(s), keeping {keep_count}).")
        return
    if not confirm(f"Delete {len(old)} old backup(s), keeping the newest {keep_count}?", yes):
        log_info("Cancelled.")
        return
    removed = 0
    for path in old:
        try:
            path.unlink()
            removed += 1
        except OSError as exc:
            log_warn(f"Could not delete {path.name}: {exc}")
    log_success(f"Removed {removed} backup(s).")
