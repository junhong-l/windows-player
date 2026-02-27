"""
视频播放器 - 主程序入口
基于 Python + mpv + PyQt6
"""
import sys
import os
import logging
import traceback


def _get_app_exe_dir() -> str:
    """获取程序目录（用于写日志/设置）：
    - 打包后：sys.executable 所在目录（安装目录）
    - 开发时：脚本所在目录
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_resource_dir() -> str:
    """获取资源文件目录（icon.ico / libmpv-2.dll 所在位置）：
    - 打包后 PyInstaller 6+：sys._MEIPASS（即 _internal/ 子目录）
    - 开发时：脚本所在目录
    """
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _setup_logging() -> str:
    """配置日志，优先写到 exe 目录，失败则退回到 AppData。返回日志路径。"""
    primary_dir = _get_app_exe_dir()
    log_path = os.path.join(primary_dir, 'crash.log')
    try:
        # 测试是否可写
        with open(log_path, 'a', encoding='utf-8'):
            pass
    except (PermissionError, OSError):
        # 退回到 %APPDATA%\VideoPlayer\crash.log
        fallback_dir = os.path.join(
            os.environ.get('APPDATA', os.path.expanduser('~')), 'VideoPlayer'
        )
        os.makedirs(fallback_dir, exist_ok=True)
        log_path = os.path.join(fallback_dir, 'crash.log')

    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        encoding='utf-8',
    )
    return log_path


_log_path = _setup_logging()

# 启用 faulthandler：即使 C 层崩溃（段错误/访问违规）也会写入 fault.log
import faulthandler as _faulthandler
_fault_log_path = os.path.join(_get_app_exe_dir(), 'fault.log')
try:
    _fault_log_file = open(_fault_log_path, 'a', encoding='utf-8')
    _faulthandler.enable(_fault_log_file)
except Exception:
    _faulthandler.enable()  # 退回到 stderr

logging.info("========== 程序启动 ==========")
logging.info(f"版本: Python {sys.version.split()[0]}, Executable: {sys.executable}")

# 设置 DLL 搜索路径（Python 3.8+ 必须用 os.add_dll_directory，PATH 对 ctypes 无效）
# 句柄必须保存到模块级列表，否则 GC 会立即回收并移除搜索目录
_dll_dir_handles = []

if sys.platform == 'win32':
    _resource_dir = _get_resource_dir()
    _dll_dirs_to_add = [_resource_dir]
    for _sub in ('PyQt6/Qt6/bin', 'PyQt6/Qt6/plugins'):
        _p = os.path.join(_resource_dir, *_sub.split('/'))
        if os.path.isdir(_p):
            _dll_dirs_to_add.append(_p)

    for _d in _dll_dirs_to_add:
        try:
            _dll_dir_handles.append(os.add_dll_directory(_d))
        except Exception as _e:
            logging.warning(f"add_dll_directory 失败 {_d}: {_e}")

    os.environ['PATH'] = os.pathsep.join(_dll_dirs_to_add) + os.pathsep + os.environ.get('PATH', '')

    # 设置 Windows 任务栏图标（需要在 QApplication 创建前设置）
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('player.videoplayer.1.0')

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon

# 注意：MainWindow 延迟导入（在 _main_inner 内），避免模块级 C 崩溃无法记录日志


class DefaultPlayerDialog(QDialog):
    """自定义深色风格的默认播放器对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置默认播放器")
        self.setFixedSize(400, 200)
        self.result_accepted = False
        
        # 设置窗口图标
        icon_path = os.path.join(_get_resource_dir(), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setStyleSheet("""
            QDialog {
                background-color: #1a1a1a;
                color: #fff;
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
            }
            QLabel {
                color: #e0e0e0;
                background: transparent;
            }
            QLabel#title {
                font-size: 15px;
                font-weight: bold;
                color: #fff;
            }
            QLabel#subtitle {
                font-size: 13px;
                color: #888;
            }
            QCheckBox {
                color: #888;
                font-size: 12px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #555;
                border-radius: 3px;
                background: #2a2a2a;
            }
            QCheckBox::indicator:checked {
                background: #00a1d6;
                border-color: #00a1d6;
            }
            QPushButton {
                border: none;
                border-radius: 4px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#primary {
                background: #00a1d6;
                color: #fff;
            }
            QPushButton#primary:hover {
                background: #00b5e5;
            }
            QPushButton#secondary {
                background: #333;
                color: #fff;
            }
            QPushButton#secondary:hover {
                background: #444;
            }
        """)
        
        self._build()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_dark_titlebar_set', False):
            self._dark_titlebar_set = True
            if sys.platform == 'win32':
                try:
                    import ctypes
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        int(self.winId()), 20,
                        ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
                    )
                except Exception:
                    pass

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # 标题
        title = QLabel("是否将此应用设为默认视频播放器？")
        title.setObjectName("title")
        layout.addWidget(title)
        
        # 副标题
        subtitle = QLabel("设置后，双击视频文件将自动使用此播放器打开。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        
        layout.addStretch()
        
        # 复选框
        self.checkbox = QCheckBox("不再提示")
        layout.addWidget(self.checkbox)
        
        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()
        
        self.no_btn = QPushButton("暂不设置")
        self.no_btn.setObjectName("secondary")
        self.no_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.no_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.no_btn)
        
        self.yes_btn = QPushButton("设为默认")
        self.yes_btn.setObjectName("primary")
        self.yes_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.yes_btn.clicked.connect(self._on_accept)
        btn_row.addWidget(self.yes_btn)
        
        layout.addLayout(btn_row)
    
    def _on_accept(self):
        self.result_accepted = True
        self.accept()
    
    def is_never_ask_checked(self) -> bool:
        return self.checkbox.isChecked()


def check_default_player(window):
    """检查并提示设置默认播放器"""
    if sys.platform != 'win32':
        return
    
    from default_player import default_player_manager
    
    if not default_player_manager.should_ask_default():
        return
    
    # 创建自定义对话框
    dialog = DefaultPlayerDialog(window)
    dialog.exec()
    
    # 保存"不再提示"选项
    if dialog.is_never_ask_checked():
        default_player_manager.set_never_ask(True)
    
    # 如果用户选择设为默认
    if dialog.result_accepted:
        default_player_manager.set_as_default()
        # 显示提示
        window._show_toast("已注册文件关联，请在系统设置中确认", 3000)


def main():
    """主函数"""
    try:
        _main_inner()
    except Exception as e:
        logging.critical(f"程序崩溃: {e}")
        logging.critical(traceback.format_exc())
        # 尝试弹出错误对话框
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "启动错误", f"程序启动失败:\n\n{e}\n\n详细日志已写入:\n{_log_path}")
        except:
            pass
        sys.exit(1)


def _main_inner():
    """实际的主函数逻辑"""
    # 延迟导入：确保 DLL 目录已注册，且任何 ImportError 都能被 main() 捕获
    from main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    icon_path = os.path.join(_get_resource_dir(), 'icon.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    app.setApplicationName("视频播放器")
    from version import __version__
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Player")

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.isfile(file_path):
            QTimer.singleShot(200, lambda: window._load_file(file_path))
    else:
        QTimer.singleShot(500, lambda: check_default_player(window))

    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"顶层未捕获异常: {e}")
        logging.critical(traceback.format_exc())
