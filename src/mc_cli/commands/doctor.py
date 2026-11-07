"""`mc-cli doctor` — environment and instance diagnostics."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.table import Table

from mc_cli.config.manager import config_dir, get, get_mc_dir, get_workspace
from mc_cli.core.instance import get_instance_info, resolve_version_json
from mc_cli.core.java import find_java, java_major
from mc_cli.core.scanner import scan_instances
from mc_cli.utils.console import console, log_info

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    message: str


def _config_check() -> Check:
    directory = config_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return Check("Config folder", OK, str(directory))
    except OSError as exc:
        return Check("Config folder", FAIL, f"{directory}: {exc}")


def _root_check() -> Check:
    root = get_mc_dir()
    if not root:
        return Check(".minecraft root", FAIL, "not configured (use `mc-cli config root add <path>`)")
    if not (root / "versions").is_dir():
        return Check(".minecraft root", FAIL, f"{root} has no versions/ folder")
    return Check(".minecraft root", OK, str(root))


def _workspace_check() -> Check:
    workspace = get_workspace()
    if not workspace:
        return Check("Active instance", WARN, "none selected (use `mc-cli instance use <name>`)")
    try:
        resolve_version_json(workspace)
    except (OSError, ValueError) as exc:
        return Check("Active instance", FAIL, f"{workspace.name}: {exc}")
    return Check("Active instance", OK, workspace.name)


def _instances_check() -> Check:
    root = get_mc_dir()
    if not root:
        return Check("Instances", WARN, "no root configured")
    result = scan_instances(root)
    if result.errors:
        detail = "; ".join(f"{e.path.name}: {e.message}" for e in result.errors[:3])
        extra = f" (+{len(result.errors) - 3} more)" if len(result.errors) > 3 else ""
        return Check("Instances", WARN, f"{len(result.instances)} valid, {len(result.errors)} damaged: {detail}{extra}")
    return Check("Instances", OK, f"{len(result.instances)} valid")


def _java_check() -> Check:
    java = Path(get("java_path")) if get("java_path") else None
    exe = find_java(str(java) if java else None)
    if not exe:
        return Check("Java", FAIL, "no java.exe found; install Java or set java_path")

    required = None
    workspace = get_workspace()
    if workspace:
        try:
            merged, _ = resolve_version_json(workspace)
            required = (merged.get("javaVersion") or {}).get("majorVersion")
        except Exception:
            required = None

    major = java_major(exe)
    if major is None:
        return Check("Java", WARN, f"{exe} - could not determine the Java version")
    if required is not None and int(required) > major:
        return Check("Java", WARN, f"{exe} - Java {major} (the instance wants Java {required}+)")
    return Check("Java", OK, f"{exe} - Java {major}")


def _disk_check() -> Check:
    root = get_mc_dir() or Path.cwd()
    try:
        usage = shutil.disk_usage(root)
    except OSError as exc:
        return Check("Disk", WARN, str(exc))
    free_gb = usage.free / (1024 ** 3)
    status = OK if free_gb >= 5 else WARN
    return Check("Disk", status, f"{free_gb:.1f} GB free on {Path(root).anchor or root}")


def _backup_check() -> Check:
    workspace = get_workspace()
    if not workspace:
        return Check("Backups", WARN, "no active instance")
    backups = workspace / "backups"
    if not backups.is_dir():
        return Check("Backups", WARN, "none yet (`mc-cli save backup all`)")
    files = list(backups.glob("*.zip"))
    size = sum(p.stat().st_size for p in files)
    return Check("Backups", OK, f"{len(files)} backup(s), {size / (1024 * 1024):.1f} MB")


def _mods_check() -> Check:
    workspace = get_workspace()
    if not workspace:
        return Check("Mods", WARN, "no active instance")
    mods = workspace / "mods"
    if not mods.is_dir():
        return Check("Mods", OK, "no mods folder")
    jars = [p for p in mods.iterdir() if p.is_file() and p.suffix.lower() in {".jar", ".disabled"}]
    if not jars:
        return Check("Mods", OK, "no mods installed")
    info = get_instance_info(workspace)
    if info and info.loader_type == "Vanilla":
        return Check("Mods", WARN, f"{len(jars)} jar(s) but the instance is vanilla")
    return Check("Mods", OK, f"{len(jars)} jar(s)")


def doctor() -> None:
    """Check Java, paths, instance JSONs and disk space."""
    log_info("Running diagnostics...")
    checks = [
        _config_check(),
        _root_check(),
        _workspace_check(),
        _instances_check(),
        _java_check(),
        _disk_check(),
        _backup_check(),
        _mods_check(),
    ]

    table = Table(title="mc-cli doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Details", style="green")
    for check in checks:
        style = {OK: "green", WARN: "yellow", FAIL: "red"}.get(check.status, "white")
        table.add_row(check.name, f"[{style}]{check.status}[/{style}]", check.message)
    console.print(table)

    failures = sum(1 for c in checks if c.status == FAIL)
    warnings = sum(1 for c in checks if c.status == WARN)
    if failures:
        log_info(f"{failures} problem(s), {warnings} warning(s).")
        raise typer.Exit(1)
    log_info(f"All good ({warnings} warning(s)).")
