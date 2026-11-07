"""Console helpers: logging, logo, progress bars and animation control.

The little random delays exist purely for flavour.  They are disabled when
output is not a real terminal or when the user turns animations off, so that
scripted / piped usage is never slowed down by them.
"""
from __future__ import annotations

import random
import sys
import time

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

console = Console()
_animations = True


def set_animations(enabled: bool) -> None:
    """Enable/disable the decorative delays and spinner effects."""
    global _animations
    _animations = bool(enabled)


def animations_enabled() -> bool:
    """Animations only make sense on an interactive terminal."""
    return _animations and console.is_terminal


def _is_interactive() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def is_interactive() -> bool:
    return _is_interactive()


def _random_delay() -> None:
    if not animations_enabled():
        return
    time.sleep(random.uniform(0.01, 0.05))


def print_logo() -> None:
    """Print the startup logo (ASCII art, gracefully degraded without pyfiglet)."""
    try:
        import pyfiglet

        ascii_art = pyfiglet.figlet_format("M  C   o n   C  M  D", font="slant")
    except Exception:  # pragma: no cover - optional dependency
        ascii_art = "MC on CMD"
    console.print(f"[bold cyan]{ascii_art}[/bold cyan]", justify="center")
    from rich.rule import Rule

    console.print(Rule("[dim]Minecraft CLI Manager[/dim]", style="bright_blue"))
    console.print()


# ================= 日志系统 =================

def log_info(msg: str) -> None:
    console.print(f"[bold blue][INFO][/bold blue] {msg}")
    _random_delay()


def log_warn(msg: str) -> None:
    console.print(f"[bold yellow][WARN][/bold yellow] {msg}")
    _random_delay()


def log_error(msg: str) -> None:
    console.print(f"[bold red][ERROR][/bold red] {msg}")
    _random_delay()


def log_fatal(msg: str) -> None:
    console.print(f"[bold white on red][FATAL][/bold white on red] {msg}")
    _random_delay()


def log_success(msg: str) -> None:
    console.print(f"[bold green][SUCCESS][/bold green] {msg}")
    _random_delay()


def get_download_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40, style="cyan", complete_style="green"),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        transient=True,  # 下载完成后自动消失，不污染屏幕
    )
