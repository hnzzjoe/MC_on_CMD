"""`mc-cli shader ...` — shader loader installation and shaderpack management."""
from __future__ import annotations

import datetime
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer
from rich.table import Table

from mc_cli.commands._common import confirm, require_workspace
from mc_cli.core.instance import get_instance_info
from mc_cli.downloader.modrinth import ModrinthError, fetch_and_download_modrinth
from mc_cli.utils.console import console, log_error, log_info, log_success, log_warn

shader_app = typer.Typer(help="Manage shaders and the Iris/Oculus loader.", no_args_is_help=True)

IRIS_HEADER = "#This file stores configuration options for Iris, such as the currently active shaderpack"


# ================= Iris 配置 =================

def iris_config_path(workspace: Path) -> Path:
    return Path(workspace) / "config" / "iris.properties"


def read_iris_config(workspace: Path) -> dict[str, str]:
    path = iris_config_path(workspace)
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            result[key.strip()] = value.strip()
    except OSError:
        return {}
    return result


def write_iris_config(workspace: Path, updates: dict[str, str]) -> Path:
    path = iris_config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = read_iris_config(workspace)
    lines: list[str] = []
    if path.is_file():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
    if not lines:
        now = datetime.datetime.now().strftime("%a %b %d %H:%M:%S CST %Y")
        lines = [IRIS_HEADER, f"#{now}", ""]

    keys_written: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                output.append(f"{key}={updates[key]}")
                keys_written.add(key)
                continue
        output.append(line)
    for key, value in updates.items():
        if key not in keys_written:
            output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")
    return path


def _shader_entries(workspace: Path) -> list[Path]:
    shaderpacks = Path(workspace) / "shaderpacks"
    if not shaderpacks.is_dir():
        return []
    entries = [p for p in shaderpacks.iterdir() if p.is_dir() or p.suffix.lower() == ".zip"]
    return sorted(entries, key=lambda p: p.name.lower())


def _find_entry(workspace: Path, name: str) -> Path | None:
    wanted = name.strip().strip('"').strip("'").lower()
    for entry in _shader_entries(workspace):
        candidates = {entry.name.lower(), entry.stem.lower()}
        if wanted in candidates or any(wanted in c for c in candidates):
            return entry
    return None


def _active_shader(workspace: Path) -> str:
    return read_iris_config(workspace).get("shaderPack", "").strip()


# ================= 光影加载器 =================

def _download_loader_mods(info, mods_dir: Path, slugs: list[str]) -> int:
    failures = 0

    def fetch(slug: str) -> bool:
        try:
            return bool(fetch_and_download_modrinth(slug, info.mc_version, info.loader_type, mods_dir))
        except (ModrinthError, Exception) as exc:  # noqa: BLE001 - report and continue
            log_warn(f"{slug}: {exc}")
            return False

    with ThreadPoolExecutor(max_workers=len(slugs) or 1) as pool:
        futures = {pool.submit(fetch, slug): slug for slug in slugs}
        for future in as_completed(futures):
            if not future.result():
                failures += 1
    return failures


def install_shader_loader(workspace: Path) -> None:
    info = get_instance_info(workspace)
    if not info:
        log_error("Failed to parse workspace info.")
        raise typer.Exit(1)

    log_info(f"Target: MC {info.mc_version} | Loader: {info.loader_type}")
    mods_dir = Path(workspace) / "mods"
    mods_dir.mkdir(exist_ok=True)

    if info.loader_type in {"Fabric", "Quilt", "NeoForge"}:
        log_info("Installing Iris + Sodium...")
        failures = _download_loader_mods(info, mods_dir, ["iris", "sodium"])
    elif info.loader_type == "Forge":
        log_info("Installing Oculus + Embeddium...")
        failures = _download_loader_mods(info, mods_dir, ["oculus", "embeddium"])
    else:
        log_warn("Vanilla instances do not support shaders. Install a mod loader first.")
        return

    if failures:
        log_warn(f"{failures} shader loader component(s) could not be installed.")
    else:
        log_success("Shader loader installed.")


@shader_app.command("install")
def install() -> None:
    """Install the shader loader (Iris+Sodium / Oculus+Embeddium) for this instance."""
    workspace, info = require_workspace()
    install_shader_loader(workspace)


# ================= 光影包管理 =================

