# 🎬 视频播放器

基于 Python + mpv + PyQt6 开发的现代化视频播放器，拥有 B站风格的深色界面。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## � 快速开始

### 方式一：运行开发版本

1. **安装依赖**：
   ```bash
   python setup.py
   ```
   这会自动安装所有依赖并检查环境。

2. **下载 libmpv-2.dll**：
   - 手动下载 https://sourceforge.net/projects/mpv-player-windows/files/libmpv/
   - 将 `libmpv-2.dll` 放到项目根目录

3. **运行程序**：
   ```bash
   python main.py
   ```

### 方式二：打包成 exe

```bash
# 1. 确保已完成上述步骤 1-2
# 2. 执行打包
python build.py

# 3. 运行打包后的程序
dist\视频播放器.exe
```

打包后的 exe 文件（约 80-90 MB）包含所有依赖，可以独立运行，无需 Python 环境。

---

## ✨ 功能特点

### 播放功能
- **多格式支持**：mp4, mkv, avi, mov, wmv, flv, webm, m4v, mpeg, mpg, 3gp 等
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

## 🛠️ 安装步骤

### 1. 安装 mpv 播放器

#### Windows
1. 从 [mpv 官网](https://mpv.io/installation/) 或 [SourceForge](https://sourceforge.net/projects/mpv-player-windows/files/) 下载 mpv
2. 解压后将 `libmpv-2.dll` 复制到项目目录

#### macOS
```bash
brew install mpv
```

#### Linux
```bash
# Ubuntu/Debian
sudo apt install mpv libmpv-dev

# Arch Linux
sudo pacman -S mpv
```

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
Player/
├── main.py              # 程序入口
├── main_window.py       # 主窗口 UI（欢迎页、播放页、控制栏、播放列表）
├── player_core.py       # mpv 播放器核心封装
├── folder_settings.py   # 设置管理（全局设置、文件夹设置）
├── create_icon.py       # 图标生成脚本
├── icon.ico             # 应用图标
├── icon.png             # PNG 图标
├── global_settings.json # 全局设置文件（运行后生成）
├── requirements.txt     # Python 依赖
└── README.md            # 说明文档
```

## 🔧 配置说明

### 全局设置（保存在程序目录）
- **播放速度**：0.25x - 3.0x，默认 1.0x
- **快进步长**：1-300 秒，默认 10 秒

### 文件夹设置（保存在程序目录）
- **跳过片头**：0-600 秒，自动填入当前播放位置
- **跳过片尾**：0-600 秒，自动填入距结尾时间
- **播放进度**：自动保存每个视频的观看进度

### 设置文件
- `global_settings.json`：全局设置，保存在程序目录
- `settings/folder_*.json`：文件夹设置，保存在程序目录的 settings 子文件夹中

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

## 📦 打包为 EXE

### 自动打包
```bash
python build.py
```

打包完成后，`dist/视频播放器.exe` 即为可执行文件（约 90MB）。

### 手动打包
```bash
pip install pyinstaller
pyinstaller build.spec --clean --noconfirm
```

### 打包注意事项
- 确保 `libmpv-2.dll` 在项目目录中
- 打包后的 exe 可独立运行，无需 Python 环境
- 首次运行可能需要一点时间解压资源

## 📋 依赖

- Python 3.10+
- PyQt6
- python-mpv
- qtawesome
- Pillow（仅用于生成图标）
- PyInstaller（仅用于打包）

## 📝 许可证

MIT License

## 🙏 致谢

- [mpv](https://mpv.io/) - 强大的开源视频播放器
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Python GUI 框架
- [qtawesome](https://github.com/spyder-ide/qtawesome) - FontAwesome 图标库
