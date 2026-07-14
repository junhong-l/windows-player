# 🎬 视频播放器

基于 Python + mpv + PyQt6 开发的现代化视频播放器，拥有 B站风格的深色界面。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 🚀 快速开始

### 方式一：直接安装（推荐）

从 [Releases](../../releases) 下载最新的 `视频播放器_安装包_vX.X.X.exe`，双击安装即可。安装包包含所有依赖，无需 Python 环境。

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
# 需要先安装 Inno Setup（6 或以上版本均可，https://jrsoftware.org/isdl.php）
python build.py
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
- **B站风格**：现代化深色界面，半透明悬浮控制栏，按钮全部使用图标（无文字）
- **响应式布局**：窗口变窄时自动隐藏次要按钮（先隐藏音轨/字幕，再隐藏快进/快退）
- **音量弹出面板**：点击音量图标才展开滑块，不常驻占用控制栏空间
- **自动隐藏**：控制栏在鼠标移开后自动隐藏
- **深色标题栏**：Windows 10/11 原生深色标题栏
- **自定义字体**：内置 OPPO Sans 字体，界面文字更清晰
- **Toast 提示**：操作反馈提示

### 系统集成
- **文件关联**：可设为默认视频播放器
- **文件图标**：关联的视频文件显示播放器图标
- **图标修复**：内置修复文件关联图标功能

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
├── main.py              # 程序入口（日志/崩溃处理、DLL 路径、全局字体、启动流程）
├── main_window.py       # 主窗口 UI（欢迎页、播放页、控制栏、播放列表）
├── player_core.py       # mpv 播放器核心封装（播放、字幕、音轨控制）
├── folder_settings.py   # 设置管理（全局设置、文件夹设置）
├── default_player.py    # 默认播放器和文件关联管理
├── version.py           # 版本号（唯一维护处）
├── build.py             # 打包脚本
├── build.spec           # PyInstaller 打包配置
├── installer.iss        # Inno Setup 安装包脚本
├── setup.py             # 环境配置脚本
├── icon.ico             # 应用图标
├── fonts/OPPOSans4.ttf  # 内置界面字体（OPPO Sans 4.0）
├── requirements.txt     # Python 依赖
└── README.md            # 说明文档
```

运行时会额外生成以下**非代码文件**，均已在 `.gitignore` 中排除，无需手动管理，可随时删除：

| 文件/目录 | 说明 |
|-----------|------|
| `crash.log` | 每次启动都会追加一行日志，用于排查启动失败/崩溃原因 |
| `fault.log` | `faulthandler` 捕获的底层崩溃（如 mpv 线程段错误）堆栈 |
| `settings/` | 用户的全局设置和各文件夹的播放进度/片头片尾设置 |
| `__pycache__/` | Python 字节码缓存 |

> 开发模式下（直接 `python main.py` 运行）这些文件会写在项目根目录，因为程序把"当前目录"当作日志/配置的落地目录；打包后的 exe 会写在安装目录下。删除后重新运行程序会自动重建，不影响使用。

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

1. **快速设置片头**：播放到片头结束位置，点击片头按钮（门形图标），当前位置会自动填入
2. **快速设置片尾**：播放到片尾开始位置，点击片尾按钮（门形图标），距结尾时间会自动填入
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

### 根目录出现 crash.log / fault.log
这是正常现象：程序每次启动都会记录一行日志到 `crash.log`（用于排查崩溃），并用 `faulthandler` 监听底层崩溃写入 `fault.log`。两者都已在 `.gitignore` 中，可随时删除，重新运行会自动重建，不影响功能。

## 📦 打包为安装包

```bash
# 需要先安装 Inno Setup（6 或以上版本均可，https://jrsoftware.org/isdl.php）
python build.py
# 输出：dist\视频播放器_安装包_vX.X.X.exe
```

打包完成后 `dist\` 目录只保留安装包，中间产物自动清理。若只需要 PyInstaller 的一目录输出（不生成安装包），可使用 `python build.py --dir-only`。

**修改版本号**：只需编辑 `version.py` 中的 `__version__`，打包时自动同步到安装包文件名和安装界面。

## 📋 依赖

- Python 3.10+
- PyQt6
- python-mpv
- qtawesome
- darkdetect
- PyInstaller + Inno Setup 6+（仅用于打包）

## 📝 许可证

MIT License

## 🙏 致谢

- [mpv](https://mpv.io/) - 强大的开源视频播放器
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - Python GUI 框架
- [qtawesome](https://github.com/spyder-ide/qtawesome) - FontAwesome 图标库
