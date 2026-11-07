"""mc-cli entry point: command groups plus the interactive shell."""
from __future__ import annotations

import shlex
import time
from pathlib import Path

import typer
from rich.prompt import Prompt

from mc_cli.commands import diagnostics as diag
from mc_cli.commands.config import config_app
from mc_cli.commands.doctor import doctor
from mc_cli.commands.instance import instance_app
from mc_cli.commands.mods import mod_app
from mc_cli.commands.resourcepacks import resourcepack_app
from mc_cli.commands.saves import save_app
from mc_cli.commands.shaders import shader_app
from mc_cli.config.manager import (
    auto_detect_minecraft,
    clear_workspace,
    get_bool,
    get_mc_dir,
    get_workspace,
    save_mc_dir,
    save_workspace,
)
from mc_cli.core.scanner import scan_instances
from mc_cli.utils.console import (
    console,
    log_error,
    log_fatal,
    log_info,
    log_success,
    log_warn,
    print_logo,
    set_animations,
)

app = typer.Typer(
    help="Minecraft CLI Manager - manage instances, mods, shaders, worlds and more.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)

app.add_typer(instance_app, name="instance", help="Manage instances (versions).")
app.add_typer(mod_app, name="mod", help="Search / install / update mods.")
app.add_typer(shader_app, name="shader", help="Install shader loaders and shaderpacks.")
app.add_typer(resourcepack_app, name="resourcepack", help="Manage resource packs.")
app.add_typer(save_app, name="save", help="Worlds and backups.")
app.add_typer(config_app, name="config", help="Settings and .minecraft roots.")
app.command("logs")(diag.logs)
app.command("crash")(diag.crash)
app.command("doctor")(doctor)


@app.callback()
def _global_options(
    no_anim: bool = typer.Option(False, "--no-anim", help="Disable decorative delays/animations"),
) -> None:
    set_animations(False if no_anim else get_bool("animations", True))


@app.command("info")
def info() -> None:
    """Show tool information."""
    console.print("MC_on_cmd v0.1.0 — Minecraft CLI Manager")


# ================= 交互式终端 =================

SHELL_HELP = """
[bold cyan]Commands[/bold cyan] (same as the CLI, without the `mc-cli` prefix):
  [green]instance list|use|create|clone|delete|rename|versions[/green]
  [green]mod search|install|list|info|update|local|conflicts|enable|disable[/green]
  [green]shader install|import|list|use|delete[/green]
  [green]resourcepack list|import|enable|disable|delete|install[/green]
  [green]save list|list-backups|backup|restore|import|export|clean[/green]
  [green]logs|crash|doctor[/green]
  [green]config show|set|reset|root ...[/green]
[bold cyan]Shortcuts:[/bold cyan]
  [green]set ver[/green]  - pick an instance     [green]set mc[/green] - change .minecraft
  [green]help <command>[/green] - command help    [green]exit[/green]    - quit
"""


def clean_arg(arg: str) -> str:
    """Strip whitespace and any surrounding quotes the user pasted."""
    return arg.strip().strip('"').strip("'").strip()


def _ensure_root() -> Path | None:
    """Return an active .minecraft root, prompting once if needed."""
    mc_dir = get_mc_dir()
    if mc_dir:
        return mc_dir

    detected = auto_detect_minecraft()
    if detected:
        save_mc_dir(detected)
        log_success(f"Detected .minecraft: {detected}")
        return detected

    default_path = str(Path.home() / "AppData/Roaming/.minecraft")
    answer = Prompt.ask("[yellow]Enter .minecraft path[/yellow]", default=default_path)
    candidate = Path(clean_arg(answer)).expanduser().resolve()
    if not (candidate / "versions").is_dir():
        log_fatal(f"{candidate} does not contain a 'versions' folder.")
        return None
    save_mc_dir(candidate)
    log_success(f"Configuration saved: {candidate}")
    return candidate


def _run_cli(argv: list[str]) -> None:
    """Run a CLI command from inside the interactive shell."""
    try:
        app(argv, standalone_mode=False, prog_name="mc-cli")
    except SystemExit:
        pass
    except KeyboardInterrupt:
        console.print()
    except Exception as exc:  # click usage errors and friends
        message = exc.format_message() if hasattr(exc, "format_message") else str(exc)
        if message:
            log_error(message)


def _shim(argv: list[str]) -> list[str]:
    """Accept a few legacy positional forms from the old shell."""
    if (
        len(argv) >= 2
        and argv[0] == "mod"
        and argv[1] == "search"
        and argv[-1].isdigit()
        and "--page" not in argv
        and "-p" not in argv
    ):
        return argv[:-1] + ["--page", argv[-1]]
    return argv


def _select_instance() -> None:
    mc_dir = get_mc_dir()
    if not mc_dir:
        log_error("No .minecraft configured yet.")
        return
    result = scan_instances(mc_dir)
    if not result.instances:
        log_error("No valid instances found.")
        return

    from rich.table import Table

    table = Table(title="Available instances")
    table.add_column("#", style="cyan")
    table.add_column("Folder", style="green")
    table.add_column("MC", style="magenta")
    table.add_column("Loader", style="yellow")
    for index, inst in enumerate(result.instances, start=1):
        table.add_row(str(index), inst.folder_name, inst.mc_version, inst.loader_type)
    console.print(table)

    choice = Prompt.ask(
        "[cyan]Select instance[/cyan]",
        choices=[str(i) for i in range(1, len(result.instances) + 1)],
    )
    selected = result.instances[int(choice) - 1]
    save_workspace(selected.path)
    log_success(f"Workspace set to: {selected.folder_name}")


@app.command("start")
def start() -> None:
    """Start the interactive terminal."""
    with console.status("[bold cyan]Waking up...", spinner="dots12") as status:
        time.sleep(0.3)
        status.update("[bold cyan]Loading modules...")
        time.sleep(0.2)
        status.update("[bold cyan]Checking environment...")
        time.sleep(0.2)

    print_logo()
    try:
        mc_dir = _ensure_root()
    except (EOFError, KeyboardInterrupt):
        console.print()
        raise typer.Exit(1)
    if not mc_dir:
        raise typer.Exit(1)

    workspace = get_workspace()
    log_info("Type 'help' for commands, 'exit' to quit.")

    while True:
        prompt = "[bold green]MC[/bold green]"
        if workspace:
            prompt += f"[bold cyan]({workspace.name})[/bold cyan]"
        prompt += "> "
        try:
            raw = clean_arg(console.input(prompt))
        except (EOFError, KeyboardInterrupt):
            console.print()
            log_info("Exiting...")
            break
        if not raw:
            continue
        if raw in {"exit", "quit"}:
            log_info("Exiting...")
            break
        if raw in {"help", "?"}:
            console.print(SHELL_HELP)
            continue

        if raw in {"set ver", "set version"}:
            try:
                _select_instance()
            except (EOFError, KeyboardInterrupt):
                console.print()
                log_info("Exiting...")
                break
            workspace = get_workspace()
            continue
        if raw == "set mc":
            try:
                answer = Prompt.ask("[yellow]Enter new .minecraft path[/yellow]")
            except (EOFError, KeyboardInterrupt):
                console.print()
                log_info("Exiting...")
                break
            candidate = Path(clean_arg(answer)).expanduser().resolve()
            if (candidate / "versions").is_dir():
                save_mc_dir(candidate)
                clear_workspace()
                workspace = None
                log_success(f"Changed .minecraft directory to: {candidate}")
            else:
                log_error("Invalid directory. It must contain a 'versions' folder.")
            continue
        if raw.startswith("help "):
            try:
                _run_cli(shlex.split(raw)[1:] + ["--help"])
            except ValueError as exc:
                log_error(f"Could not parse the command: {exc}")
            continue

        try:
            argv = shlex.split(raw)
        except ValueError as exc:
            log_error(f"Could not parse the command: {exc}")
            continue
        if not argv:
            continue
        _run_cli(_shim(argv))
        workspace = get_workspace()

    raise typer.Exit()


if __name__ == "__main__":  # pragma: no cover
    app()
