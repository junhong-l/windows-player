# 🎬 视频播放器

基于 Python + mpv + PyQt6 开发的现代化视频播放器，拥有 B站风格的深色界面。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 🚀 快速开始

### 方式一：直接安装（推荐）

从 [Releases](../../releases) 下载最新的 `视频播放器_安装包_vX.X.X.exe`，双击安装即可。安装包约 59 MB，包含所有依赖，无需 Python 环境。

### 方式二：从源码运行

1. **安装依赖**：
   ```bash
   python setup.py
   ```

2. **下载 libmpv-2.dll**：
   - 从 https://sourceforge.net/projects/mpv-player-windows/files/libmpv/ 下载
   - 将 `libmpv-2.dll` 放到项目根目录

3. **运行程序**：
   ```bash
   python main.py
   ```

### 方式三：自行打包

```bash
# 需要先安装 Inno Setup 6（https://jrsoftware.org/isdl.php）
python build.py --installer
# 输出：dist\视频播放器_安装包_vX.X.X.exe
```

> 修改版本号只需编辑 `version.py` 中的 `__version__`，打包时会自动同步。

---

## ✨ 功能特点

### 播放功能
- **多格式支持**：mp4, mkv, avi, mov, wmv, flv, webm, m4v, mpeg, mpg, 3gp 等
- **字幕支持**：内嵌字幕、外挂字幕（srt/ass/ssa/sub/vtt）、字幕延迟调整
- **倍速播放**：0.25x - 3.0x 倍速，满足不同观看需求
- **自定义快进**：1-300 秒可调快进步长
- **跳过片头片尾**：自动跳过片头/片尾（按文件夹保存设置）
- **音轨切换**：支持多音轨视频的音轨选择
- **进度记忆**：自动保存和恢复播放进度

### 文件夹管理
- **播放列表**：打开文件夹自动生成播放列表
- **连续播放**：自动播放下一集
- **进度显示**：列表中显示每个视频的观看进度
- **拖放支持**：支持拖放文件或文件夹到窗口

### 界面设计
- **B站风格**：现代化深色界面，半透明悬浮控制栏
- **自动隐藏**：控制栏在鼠标移开后自动隐藏
- **深色标题栏**：Windows 10/11 原生深色标题栏
- **Toast 提示**：操作反馈提示

### 系统集成
- **文件关联**：可设为默认视频播放器
- **文件图标**：关联的视频文件显示播放器图标
- **图标修复**：内置修复文件关联图标功能

## 🖼️ 界面预览

```
┌─────────────────────────────────────────────────────────────┐
│  视频播放器                                          ─ □ ×  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                                                             │
│                      视 频 画 面                             │
│                                                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ ═══════════════════════●════════════════════════════════    │
│ ⏮ ▶ ⏭  ↻ ◀◀ ▶▶  00:12:34 / 00:45:00    片头 片尾 列表 倍速 │
└─────────────────────────────────────────────────────────────┘
```

## 🛠️ 开发环境搭建

### 1. 安装 mpv

从 [SourceForge](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/) 下载 `libmpv-2.dll`，放到项目根目录。

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 运行播放器

```bash
python main.py
```

## ⌨️ 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Space` | 播放/暂停 |
| `←` | 快退（默认10秒） |
| `→` | 快进（默认10秒） |
| `↑` | 增加音量 5% |
| `↓` | 减少音量 5% |
| `M` | 静音/取消静音 |
| `F` | 全屏/退出全屏 |
| `Esc` | 退出全屏 |
| `Ctrl+O` | 打开文件 |

## 📁 项目结构

```
windows-player/
├── main.py              # 程序入口
├── main_window.py       # 主窗口 UI（欢迎页、播放页、控制栏、播放列表）
├── player_core.py       # mpv 播放器核心封装（播放、字幕、音轨控制）
├── folder_settings.py   # 设置管理（全局设置、文件夹设置）
├── default_player.py    # 默认播放器和文件关联管理
├── version.py           # 版本号（唯一维护处）
├── build.py             # 打包脚本
├── build.spec           # PyInstaller 打包配置
├── installer.iss        # Inno Setup 安装包脚本
├── setup.py             # 环境配置脚本
├── create_icon.py       # 图标生成脚本
├── icon.ico             # 应用图标
├── requirements.txt     # Python 依赖
└── README.md            # 说明文档
```

## 🔧 配置说明

### 全局设置
- **播放速度**：0.25x - 3.0x，默认 1.0x
- **快进步长**：1-300 秒，默认 10 秒

### 文件夹设置
- **跳过片头**：0-600 秒，自动填入当前播放位置
- **跳过片尾**：0-600 秒，自动填入距结尾时间
- **播放进度**：自动保存每个视频的观看进度

### 设置文件位置
所有设置统一保存在 `settings/` 目录中：
- `settings/global_settings.json`：全局设置
- `settings/folder_*.json`：各文件夹的播放设置

## 🎮 使用技巧

1. **快速设置片头**：播放到片头结束位置，点击"片头"按钮，当前位置会自动填入
2. **快速设置片尾**：播放到片尾开始位置，点击"片尾"按钮，距结尾时间会自动填入
3. **连续追剧**：打开文件夹后，播完一集会自动播放下一集
4. **继续观看**：打开之前看过的视频，会自动跳转到上次观看位置

## ⚠️ 常见问题

### mpv 找不到 / DLL 加载失败
确保 `libmpv-2.dll` 放在项目目录下，或者 mpv 已添加到系统 PATH。

### 视频无法播放
1. 确认文件格式是否支持
2. 检查 mpv 是否正确安装
3. 尝试更新 mpv 到最新版本

### 任务栏图标不显示
重启应用后图标会正确显示。

### 视频文件图标不显示
1. 打开设置，点击「修复文件图标」按钮
2. 注销并重新登录 Windows，或重启电脑
3. 注意：只有打包后的 exe 才能正确显示文件图标

## 📦 打包为安装包

```bash
# 需要先安装 Inno Setup 6（https://jrsoftware.org/isdl.php）
python build.py --installer
# 输出：dist\视频播放器_安装包_vX.X.X.exe（约 59 MB）
```

打包完成后 `dist\` 目录只保留安装包，中间产物自动清理。

**修改版本号**：只需编辑 `version.py` 中的 `__version__`，打包时自动同步到安装包文件名和安装界面。

## 📋 依赖

- Python 3.10+
- PyQt6
- python-mpv
- qtawesome
- darkdetect
- Pillow（仅用于生成图标）
- PyInstaller + Inno Setup 6（仅用于打包）

## 📝 许可证

MIT License

## 🙏 致谢

- [mpv](https://mpv.io/) - 强大的开源视频播放器
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Python GUI 框架
- [qtawesome](https://github.com/spyder-ide/qtawesome) - FontAwesome 图标库
