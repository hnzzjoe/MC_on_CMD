"""Optional sharing of mods / saves / resourcepacks between instances.

When a kind is enabled, commands read/write ``<minecraft>/shared/<kind>``
instead of the per-instance folder, so every instance under that root sees the
same content.
"""
from __future__ import annotations

from pathlib import Path

from mc_cli.config.manager import load_config
from mc_cli.core.instance import mc_root_of

KINDS = ("mods", "saves", "resourcepacks")


def shared_enabled(kind: str) -> bool:
    return bool((load_config().get("shared") or {}).get(kind))


def shared_root(workspace: Path, kind: str) -> Path:
    path = mc_root_of(workspace) / "shared" / kind
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_dir(workspace: Path, kind: str) -> Path:
    """Where commands should read/write this kind of content."""
    if shared_enabled(kind):
        return shared_root(workspace, kind)
    path = Path(workspace) / kind
    path.mkdir(exist_ok=True)
    return path
