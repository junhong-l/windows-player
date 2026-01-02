"""
视频播放器 - 主程序入口
基于 Python + mpv + PyQt6
"""
import sys
import os

# 设置 mpv 库路径（Windows）- 必须在 import mpv 之前
if sys.platform == 'win32':
    os.environ['PATH'] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ['PATH']
    # 设置 Windows 任务栏图标（需要在 QApplication 创建前设置）
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('player.videoplayer.1.0')

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QIcon

from main_window import MainWindow


class DefaultPlayerDialog(QDialog):
    """自定义深色风格的默认播放器对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置默认播放器")
        self.setFixedSize(400, 200)
        self.result_accepted = False
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 设置深色标题栏
        if sys.platform == 'win32':
            try:
                import ctypes
                hwnd = int(self.winId())
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                    ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
                )
            except:
                pass
        
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
    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    
    app = QApplication(sys.argv)
    
    # 设置应用图标（任务栏图标）
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 设置应用信息
    app.setApplicationName("视频播放器")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Player")
    
    # 设置默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 检查命令行参数（是否有传入的视频文件）
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.isfile(file_path):
            # 延迟加载文件，等窗口完全初始化
            QTimer.singleShot(200, lambda: window._load_file(file_path))
    else:
        # 没有文件参数时，检查默认播放器设置
        QTimer.singleShot(500, lambda: check_default_player(window))
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
