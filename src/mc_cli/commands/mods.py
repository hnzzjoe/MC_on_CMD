"""`mc-cli mod ...` — search, install, update and inspect mods."""
from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path

import typer
from rich.table import Table

from mc_cli.commands._common import (
    ensure_loader,
    format_size,
    require_mods_dir,
    require_workspace,
)
from mc_cli.downloader import modrinth
from mc_cli.downloader.general import DownloadError, sha1_of
from mc_cli.core.modjar import looks_like_mod_jar, read_mod_metadata
from mc_cli.utils.console import console, is_interactive, log_error, log_info, log_success, log_warn

mod_app = typer.Typer(help="Manage mods (Modrinth).", no_args_is_help=True)

KNOWN_INCOMPATIBLE = [
    ({"optifine", "sodium"}, "OptiFine and Sodium cannot be used together"),
    ({"optifine", "embeddium"}, "OptiFine and Embeddium cannot be used together"),
    ({"optifine", "iris"}, "OptiFine and Iris cannot be used together"),
    ({"sodium", "embeddium"}, "Sodium and Embeddium are two implementations of the same renderer"),
]


def _mod_files(mods_dir: Path) -> list[Path]:
    if not mods_dir.is_dir():
        return []
    return sorted(
        (p for p in mods_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jar", ".disabled"}),
        key=lambda p: p.name.lower(),
    )


@mod_app.command("search")
def search(
    query: list[str] = typer.Argument(..., help="Search terms"),
    page: int = typer.Option(1, "--page", "-p", min=1),
    limit: int = typer.Option(5, "--limit", "-n", min=1, max=20),
    install_index: int | None = typer.Option(None, "--install", help="Install the result with this index"),
    no_prompt: bool = typer.Option(False, "--no-prompt", help="Never ask to install a result"),
) -> None:
    """Search Modrinth and optionally install a result by its index."""
    text = " ".join(query).strip()
    try:
        data = modrinth.search(text, page, limit)
    except modrinth.ModrinthError as exc:
        log_error(f"Search failed: {exc}")
        raise typer.Exit(1)

    hits = data.get("hits") or []
    total = data.get("total_hits", 0)
    if not hits:
        log_warn(f"No mods found for '{text}' (page {page}).")
        return

    offset = (page - 1) * limit
    table = Table(title=f"Search results for '{text}' (page {page}, {total} total)")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Mod", style="green")
    table.add_column("Slug", style="magenta")
    table.add_column("Downloads", style="yellow", justify="right")
    table.add_column("Description", style="white", max_width=42)
    for index, mod in enumerate(hits, start=1):
        description = mod.get("description", "") or ""
        if len(description) > 42:
            description = description[:39] + "..."
        table.add_row(
            str(offset + index),
            mod.get("title", "?"),
            mod.get("slug", "?"),
            f"{mod.get('downloads', 0):,}",
            description,
        )
    console.print(table)
    log_info(f"Next page: mc-cli mod search {text} --page {page + 1}")

    chosen: int | None = install_index
    if chosen is None and not no_prompt and is_interactive():
        raw = typer.prompt("Install result # (empty to skip)", default="", show_default=False)
        if raw.strip().isdigit():
            chosen = int(raw.strip())
    if chosen is None:
        return

    position = chosen - offset
    if 1 <= position <= len(hits):
        install(hits[position - 1].get("slug", ""))
    else:
        log_error(f"Index {chosen} is not on this page (use --page to navigate).")
        raise typer.Exit(1)


@mod_app.command("install")
def install(
    slug: str = typer.Argument(..., help="Modrinth slug or project id"),
    optional: bool = typer.Option(False, "--optional", help="Also install optional dependencies"),
    max_depth: int = typer.Option(5, "--max-depth", help="Dependency recursion limit"),
) -> None:
    """Install a mod together with its required dependencies."""
    _, info, mods_dir = require_mods_dir()
    ensure_loader(info)
    try:
        project = modrinth.get_project(slug)
        log_info(f"Installing {project.get('title', slug)} for MC {info.mc_version} ({info.loader_type})...")
        downloaded = modrinth.install_project(
            slug,
            info.mc_version,
            info.loader_type,
            mods_dir,
            max_depth=max_depth,
            include_optional=optional,
        )
    except (modrinth.ModrinthError, DownloadError) as exc:
        log_error(f"Install failed: {exc}")
        raise typer.Exit(1)

    if not downloaded:
        log_warn("Nothing was downloaded (already installed or no compatible version).")
        return
    log_success(f"Installed {len(downloaded)} file(s) into {mods_dir}")
    for path in downloaded:
        console.print(f"  - {path.name}")


@mod_app.command("list")
def list_mods() -> None:
    """List installed mods with their id/version when the jar can be parsed."""
    _, info, mods_dir = require_mods_dir()
    mods = _mod_files(mods_dir)
    if not mods:
        log_warn("No mods installed in this instance.")
        return

    table = Table(title=f"Installed mods ({len(mods)}) — {info.folder_name}")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("File", style="green")
    table.add_column("Mod id", style="magenta")
    table.add_column("Version", style="blue")
    table.add_column("Size", style="yellow", justify="right")
    table.add_column("Status", style="white")
    for index, path in enumerate(mods, start=1):
        meta = read_mod_metadata(path)
        status = "[red]disabled[/red]" if path.suffix == ".disabled" else "[green]enabled[/green]"
        table.add_row(
            str(index),
            path.name,
            meta.mod_id if meta else "?",
            meta.version if meta else "?",
            format_size(path.stat().st_size),
            status,
        )
    console.print(table)


@mod_app.command("info")
def info(slug: str = typer.Argument(..., help="Modrinth slug or project id")) -> None:
    """Show project details, the latest compatible version and dependencies."""
    workspace, instance = require_workspace()
    mods_dir = workspace / "mods"
    try:
        project = modrinth.get_project(slug)
        versions = modrinth.get_versions(slug, instance.mc_version, instance.loader_type)
    except modrinth.ModrinthError as exc:
        log_error(f"Could not fetch project: {exc}")
        raise typer.Exit(1)

    table = Table(title=str(project.get("title", slug)), show_header=False)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Slug", str(project.get("slug", "?")))
    table.add_row("Type", str(project.get("project_type", "?")))
    table.add_row("Downloads", f"{project.get('downloads', 0):,}")
    table.add_row("Loaders", ", ".join(project.get("loaders") or []) or "-")
    table.add_row("Description", str(project.get("description", "")))
    console.print(table)

    version = modrinth.pick_version(versions)
    if not version:
        log_warn(f"No compatible version for MC {instance.mc_version} / {instance.loader_type}.")
        return
    file = modrinth.pick_file(version)
    log_info(
        f"Latest compatible: {version.get('version_number')} ({version.get('version_type')})"
        + (f" — {file['filename']}" if file else "")
    )

    dependencies = version.get("dependencies") or []
    if dependencies:
        dep_table = Table(title="Dependencies")
        dep_table.add_column("Project", style="green")
        dep_table.add_column("Type", style="magenta")
        for dep in dependencies:
            dep_id = dep.get("project_id") or dep.get("version_id") or "?"
            dep_name = dep_id
            try:
                dep_name = modrinth.get_project(str(dep_id)).get("title", dep_id)
            except modrinth.ModrinthError:
                pass
            dep_table.add_row(dep_name, dep.get("dependency_type", "?"))
        console.print(dep_table)

    installed = any(
        p.name.lower().startswith(str(project.get("slug", "")).lower()) for p in _mod_files(mods_dir)
    )
    log_info("Installed: yes" if installed else "Installed: no")


@mod_app.command("update")
def update(
    all_: bool = typer.Option(False, "--all", help="Download every available update"),
    check_only: bool = typer.Option(False, "--check", help="Only report available updates"),
    remove_old: bool = typer.Option(False, "--remove-old", help="Delete old jars instead of renaming to .old"),
) -> None:
    """Check jar sha1 hashes against Modrinth and download newer versions."""
    _, instance, mods_dir = require_mods_dir()
    jars = [p for p in _mod_files(mods_dir) if p.name.lower().endswith(".jar")]
    if not jars:
        log_warn("No enabled mod jars to check.")
        return

    log_info(f"Checking {len(jars)} jar(s) against Modrinth...")
    try:
        updates = modrinth.check_updates(jars, instance.mc_version, instance.loader_type)
    except modrinth.ModrinthError as exc:
        log_error(f"Update check failed: {exc}")
        raise typer.Exit(1)

    rows = []
    for jar in jars:
        try:
            digest = sha1_of(jar)
        except OSError:
            continue
        latest = updates.get(digest)
        if not latest:
            continue
        file = modrinth.pick_file(latest)
        if not file:
            continue
        new_hash = (file.get("hashes") or {}).get("sha1")
        if new_hash and new_hash == digest:
            continue
        rows.append((jar, latest, file))

    if not rows:
        log_success("All mods are up to date.")
        return

    table = Table(title=f"Updates available ({len(rows)})")
    table.add_column("Old file", style="yellow")
    table.add_column("New version", style="green")
    table.add_column("New file", style="cyan")
    for jar, latest, file in rows:
        table.add_row(jar.name, str(latest.get("version_number", "?")), file["filename"])
    console.print(table)

    if check_only or not all_:
        log_info("Run `mc-cli mod update --all` to install these updates.")
        return

    updated = 0
    for jar, latest, file in rows:
        try:
            path = modrinth.download_version(latest, mods_dir)
        except (modrinth.ModrinthError, DownloadError) as exc:
            log_warn(f"Could not update {jar.name}: {exc}")
            continue
        if path.name != jar.name:
            if remove_old:
                jar.unlink(missing_ok=True)
            else:
                jar.rename(jar.with_name(jar.name + ".old"))
        updated += 1
        log_success(f"Updated {jar.name} -> {path.name}")
    log_success(f"{updated} mod(s) updated.")


@mod_app.command("local")
def install_local(
    jar: Path = typer.Argument(..., exists=True, dir_okay=False, help="Path to a local .jar"),
    name: str = typer.Option("", "--name", help="Target file name (defaults to the source name)"),
) -> None:
    """Install a mod from a local jar file (after validating it)."""
    if jar.suffix.lower() != ".jar":
        log_error("Only .jar files can be installed.")
        raise typer.Exit(1)
    if not looks_like_mod_jar(jar):
        log_error("This jar does not contain mod metadata (not a Forge/Fabric/NeoForge mod?).")
        raise typer.Exit(1)
    _, _, mods_dir = require_mods_dir()
    target = mods_dir / (name or jar.name)
    if target.exists():
        log_error(f"Target already exists: {target.name}")
        raise typer.Exit(1)
    shutil.copy2(jar, target)
    meta = read_mod_metadata(target)
    log_success(f"Installed {target.name}" + (f" ({meta.name} {meta.version})" if meta else ""))


@mod_app.command("conflicts")
def conflicts() -> None:
    """Detect duplicate mod ids and known incompatible mods."""
    _, _, mods_dir = require_mods_dir()
    mods = _mod_files(mods_dir)
    if not mods:
        log_warn("No mods installed.")
        return

    by_id: dict[str, list[Path]] = {}
    unknown: list[Path] = []
    for path in mods:
        meta = read_mod_metadata(path)
        if not meta:
            unknown.append(path)
            continue
        by_id.setdefault(meta.mod_id.lower(), []).append(path)

    problems = 0
    for mod_id, paths in sorted(by_id.items()):
        if len(paths) > 1:
            problems += 1
            log_warn(f"Duplicate mod id '{mod_id}':")
            for path in paths:
                console.print(f"  - {path.name}")

    installed_ids = set(by_id)
    for pair, message in KNOWN_INCOMPATIBLE:
        if pair <= installed_ids:
            problems += 1
            log_warn(message + f" ({', '.join(sorted(pair))})")

    if unknown:
        log_info(f"{len(unknown)} jar(s) without readable metadata (not treated as conflicts).")
    if problems == 0:
        log_success(f"No conflicts detected in {len(mods)} jar(s).")


def _select_files(mods_dir: Path, patterns: list[str]) -> tuple[list[Path], list[str]]:
    files = _mod_files(mods_dir)
    selected: list[Path] = []
    unmatched: list[str] = []
    for pattern in patterns:
        needle = pattern.strip().strip('"').strip("'").lower()
        if not needle:
            continue
        if needle in {"all", "*"}:
            selected.extend(files)
            continue
        base = needle[:-9] if needle.endswith(".disabled") else needle
        matched = []
        for path in files:
            name = path.name.lower()
            base_name = name[:-9] if name.endswith(".disabled") else name
            if fnmatch.fnmatch(name, needle) or fnmatch.fnmatch(base_name, base) or needle in name:
                matched.append(path)
        if matched:
            selected.extend(matched)
        else:
            unmatched.append(pattern)
    return sorted(set(selected)), unmatched


@mod_app.command("enable")
def enable(names: list[str] = typer.Argument(..., help="Names, globs or 'all'")) -> None:
    """Enable one or more mods (strips the .disabled suffix)."""
    _, _, mods_dir = require_mods_dir()
    selected, unmatched = _select_files(mods_dir, names)
    for pattern in unmatched:
        log_warn(f"No file matched '{pattern}'.")
    changed = 0
    for path in selected:
        if path.name.endswith(".disabled"):
            target = path.with_name(path.name[:-9])
            if target.exists():
                log_warn(f"{target.name} already exists; skipped.")
                continue
            path.rename(target)
            changed += 1
    log_success(f"Enabled {changed} mod(s).")


@mod_app.command("disable")
def disable(names: list[str] = typer.Argument(..., help="Names, globs or 'all'")) -> None:
    """Disable one or more mods (adds the .disabled suffix)."""
    _, _, mods_dir = require_mods_dir()
    selected, unmatched = _select_files(mods_dir, names)
    for pattern in unmatched:
        log_warn(f"No file matched '{pattern}'.")
    changed = 0
    for path in selected:
        if not path.name.endswith(".disabled"):
            target = path.with_name(path.name + ".disabled")
            path.rename(target)
            changed += 1
    log_success(f"Disabled {changed} mod(s).")
