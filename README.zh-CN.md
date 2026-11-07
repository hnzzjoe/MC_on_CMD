
# MC_on_cmd (mc-cli)

[[English](README.md) | 简体中文]

一款强大的 Windows 命令行 Minecraft 管理工具。支持实例管理、模组下载、光影一键部署、资源包管理与存档安全备份。同时内置极具极客风的交互式终端（`mc-cli start`）。

## 📦 安装说明

### 方式一：直接下载 (适用于普通玩家)

1. 前往 [Releases](https://github.com/hnzzjoe/MC_on_CMD/releases) 页面下载最新的 `mc-cli.exe`。
2. 新建一个文件夹（例如 `D:\Tools\MC_CLI`），将下载的 `.exe` 放入其中。
3. **添加到环境变量（强烈推荐）**：
   - 按 `Win` 键搜索“环境变量”。
   - 在“用户变量”中双击 `Path`，点击“新建”，填入刚才的文件夹路径（如 `D:\Tools\MC_CLI`），一路确定保存。
4. 重启终端（PowerShell/CMD），在任意目录下输入 `mc-cli start` 即可启动！

> **注意：** 如果没有添加到环境变量，需要在 exe 所在目录下使用 `.\mc-cli.exe` 运行。

### 方式二：源码安装 (适用于开发者)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

## 🚀 快速开始

```powershell
mc-cli start                                  # 进入交互式终端（推荐，体验极佳）
mc-cli config root add "D:\games\.minecraft"  # 或者使用传统 CLI 指令注册并激活 .minecraft
mc-cli instance use 1.20.1-fabric             # 切换到指定实例
```

*(在交互式终端内，输入 `help` 即可查看所有快捷指令！)*

## 🛠️ 指令大全

### 实例管理 (Instances)

| 指令 | 描述 |
| --- | --- |
| `mc-cli instance list` | 列出所有实例（文件夹 / MC版本 / 加载器），并报告损坏的实例 |
| `mc-cli instance use <name>` | 切换当前工作实例 |
| `mc-cli instance versions` | 获取 Mojang 官方可用版本列表 |
| `mc-cli instance create <name> -v <ver> [--loader vanilla\|fabric]` | 从官方清单创建实例 |
| `mc-cli instance clone <src> <dst> [--with-data]` | 克隆实例（依赖库与资源文件通过根目录共享） |
| `mc-cli instance rename <old> <new>` | 重命名实例文件夹及 json 文件 |
| `mc-cli instance delete <name> [-y]` | 删除实例及其包含的模组/存档/配置 |

### 模组管理 (Mods - 数据源 Modrinth)

| 指令 | 描述 |
| --- | --- |
| `mc-cli mod search <query> [--page N]` | 搜索模组；交互式输入序号即可直接安装 |
| `mc-cli mod install <slug>` | 安装模组并递归安装必需的前置依赖 |
| `mc-cli mod list` | 列出已安装模组，显示 ID / 版本 / 启用状态 |
| `mc-cli mod info <slug>` | 查看项目详情、可用版本及依赖树 |
| `mc-cli mod update [--check\|--all] [--remove-old]` | 通过 sha1 批量检查 / 一键更新模组 |
| `mc-cli mod local <jar>` | 验证并安装本地 jar 包 |
| `mc-cli mod conflicts` | 检查重复的模组 ID 及已知的不兼容组合 |
| `mc-cli mod enable\|disable <name...>` | 支持通配符，或使用 `all` 批量启用/禁用 |

### 光影与资源包 (Shaders / Resource Packs)

```powershell
mc-cli shader install                 # 自动下载并安装前置 (Iris+Sodium / Oculus+Embeddium)
mc-cli shader import <pack.zip>       # 验证并导入光影包（默认自动启用）
mc-cli shader list | use <name> | delete <name> [-y]

mc-cli resourcepack list | import <zip> | enable <name> | disable <name> | delete <name>
mc-cli resourcepack install <slug>    # 从 Modrinth 直接搜索并下载资源包
```

### 存档管理 (Saves)

```powershell
mc-cli save list | list-backups
mc-cli save backup <name|all>
mc-cli save restore <backup.zip> [-y]  # 先解压到临时目录校验，再合并覆盖；旧存档会移入 backups/overwritten
mc-cli save import <world.zip> [--name N] [--replace]
mc-cli save export <world> [--to <dir|file.zip>]
mc-cli save clean [--keep N] [-y]      # 自动清理旧的备份文件
```

### 诊断与配置 (Diagnostics / Configuration)

```powershell
mc-cli logs [-n 40] [-f]
mc-cli crash [--all]
mc-cli doctor
mc-cli config show | reset | set <key> <value>
mc-cli config root list | add <path> [--use] | use <index|path> | remove <index|path>
```

## ⚙️ 配置文件

`config.json` 默认位于 `%APPDATA%\MCCliTool` （可通过环境变量 `MCCLI_CONFIG_DIR` 覆盖位置）：

| 键名 | 默认值 | 描述 |
| --- | --- | --- |
| `java_path` | 自动探测 | 指定 `java.exe` 路径（用于 doctor 诊断） |
| `backup_keep` | 10 | 自动清理时保留的备份数量 |
| `animations` | true | 是否启用终端装饰延迟/动画（`--no-anim` 临时禁用） |
| `shared.mods` / `shared.saves` / `shared.resourcepacks` | false | 在多个实例间共享目录（使用目录联接实现） |

## 📝 备注

- `instance create` 目前支持 Vanilla 和 Fabric；对于 Forge/NeoForge，请先使用官方安装器或 PCL2 创建实例。
- 运行测试：`python -m unittest discover -s tests -t .`
- **开源协议**：本项目基于 MPL-2.0 协议开源。
```
