"""`mc-cli logs` and `mc-cli crash` - inspect an instance's run diagnostics."""
from __future__ import annotations

import time
from pathlib import Path

import typer

from mc_cli.commands._common import require_workspace
from mc_cli.utils.console import console, log_info, log_warn


def _latest_log(workspace: Path) -> Path | None:
    logs = workspace / "logs"
    latest = logs / "latest.log"
    if latest.is_file():
        return latest
    if logs.is_dir():
        candidates = sorted(logs.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else None
    return None


def logs(
    lines: int = typer.Option(40, "--lines", "-n", min=1, help="Lines to show"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Keep printing new lines"),
) -> None:
    """Show the tail of the instance's latest.log."""
    workspace, _ = require_workspace()
    path = _latest_log(workspace)
    if not path:
        log_warn("No log file found for this instance yet.")
        return

    log_info(f"Tail of {path} ({lines} lines)")
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[-lines:]:
        console.print(line, markup=False, highlight=False)

    if not follow:
        return
    log_info("Following... press Ctrl+C to stop.")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(0, 2)
            while True:
                line = fh.readline()
                if line:
                    console.print(line.rstrip("\n"), markup=False, highlight=False)
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        log_info("Stopped following.")


def crash(show_all: bool = typer.Option(False, "--all", help="Print the whole report")) -> None:
    """Analyse the newest crash report."""
    workspace, _ = require_workspace()
    reports = workspace / "crash-reports"
    if not reports.is_dir():
        log_warn("No crash-reports folder found.")
        return
    candidates = sorted(
        (p for p in reports.glob("crash-*.txt") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        log_warn("No crash reports found.")
        return

    report = candidates[0]
    log_info(f"Latest crash report: {report.name}")
    lines = report.read_text(encoding="utf-8", errors="replace").splitlines()

    if show_all:
        for line in lines:
            console.print(line, markup=False, highlight=False)
        return

    causes: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Caused by:") and stripped not in causes:
            causes.append(stripped)
        elif not causes and (
            "Exception" in stripped or stripped.startswith("java.lang.Error")
        ) and len(stripped) < 300:
            causes.append(stripped)

    description = next((l for l in lines if l.startswith("Description:")), "")
    console.print("\n".join(lines[:12]), markup=False, highlight=False)
    if description and description not in "\n".join(lines[:12]):
        console.print(description, markup=False)
    if causes:
        console.print("\n[bold red]Suspected cause(s):[/bold red]")
        for cause in causes[:10]:
            console.print(f"  [red]{cause}[/red]", markup=True, highlight=False)
    else:
        log_warn("No 'Caused by' line found - see the full report with `mc-cli crash --all`.")
    log_info(f"Full report: {report}")