def _validate_shader_zip(path: Path) -> str:
    """Return an error message when the zip is not a shaderpack, else ''."""
    if not path.is_file():
        return f"file not found: {path}"
    if path.suffix.lower() != ".zip":
        return "shaderpacks must be .zip archives"
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except zipfile.BadZipFile:
        return "not a valid zip archive"
    if not names:
        return "the archive is empty"
    if any(name.startswith("shaders/") or "/shaders/" in name for name in names):
        return ""
    return "the archive does not contain a 'shaders' folder"


@shader_app.command("import")
def import_shader_pack(
    zip_path: Path = typer.Argument(..., help="Local shaderpack .zip"),
    no_enable: bool = typer.Option(False, "--no-enable", help="Do not activate the shaderpack"),
) -> None:
    """Import a local shaderpack into shaderpacks/ and activate it."""
    workspace, info = require_workspace()
    if info.loader_type == "Vanilla":
        log_error("Vanilla instances cannot load shaderpacks. Install a mod loader first.")
        raise typer.Exit(1)
    problem = _validate_shader_zip(zip_path)
    if problem:
        log_error(problem)
        raise typer.Exit(1)

    mods_dir = workspace / "mods"
    has_iris = any("iris" in p.name.lower() for p in mods_dir.glob("*.jar")) if mods_dir.is_dir() else False
    if info.loader_type in {"Fabric", "Quilt", "NeoForge"} and not has_iris:
        log_error("Iris is not installed. Run `mc-cli shader install` first.")
        raise typer.Exit(1)
    if info.loader_type == "Forge":
        has_oculus = any("oculus" in p.name.lower() for p in mods_dir.glob("*.jar")) if mods_dir.is_dir() else False
        if not has_oculus:
            log_error("Oculus is not installed. Run `mc-cli shader install` first.")
            raise typer.Exit(1)

    shaderpacks_dir = workspace / "shaderpacks"
    shaderpacks_dir.mkdir(exist_ok=True)
    target = shaderpacks_dir / zip_path.name
    shutil.copy2(zip_path, target)
    log_success(f"Imported {target.name}")
    if not no_enable and info.loader_type != "Forge":
        write_iris_config(workspace, {"enableShaders": "true", "shaderPack": target.name})
        log_success(f"Activated shaderpack: {target.name}")


@shader_app.command("list")
def list_shaders() -> None:
    """List installed shaderpacks and the active one."""
    workspace, _ = require_workspace()
    entries = _shader_entries(workspace)
    if not entries:
        log_warn("No shaderpacks installed. Use `mc-cli shader import <zip>`.")
        return

    active = _active_shader(workspace)
    table = Table(title="Shaderpacks")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Size", style="yellow", justify="right")
    table.add_column("Active", style="white")
    for index, entry in enumerate(entries, start=1):
        is_active = entry.name == active or (not entry.suffix and entry.name == active)
        if entry.is_dir():
            size = sum(p.stat().st_size for p in entry.rglob("*") if p.is_file())
            kind = "folder"
        else:
            size = entry.stat().st_size
            kind = "zip"
        table.add_row(
            str(index),
            entry.name,
            kind,
            f"{size / (1024 * 1024):.2f} MB",
            "*" if is_active else "",
        )
    console.print(table)
    if not active:
        log_info("No shaderpack is currently enabled.")


@shader_app.command("use")
def use_shader(name: str = typer.Argument(..., help="Shaderpack name (or part of it)")) -> None:
    """Activate an installed shaderpack."""
    workspace, _ = require_workspace()
    entry = _find_entry(workspace, name)
    if not entry:
        log_error(f"No shaderpack matched '{name}'.")
        raise typer.Exit(1)
    write_iris_config(workspace, {"enableShaders": "true", "shaderPack": entry.name})
    log_success(f"Active shaderpack: {entry.name}")


@shader_app.command("delete")
def delete_shader(
    name: str = typer.Argument(..., help="Shaderpack name"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Delete a shaderpack (with confirmation)."""
    workspace, _ = require_workspace()
    entry = _find_entry(workspace, name)
    if not entry:
        log_error(f"No shaderpack matched '{name}'.")
        raise typer.Exit(1)
    if not confirm(f"Delete shaderpack '{entry.name}'?", yes):
        log_info("Cancelled.")
        return
    if entry.is_dir():
        shutil.rmtree(entry)
    else:
        entry.unlink()
    if _active_shader(workspace) == entry.name:
        write_iris_config(workspace, {"enableShaders": "false", "shaderPack": ""})
    log_success(f"Deleted shaderpack: {entry.name}")
