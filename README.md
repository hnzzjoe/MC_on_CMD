# MC_on_cmd (mc-cli)

A Windows command-line tool for managing Minecraft instances, mods, shaders, resource packs, and saves, while also retaining the `mc-cli start` interactive terminal.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

> **Note:** You need to add it to the environment variables, or use it in the same directory. Open it in a terminal.

## Quick Start

```powershell
mc-cli config root add "D:\games\.minecraft"   # Register and activate .minecraft
mc-cli instance list                          # View instances (* marks the current instance)
mc-cli instance use 1.20.1-fabric             # Switch instance
mc-cli start                                  # Enter the interactive terminal
```

## Command Overview

### Instances

| Command | Description |
| --- | --- |
| `mc-cli instance list` | List instances (folder / MC version / loader) and report corrupted instances |
| `mc-cli instance use <name>` | Switch the current instance |
| `mc-cli instance versions` | List available Mojang versions |
| `mc-cli instance create <name> -v <ver> [--loader vanilla\|fabric]` | Create an instance from the official manifest |
| `mc-cli instance clone <src> <dst> [--with-data]` | Clone an instance (libraries and assets are shared in the root directory) |
| `mc-cli instance rename <old> <new>` | Rename the folder and json |
| `mc-cli instance delete <name> [-y]` | Delete an instance along with its mods/saves/config |

### Mods (Modrinth)

| Command | Description |
| --- | --- |
| `mc-cli mod search <query> [--page N]` | Search; an interactive prompt lets you enter a number to install directly |
| `mc-cli mod install <slug>` | Install a mod and recursively install required dependencies (already-installed ones are skipped automatically) |
| `mc-cli mod list` | List mods, showing mod id / version / enabled status |
| `mc-cli mod info <slug>` | Project details, available versions, dependencies |
| `mc-cli mod update [--check\|--all] [--remove-old]` | Batch check by sha1 / one-click update |
| `mc-cli mod local <jar>` | Install a local jar after verification |
| `mc-cli mod conflicts` | Duplicate mod ids, known incompatible combinations |
| `mc-cli mod enable\|disable <name...>` | Supports wildcards and `all` |

### Shaders / Resource Packs

```powershell
mc-cli shader install                 # Iris+Sodium / Oculus+Embeddium
mc-cli shader import <pack.zip>       # Verify and import a shader pack (enabled by default)
mc-cli shader list | use <name> | delete <name> [-y]

mc-cli resourcepack list | import <zip> | enable <name> | disable <name> | delete <name>
mc-cli resourcepack install <slug>    # Install from Modrinth
```

### Saves

```powershell
mc-cli save list | list-backups
mc-cli save backup <name|all>
mc-cli save restore <backup.zip> [-y]  # Extract to a temp directory for verification first, then merge; old saves are moved to backups/overwritten
mc-cli save import <world.zip> [--name N] [--replace]
mc-cli save export <world> [--to <dir|file.zip>]
mc-cli save clean [--keep N] [-y]      # Automatically clean up old backups
```

### Diagnostics / Configuration

```powershell
mc-cli logs [-n 40] [-f]
mc-cli crash [--all]
mc-cli doctor
mc-cli config show | reset | set <key> <value>
mc-cli config root list | add <path> [--use] | use <index|path> | remove <index|path>
```

## Configuration

`config.json` is located at `%APPDATA%\MCCliTool` (can be overridden with `MCCLI_CONFIG_DIR`):

| Key | Default | Description |
| --- | --- | --- |
| `java_path` | Auto-detected | Specify `java.exe` (used for doctor verification) |
| `backup_keep` | 10 | Number of backups to keep during automatic cleanup |
| `animations` | true | Decorative delays/animations (`--no-anim` temporarily disables) |
| `shared.mods` / `shared.saves` / `shared.resourcepacks` | false | Shared directories across multiple instances (creates directory junctions) |

## Notes

- `instance create` supports Vanilla and Fabric; for Forge/NeoForge, create the instance first using the official installer.
- Common test: `python -m unittest discover -s tests -t .`