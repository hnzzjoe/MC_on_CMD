# MC_on_cmd (mc-cli)

一个用于管理 Minecraft 实例、模组、光影、资源包和存档的 Windows 命令行工具，
同时保留 `mc-cli start` 交互式终端。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .
```

## 快速开始

```powershell
mc-cli config root add "D:\games\.minecraft"   # 注册并激活 .minecraft
mc-cli instance list                          # 查看实例（* 为当前实例）
mc-cli instance use 1.20.1-fabric             # 切换实例
mc-cli start                                  # 进入交互式终端
```

## 命令一览

### 实例

| 命令 | 说明 |
| --- | --- |
| `mc-cli instance list` | 列出实例（文件夹 / MC 版本 / 加载器），并报告损坏实例 |
| `mc-cli instance use <name>` | 切换当前实例 |
| `mc-cli instance versions` | 列出 Mojang 可用版本 |
| `mc-cli instance create <name> -v <ver> [--loader vanilla\|fabric]` | 从官方清单创建实例 |
| `mc-cli instance clone <src> <dst> [--with-data]` | 克隆实例（库和资源在根目录共享） |
| `mc-cli instance rename <old> <new>` | 重命名文件夹与 json |
| `mc-cli instance delete <name> [-y]` | 删除实例及其 mods/saves/config |

### 模组（Modrinth）

| 命令 | 说明 |
| --- | --- |
| `mc-cli mod search <query> [--page N]` | 搜索；交互式提示可直接输入序号安装 |
| `mc-cli mod install <slug>` | 安装模组并递归安装必需前置（自动跳过已装） |
| `mc-cli mod list` | 列出模组，显示 mod id / 版本 / 启用状态 |
| `mc-cli mod info <slug>` | 项目详情、可用版本、依赖 |
| `mc-cli mod update [--check\|--all] [--remove-old]` | 按 sha1 批量检查 / 一键更新 |
| `mc-cli mod local <jar>` | 校验后安装本地 jar |
| `mc-cli mod conflicts` | 重复 mod id、已知不兼容组合 |
| `mc-cli mod enable\|disable <name...>` | 支持通配符与 `all` |

### 光影 / 资源包

```powershell
mc-cli shader install                 # Iris+Sodium / Oculus+Embeddium
mc-cli shader import <pack.zip>       # 校验并导入光影包（默认启用）
mc-cli shader list | use <name> | delete <name> [-y]

mc-cli resourcepack list | import <zip> | enable <name> | disable <name> | delete <name>
mc-cli resourcepack install <slug>    # 从 Modrinth 安装
```

### 存档

```powershell
mc-cli save list | list-backups
mc-cli save backup <name|all>
mc-cli save restore <backup.zip> [-y]  # 先解压到临时目录校验，再合并；旧存档移入 backups/overwritten
mc-cli save import <world.zip> [--name N] [--replace]
mc-cli save export <world> [--to <dir|file.zip>]
mc-cli save clean [--keep N] [-y]      # 自动清理旧备份
```

### 诊断 / 配置

```powershell
mc-cli logs [-n 40] [-f]
mc-cli crash [--all]
mc-cli doctor
mc-cli config show | reset | set <key> <value>
mc-cli config root list | add <path> [--use] | use <index|path> | remove <index|path>
```

## 配置项

`config.json` 位于 `%APPDATA%\MCCliTool`（可用 `MCCLI_CONFIG_DIR` 覆盖）：

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `java_path` | 自动探测 | 指定 `java.exe`（doctor 校验用） |
| `backup_keep` | 10 | 自动清理时保留的备份数 |
| `animations` | true | 装饰性延迟/动画（`--no-anim` 可临时关闭） |
| `shared.mods` / `shared.saves` / `shared.resourcepacks` | false | 多实例共享目录（创建目录联接） |

## 说明

- `instance create` 支持 Vanilla 与 Fabric；Forge/NeoForge 请先用官方安装器建好实例。
- 常见测试：`python -m unittest discover -s tests -t .`
