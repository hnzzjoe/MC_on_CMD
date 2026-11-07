
# MC_on_cmd (mc-cli)

A powerful Windows command-line tool for managing Minecraft instances, mods, shaders, resource packs, and saves. It also features a gorgeous interactive terminal (`mc-cli start`) with a retro hacker vibe.

## 📦 Installation

### Option 1: For Players (Standalone `.exe`)

1. Go to the [Releases](https://github.com/hnzzjoe/MC_on_CMD/releases) page and download the latest `mc-cli.exe`.
2. Create a folder (e.g., `D:\Tools\MC_CLI`) and put the `.exe` inside.
3. **Add to Environment Variables (Highly Recommended)**:
   - Press `Win` and search for "Environment Variables".
   - Edit the `Path` variable under "User variables".
   - Add the folder path (e.g., `D:\Tools\MC_CLI`) and save.
4. Restart your terminal and type `mc-cli start` anywhere!

> **Note:** If you don't add it to the environment variables, you must run it using `.\mc-cli.exe` in the directory where the file is located.

### Option 2: For Developers (From Source)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

## 🚀 Quick Start

```powershell
mc-cli start                                  # Enter the interactive terminal (Recommended)
mc-cli config root add "D:\games\.minecraft"  # Or register and activate .minecraft via CLI
mc-cli instance use 1.20.1-fabric             # Switch to a specific instance
```

*(Inside the interactive terminal, type `help` to see all available shortcuts!)*

## 🛠️ Command Overview

### Instances

| Command | Description |
| --- | --- |
| `mc-cli instance list` | List instances (folder / MC version / loader) and report corrupted ones |
| `mc-cli instance use <name>` | Switch the current instance |
| `mc-cli instance versions` | List available Mojang versions |
| `mc-cli instance create <name> -v <ver> [--loader vanilla\|fabric]` | Create an instance from the official manifest |
| `mc-cli instance clone <src> <dst> [--with-data]` | Clone an instance (libraries/assets are shared in the root directory) |
| `mc-cli instance rename <old> <new>` | Rename the folder and json |
| `mc-cli instance delete <name> [-y]` | Delete an instance along with its mods/saves/config |

### Mods (Powered by Modrinth)

| Command | Description |
| --- | --- |
| `mc-cli mod search <query> [--page N]` | Search; an interactive prompt lets you install directly by index |
| `mc-cli mod install <slug>` | Install a mod and recursively install required dependencies |
| `mc-cli mod list` | List mods, showing mod id / version / enabled status |
| `mc-cli mod info <slug>` | Show project details, available versions, and dependencies |
| `mc-cli mod update [--check\|--all] [--remove-old]` | Batch check by sha1 / one-click update |
| `mc-cli mod local <jar>` | Install a local jar after verification |
| `mc-cli mod conflicts` | Check duplicate mod ids and known incompatible combinations |
| `mc-cli mod enable\|disable <name...>` | Supports wildcards and `all` |

### Shaders / Resource Packs

```powershell
mc-cli shader install                 # Auto-install Iris+Sodium / Oculus+Embeddium
mc-cli shader import <pack.zip>       # Verify and import a shader pack (auto-enabled by default)
mc-cli shader list | use <name> | delete <name> [-y]

mc-cli resourcepack list | import <zip> | enable <name> | disable <name> | delete <name>
mc-cli resourcepack install <slug>    # Install from Modrinth
```

### Saves

```powershell
mc-cli save list | list-backups
mc-cli save backup <name|all>
mc-cli save restore <backup.zip> [-y]  # Extract to temp for verification first, then merge; old saves are moved to backups/overwritten
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

## ⚙️ Configuration

`config.json` is located at `%APPDATA%\MCCliTool` (can be overridden with `MCCLI_CONFIG_DIR`):

| Key | Default | Description |
| --- | --- | --- |
| `java_path` | Auto-detected | Specify `java.exe` (used for doctor verification) |
| `backup_keep` | 10 | Number of backups to keep during automatic cleanup |
| `animations` | true | Decorative delays/animations (`--no-anim` temporarily disables) |
| `shared.mods` / `shared.saves` / `shared.resourcepacks` | false | Shared directories across multiple instances (creates directory junctions) |

## 📝 Notes

- `instance create` supports Vanilla and Fabric; for Forge/NeoForge, please create the instance first using the official installer or PCL2.
- Run tests: `python -m unittest discover -s tests -t .`
- **License**: This project is licensed under the MPL-2.0 License.
