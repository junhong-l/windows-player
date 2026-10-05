"""
视频播放器主界面（精简美观版）
基于 PyQt6 + mpv
"""
import os
import sys
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QSpinBox,
    QDoubleSpinBox, QFrame, QSizePolicy, QMessageBox, QApplication,
    QDialog, QFormLayout, QMenu, QListWidget, QSplitter, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QRect
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QAction, QKeySequence, QIcon, QCursor
import qtawesome as qta

from player_core import PlayerCore
from folder_settings import folder_settings, global_settings


class VideoWidget(QFrame):
    """视频显示区域，支持双击全屏"""

    doubleClicked = pyqtSignal()
    rightClicked = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000;")
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ClickableSlider(QSlider):
    """可点击的进度条"""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            value = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            self.setValue(int(value))
            self.sliderMoved.emit(int(value))
        super().mousePressEvent(event)


class SettingsDialog(QDialog):
    """全局设置对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局设置")
        self.setFixedSize(360, 390)
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.setStyleSheet(
            """
            QDialog { background-color: #1a1a1a; color: #e0e0e0; font-family: "OPPO Sans 4.0", "Microsoft YaHei", "Segoe UI", sans-serif; }
            QLabel { font-size: 13px; color: #e0e0e0; background: transparent; }
            QSpinBox, QDoubleSpinBox { 
                background: #2a2a2a; 
                border: 1px solid #404040; 
                border-radius: 4px; 
                padding: 8px 12px; 
                color: #fff; 
                min-width: 140px;
                font-size: 13px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus { border-color: #00a1d6; }
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                width: 0px;
                border: none;
            }
            QPushButton { 
                background: #00a1d6; 
                color: #fff; 
                border: none; 
                border-radius: 4px; 
                padding: 10px 24px; 
                font-size: 13px;
                font-weight: bold; 
            }
            QPushButton:hover { background: #00b5e5; }
            QPushButton#clearBtn, QPushButton#fixIconBtn {
                background: #444;
            }
            QPushButton#clearBtn:hover, QPushButton#fixIconBtn:hover { background: #666; }
            """
        )
        self._build()

    def showEvent(self, event):
        """窗口显示时设置深色标题栏（此时 HWND 已完整创建）"""
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
        layout.setSpacing(18)

        # 播放速度
        speed_row = QHBoxLayout()
        speed_label = QLabel("播放速度")
        speed_label.setFixedWidth(80)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.25, 3.0)
        self.speed_spin.setSingleStep(0.25)
        self.speed_spin.setSuffix(" x")
        speed_row.addWidget(speed_label)
        speed_row.addWidget(self.speed_spin, 1)
        layout.addLayout(speed_row)

        # 快进步长
        seek_row = QHBoxLayout()
        seek_label = QLabel("快进步长")
        seek_label.setFixedWidth(80)
        self.seek_spin = QSpinBox()
        self.seek_spin.setRange(1, 300)
        self.seek_spin.setSuffix(" 秒")
        seek_row.addWidget(seek_label)
        seek_row.addWidget(self.seek_spin, 1)
        layout.addLayout(seek_row)

        # 清理缓存
        cache_row = QHBoxLayout()
        cache_label = QLabel("缓存管理")
        cache_label.setFixedWidth(80)
        self.clear_cache_btn = QPushButton("清理文件夹设置")
        self.clear_cache_btn.setObjectName("clearBtn")
        self.clear_cache_btn.setToolTip("清理所有文件夹中保存的片头片尾设置")
        self.clear_cache_btn.clicked.connect(self._clear_cache)
        cache_row.addWidget(cache_label)
        cache_row.addWidget(self.clear_cache_btn, 1)
        layout.addLayout(cache_row)

        # 修复文件关联图标
        icon_row = QHBoxLayout()
        icon_label = QLabel("文件关联")
        icon_label.setFixedWidth(80)
        self.fix_icon_btn = QPushButton("修复文件图标")
        self.fix_icon_btn.setObjectName("fixIconBtn")
        self.fix_icon_btn.setToolTip("重新注册文件关联，修复视频文件不显示播放器图标的问题")
        self.fix_icon_btn.clicked.connect(self._fix_file_icons)
        icon_row.addWidget(icon_label)
        icon_row.addWidget(self.fix_icon_btn, 1)
        layout.addLayout(icon_row)

        default_row = QHBoxLayout()
        default_label = QLabel("默认播放器")
        default_label.setFixedWidth(80)
        self.default_player_btn = QPushButton("设为默认播放器")
        self.default_player_btn.setIcon(qta.icon('fa5s.desktop', color='#ffffff'))
        self.default_player_btn.setToolTip("一键设置全部支持的视频格式")
        self.default_player_btn.clicked.connect(self._set_default_player)
        default_row.addWidget(default_label)
        default_row.addWidget(self.default_player_btn, 1)
        layout.addLayout(default_row)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("应用")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)
    
    def _set_default_player(self):
        if sys.platform != 'win32':
            QMessageBox.information(self, "提示", "此功能仅支持 Windows 系统")
            return
        self.default_player_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from default_player import default_player_manager
            success = default_player_manager.set_as_default()
        except Exception as error:
            QMessageBox.critical(self, "设置失败", str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.default_player_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, "设置完成", "所有支持的视频格式已设为使用本播放器打开。")
        else:
            QMessageBox.warning(self, "设置失败", default_player_manager.last_error or "文件关联未生效，请稍后重试。")

    def _fix_file_icons(self):
        """修复文件关联图标"""
        if sys.platform != 'win32':
            QMessageBox.information(self, "提示", "此功能仅支持 Windows 系统")
            return
        
        try:
            from default_player import default_player_manager
            
            # 重新注册文件类型
            if default_player_manager.register_file_types():
                QMessageBox.information(
                    self, "修复完成",
                    "文件关联已重新注册！\n\n"
                    "如果图标仍未显示，请尝试：\n"
                    "1. 注销并重新登录 Windows\n"
                    "2. 或者重启电脑\n\n"
                    "注意：只有打包后的 exe 才能正确显示图标"
                )
            else:
                QMessageBox.warning(self, "修复失败", "注册文件关联时出错，请以管理员身份运行程序后重试")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"修复失败：{e}")
    
    def _clear_cache(self):
        """清理所有文件夹设置缓存"""
        reply = QMessageBox.question(
            self, "确认清理",
            "确定要清理所有文件夹的片头片尾设置吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = folder_settings.clear_all_settings()
            QMessageBox.information(self, "清理完成", f"已清理 {count} 个文件夹的设置文件")


class ScrollingLabel(QLabel):
    """鼠标悬停时滚动的标签"""
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._original_text = text
        self._scroll_pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self._is_hovering = False
        self.setMouseTracking(True)
    
    def setText(self, text):
        self._original_text = text
        self._scroll_pos = 0
        super().setText(text)
    
    def enterEvent(self, event):
        self._is_hovering = True
        # 检查文本是否超出宽度
        fm = self.fontMetrics()
        if fm.horizontalAdvance(self._original_text) > self.width() - 10:
            self._scroll_pos = 0
            self._timer.start(100)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self._is_hovering = False
        self._timer.stop()
        self._scroll_pos = 0
        super().setText(self._original_text)
        super().leaveEvent(event)
    
    def _scroll(self):
        if not self._is_hovering:
            return
        display_text = self._original_text + "    " + self._original_text
        self._scroll_pos = (self._scroll_pos + 1) % (len(self._original_text) + 4)
        super().setText(display_text[self._scroll_pos:])


class PlaylistItemWidget(QWidget):
    """播放列表项 - 显示标题和进度"""
    
    def __init__(self, title: str, progress: float = 0, is_current: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        # 播放指示器
        self.indicator = QLabel("▶" if is_current else "")
        self.indicator.setFixedWidth(16)
        self.indicator.setStyleSheet("color: #00a1d6; font-size: 12px;")
        layout.addWidget(self.indicator)
        
        # 标题和进度的垂直布局
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)
        
        # 标题（滚动）
        self.title_label = ScrollingLabel(title)
        self.title_label.setStyleSheet("color: #fff; font-size: 13px; background: transparent;")
        info_layout.addWidget(self.title_label)
        
        # 进度条和百分比
        progress_layout = QHBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(6)
        
        if progress > 0:
            # 进度条
            self.progress_bar = QSlider(Qt.Orientation.Horizontal)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(progress))
            self.progress_bar.setEnabled(False)
            self.progress_bar.setFixedHeight(4)
            self.progress_bar.setStyleSheet("""
                QSlider::groove:horizontal { background: #333; height: 4px; border-radius: 2px; }
                QSlider::sub-page:horizontal { background: #00a1d6; border-radius: 2px; }
                QSlider::handle:horizontal { width: 0px; }
            """)
            progress_layout.addWidget(self.progress_bar, 1)
            
            # 百分比
            self.progress_label = QLabel(f"{progress:.0f}%")
            self.progress_label.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
            self.progress_label.setFixedWidth(35)
            progress_layout.addWidget(self.progress_label)
        else:
            progress_layout.addStretch()
        
        info_layout.addLayout(progress_layout)
        layout.addLayout(info_layout, 1)


class PlaylistWidget(QWidget):
    """播放列表悬浮面板"""
    
    fileSelected = pyqtSignal(int)  # 发送选中的文件索引
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder_path = ""
        self._files = []
        self._progress = {}
        self.setFixedSize(350, 450)
        self.setStyleSheet("""
            QWidget#playlistPanel { 
                background: rgba(26, 26, 26, 0.95); 
                border-radius: 8px;
                border: 1px solid #333;
            }
            QListWidget {
                background: transparent;
                border: none;
                color: #fff;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                padding: 0px;
                border-bottom: 1px solid #2a2a2a;
                background: transparent;
            }
            QListWidget::item:hover {
                background: rgba(255,255,255,0.05);
            }
            QListWidget::item:selected {
                background: rgba(0, 161, 214, 0.3);
            }
            QLabel { color: #888; font-size: 11px; background: transparent; }
            QLabel#titleLabel { 
                color: #fff; 
                font-size: 14px; 
                font-weight: bold; 
                padding: 12px;
                background: transparent;
            }
            QLabel#folderLabel { 
                color: #666; 
                font-size: 11px; 
                padding: 4px 12px 8px 12px;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        self.setObjectName("playlistPanel")
        self._build()
    
    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        
        # 标题行
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 8, 0)
        title = QLabel("播放列表")
        title.setObjectName("titleLabel")
        header.addWidget(title)
        header.addStretch()
        
        # 关闭按钮
        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                color: #888; 
                border: none; 
                font-size: 18px; 
            }
            QPushButton:hover { color: #fff; }
        """)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        layout.addLayout(header)
        
        # 文件夹路径
        self.folder_label = QLabel("")
        self.folder_label.setObjectName("folderLabel")
        self.folder_label.setWordWrap(True)
        layout.addWidget(self.folder_label)
        
        # 文件列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list_widget, 1)
        
        # 底部信息
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("padding: 8px 12px;")
        layout.addWidget(self.info_label)
    
    def set_files(self, folder_path: str, files: list, current_index: int):
        """设置文件列表"""
        self._folder_path = folder_path
        self._files = files
        self._progress = folder_settings.get_all_progress(folder_path)
        self.folder_label.setText(f"📁 {folder_path}")
        self._refresh_list(current_index)
        self.info_label.setText(f"共 {len(files)} 个视频")
    
    def _refresh_list(self, current_index: int):
        """刷新列表显示"""
        self.list_widget.clear()
        
        for i, file_path in enumerate(self._files):
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            progress = self._progress.get(filename, 0)
            is_current = (i == current_index)
            
            # 创建列表项
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(QSize(0, 50))
            
            # 创建自定义 widget
            widget = PlaylistItemWidget(name_without_ext, progress, is_current)
            self.list_widget.setItemWidget(item, widget)
        
        if current_index >= 0 and current_index < len(self._files):
            self.list_widget.setCurrentRow(current_index)
            self.list_widget.scrollToItem(self.list_widget.item(current_index))
    
    def update_current(self, current_index: int, files: list):
        """更新当前播放项"""
        self._files = files
        if self._folder_path:
            self._progress = folder_settings.get_all_progress(self._folder_path)
        self._refresh_list(current_index)
    
    def _on_item_double_clicked(self, item):
        index = self.list_widget.row(item)
        self.fileSelected.emit(index)


class MainWindow(QMainWindow):
    """主窗口"""
    
    # 定义信号用于跨线程通信
    videoEndedSignal = pyqtSignal()
    fileLoadedSignal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频播放器")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._apply_style()

        # 组件
        self.settings_dialog = SettingsDialog(self)
        self.playlist_widget = PlaylistWidget()
        self.playlist_widget.fileSelected.connect(self._on_playlist_select)
        self.video_widget = VideoWidget()
        self.video_widget.doubleClicked.connect(self._toggle_fullscreen)
        self.video_widget.rightClicked.connect(self._open_file)
        self.video_widget.clicked.connect(self._toggle_play)

        # 状态
        self.player: PlayerCore | None = None
        self._current_file = None
        self._current_folder = None
        self._cast_manager = None
        self._cast_dialog = None
        self._folder_files = []
        self._current_index = -1
        self._is_seeking = False
        self._is_fullscreen = False
        self._controls_visible = True
        self._mouse_in_control_area = False
        self._hide_delay_ms = 2500
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_controls)

        self.videoEndedSignal.connect(self._on_video_ended)
        self.fileLoadedSignal.connect(self._on_file_loaded)

        self._build_ui()
        self._setup_shortcuts()

        # 延迟初始化播放器
        QTimer.singleShot(80, self._init_player)

        # 定时器更新进度
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_progress)
        self._timer.start(200)

        # 拖放支持
        self.setAcceptDrops(True)

    # ========== UI ========== #
    
    def showEvent(self, event):
        """窗口显示时调用（此时 HWND 已完整创建，DWM 调用更安全）"""
        super().showEvent(event)
        # 只在首次显示时设置深色标题栏
        if not getattr(self, '_dark_titlebar_set', False):
            self._dark_titlebar_set = True
            self._set_dark_titlebar()
        # 首次显示时窗口尺寸可能尚未完全稳定，延迟校正一次控制栏位置，
        # 避免出现控制栏悬浮在窗口中间的问题
        QTimer.singleShot(0, self._update_control_bar_geometry)

    def _set_dark_titlebar(self):
        """设置深色标题栏（Windows 10/11）"""
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), 20,
                    ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
                )
            except Exception:
                pass

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #000; }
            QWidget { background-color: transparent; color: #fff; font-family: "OPPO Sans 4.0", "Microsoft YaHei", "Segoe UI", sans-serif; }
            QLabel { color: #fff; background: transparent; }
            QSlider::groove:horizontal { background: rgba(255,255,255,0.3); height: 3px; border-radius: 1px; }
            QSlider::handle:horizontal { background: #00a1d6; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { background: #00b5e5; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }
            QSlider::sub-page:horizontal { background: #00a1d6; border-radius: 1px; }
            #controlBar { background: rgba(0,0,0,0.7); border: none; }
            #progressBar { background: transparent; }
            #videoContainer { background: #000; }
            """
        )

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background-color: #000000;")
        self.setCentralWidget(central)
        self.setMouseTracking(True)
        central.setMouseTracking(True)
        self.video_widget.setMouseTracking(True)
        
        # 使用 stacked widget 切换欢迎页和播放页
        from PyQt6.QtWidgets import QStackedWidget
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setMouseTracking(True)
        self.stacked_widget.setStyleSheet("background-color: #000000;")
        
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.stacked_widget)
        
        # ===== 欢迎页 =====
        self.welcome_page = QWidget()
        self.welcome_page.setStyleSheet("background: #1a1a1a;")
        welcome_layout = QVBoxLayout(self.welcome_page)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.setSpacing(30)
        
        # 标题
        title_label = QLabel("视频播放器")
        title_label.setStyleSheet("font-size: 32px; font-weight: bold; color: #fff;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(title_label)
        
        # 按钮容器
        btn_container = QHBoxLayout()
        btn_container.setSpacing(40)
        btn_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 播放视频文件按钮
        file_btn = QPushButton()
        file_btn.setFixedSize(200, 180)
        file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        file_btn.clicked.connect(self._open_file)
        file_btn_layout = QVBoxLayout(file_btn)
        file_btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_btn_layout.setSpacing(12)
        file_icon = QLabel()
        file_icon.setPixmap(qta.icon('fa5s.file-video', color='#00a1d6').pixmap(QSize(48, 48)))
        file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_icon.setStyleSheet("background: transparent;")
        file_btn_layout.addWidget(file_icon)
        file_text = QLabel("播放视频文件")
        file_text.setStyleSheet("font-size: 15px; color: #fff; background: transparent;")
        file_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_btn_layout.addWidget(file_text)
        file_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                border: 2px solid #3a3a3a;
                border-radius: 12px;
            }
            QPushButton:hover {
                background: #333;
                border-color: #00a1d6;
            }
        """)
        btn_container.addWidget(file_btn)
        
        # 添加文件夹按钮
        folder_btn = QPushButton()
        folder_btn.setFixedSize(200, 180)
        folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        folder_btn.clicked.connect(self._open_folder)
        folder_btn_layout = QVBoxLayout(folder_btn)
        folder_btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_btn_layout.setSpacing(12)
        folder_icon = QLabel()
        folder_icon.setPixmap(qta.icon('fa5s.folder-open', color='#00a1d6').pixmap(QSize(48, 48)))
        folder_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_icon.setStyleSheet("background: transparent;")
        folder_btn_layout.addWidget(folder_icon)
        folder_text = QLabel("添加文件夹")
        folder_text.setStyleSheet("font-size: 15px; color: #fff; background: transparent;")
        folder_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        folder_btn_layout.addWidget(folder_text)
        folder_btn.setStyleSheet("""
            QPushButton {
                background: #2a2a2a;
                border: 2px solid #3a3a3a;
                border-radius: 12px;
            }
            QPushButton:hover {
                background: #333;
                border-color: #00a1d6;
            }
        """)
        btn_container.addWidget(folder_btn)
        
        welcome_layout.addLayout(btn_container)
        
        # 提示文字
        hint_label = QLabel("支持拖放视频文件或文件夹到窗口")
        hint_label.setStyleSheet("font-size: 13px; color: #666;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(hint_label)

        self.welcome_settings_btn = self._mk_icon_btn("fa5s.cog", "设置")
        self.welcome_settings_btn.clicked.connect(self._show_settings)
        welcome_layout.addWidget(self.welcome_settings_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        
        self.stacked_widget.addWidget(self.welcome_page)
        
        # ===== 播放页 =====
        self.player_page = QWidget()
        self.player_page.setMouseTracking(True)
        self.player_page.setStyleSheet("background-color: #000000;")
        player_layout = QVBoxLayout(self.player_page)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(0)
        
        # 视频区域
        player_layout.addWidget(self.video_widget, 1)
        
        self.stacked_widget.addWidget(self.player_page)
        
        # 播放列表悬浮面板（作为 central widget 的子组件）
        self.playlist_widget.setParent(central)
        self.playlist_widget.hide()
        
        self.fullscreen_title = QLabel(central)
        self.fullscreen_title.setTextFormat(Qt.TextFormat.PlainText)
        self.fullscreen_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.fullscreen_title.setContentsMargins(20, 0, 20, 0)
        self.fullscreen_title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.fullscreen_title.setStyleSheet("background: rgba(0,0,0,0.8); color: #fff; font-size: 16px;")
        self.fullscreen_title.hide()

        # 底部控制栏（悬浮覆盖层）
        self.control_widget = QWidget(central)
        self.control_widget.setObjectName("controlBar")
        self.control_widget.setFixedHeight(50)
        self.control_widget.setStyleSheet("background: rgba(0,0,0,0.8);")
        c_layout = QVBoxLayout(self.control_widget)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        # 进度条（顶部细线）
        self.progress_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setObjectName("progressBar")
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setFixedHeight(14)
        self.progress_slider.sliderPressed.connect(self._on_seek_start)
        self.progress_slider.sliderReleased.connect(self._on_seek_end)
        self.progress_slider.sliderMoved.connect(self._on_seek_move)
        c_layout.addWidget(self.progress_slider)

        # 控制按钮行
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 8)
        btn_row.setSpacing(6)
        btn_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # 左侧：上一个、播放、下一个、重播、快退、快进、时间
        self.prev_btn = self._mk_icon_btn("fa5s.step-backward", "上一个")
        self.prev_btn.clicked.connect(self._play_prev)
        btn_row.addWidget(self.prev_btn)
        
        self.play_btn = self._mk_icon_btn("fa5s.play", "播放/暂停")
        self.play_btn.clicked.connect(self._toggle_play)
        btn_row.addWidget(self.play_btn)
        
        self.next_btn = self._mk_icon_btn("fa5s.step-forward", "下一个")
        self.next_btn.clicked.connect(self._play_next)
        btn_row.addWidget(self.next_btn)
        
        # 分隔
        btn_row.addSpacing(8)
        
        self.replay_btn = self._mk_icon_btn("fa5s.redo", "重播")
        self.replay_btn.clicked.connect(self._replay)
        btn_row.addWidget(self.replay_btn)
        
        self.back_btn = self._mk_icon_btn("fa5s.backward", "快退")
        self.back_btn.clicked.connect(self._seek_backward)
        btn_row.addWidget(self.back_btn)
        
        self.fwd_btn = self._mk_icon_btn("fa5s.forward", "快进")
        self.fwd_btn.clicked.connect(self._seek_forward)
        btn_row.addWidget(self.fwd_btn)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedHeight(36)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.time_label.setStyleSheet("font-size: 13px; color: #fff; margin-left: 8px;")
        btn_row.addWidget(self.time_label)

        btn_row.addStretch()

        # 右侧：片头片尾、列表、倍速、设置、音量、全屏、返回
        self.skip_intro_btn = self._mk_icon_btn("fa5s.door-open", "跳过片头（点击设置）")
        self.skip_intro_btn.clicked.connect(self._set_skip_intro)
        btn_row.addWidget(self.skip_intro_btn)
        
        self.skip_outro_btn = self._mk_icon_btn("fa5s.door-closed", "跳过片尾（点击设置）")
        self.skip_outro_btn.clicked.connect(self._set_skip_outro)
        btn_row.addWidget(self.skip_outro_btn)
        
        self.list_btn = self._mk_icon_btn("fa5s.list", "播放列表")
        self.list_btn.clicked.connect(self._show_playlist)
        btn_row.addWidget(self.list_btn)
        
        self.speed_btn = self._mk_icon_btn("fa5s.tachometer-alt", "播放速度")
        self.speed_btn.clicked.connect(self._show_speed_menu)
        btn_row.addWidget(self.speed_btn)
        
        self.audio_btn = self._mk_icon_btn("fa5s.headphones", "选择音轨")
        self.audio_btn.clicked.connect(self._show_audio_menu)
        btn_row.addWidget(self.audio_btn)
        
        self.subtitle_btn = self._mk_icon_btn("fa5s.closed-captioning", "选择字幕")
        self.subtitle_btn.clicked.connect(self._show_subtitle_menu)
        btn_row.addWidget(self.subtitle_btn)

        self.cast_btn = self._mk_icon_btn("fa5s.tv", "投屏（DLNA）")
        self.cast_btn.clicked.connect(self._show_cast_dialog)
        btn_row.addWidget(self.cast_btn)

        self.settings_btn = self._mk_icon_btn("fa5s.cog", "设置")
        self.settings_btn.clicked.connect(self._show_settings)
        btn_row.addWidget(self.settings_btn)

        self.mute_btn = self._mk_icon_btn("fa5s.volume-up", "音量")
        self.mute_btn.clicked.connect(self._toggle_volume_popup)
        btn_row.addWidget(self.mute_btn)

        # 音量滑块改为悬浮弹出面板，点击音量按钮时才显示，不再一直占用控制栏空间
        self.volume_popup = QWidget(central)
        self.volume_popup.setObjectName("volumePopup")
        self.volume_popup.setStyleSheet("""
            QWidget#volumePopup {
                background: rgba(30, 30, 30, 0.92);
                border: 1px solid #444;
                border-radius: 6px;
            }
        """)
        popup_layout = QVBoxLayout(self.volume_popup)
        popup_layout.setContentsMargins(8, 10, 8, 10)

        self.volume_slider = QSlider(Qt.Orientation.Vertical)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedHeight(100)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        popup_layout.addWidget(self.volume_slider, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.volume_popup.setFixedSize(40, 130)
        self.volume_popup.hide()

        self.full_btn = self._mk_icon_btn("fa5s.expand", "全屏")
        self.full_btn.clicked.connect(self._toggle_fullscreen)
        btn_row.addWidget(self.full_btn)
        
        self.home_btn = self._mk_icon_btn("fa5s.home", "返回主页")
        self.home_btn.clicked.connect(self._go_home)
        btn_row.addWidget(self.home_btn)

        c_layout.addLayout(btn_row)
        
        # 控制栏初始位置（会在resizeEvent中更新）
        self.control_widget.raise_()  # 确保在最上层
        self.control_widget.hide()  # 初始隐藏
        
        # Toast 提示标签
        self.toast_label = QLabel(central)
        self.toast_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast_label.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.75);
                color: #fff;
                font-size: 14px;
                padding: 12px 24px;
                border-radius: 6px;
            }
        """)
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast_label.hide)

    def _show_toast(self, message: str, duration: int = 1500):
        """显示 Toast 提示"""
        self.toast_label.setText(message)
        self.toast_label.adjustSize()
        # 居中显示
        x = (self.width() - self.toast_label.width()) // 2
        y = (self.height() - self.toast_label.height()) // 2
        self.toast_label.move(x, y)
        self.toast_label.raise_()
        self.toast_label.show()
        self.toast_timer.start(duration)

    def _mk_icon_btn(self, icon_name: str, tip: str) -> QPushButton:
        """创建图标按钮（使用qtawesome矢量图标）"""
        btn = QPushButton()
        btn.setIcon(qta.icon(icon_name, color='#ffffff'))
        btn.setIconSize(QSize(18, 18))
        btn.setToolTip(tip)
        btn.setFixedSize(36, 36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                border: none; 
            }
            QPushButton:hover { background: rgba(255,255,255,0.1); border-radius: 4px; }
            QToolTip { background: #333; color: #fff; border: 1px solid #555; padding: 4px; }
        """)
        return btn

    def _mk_text_btn(self, text: str, tip: str) -> QPushButton:
        """创建文字按钮"""
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { 
                background: transparent; 
                color: #fff; 
                border: none; 
                font-size: 13px;
                padding: 0px 8px;
            }
            QPushButton:hover { color: #00a1d6; }
            QToolTip { background: #333; color: #fff; border: 1px solid #555; padding: 4px; }
        """)
        return btn

    # ========== 快捷键 ========== #

    def _setup_shortcuts(self):
        mapping = [
            (Qt.Key.Key_Space, self._toggle_play),
            (Qt.Key.Key_Left, self._seek_backward),
            (Qt.Key.Key_Right, self._seek_forward),
            (Qt.Key.Key_Up, lambda: self.volume_slider.setValue(min(100, self.volume_slider.value() + 5))),
            (Qt.Key.Key_Down, lambda: self.volume_slider.setValue(max(0, self.volume_slider.value() - 5))),
            (Qt.Key.Key_M, self._toggle_mute),
            (Qt.Key.Key_F, self._toggle_fullscreen),
            (Qt.Key.Key_Escape, self._exit_fullscreen),
        ]
        for key, cb in mapping:
            act = QAction(self)
            act.setShortcut(QKeySequence(key))
            act.triggered.connect(cb)
            self.addAction(act)

        open_act = QAction(self)
        open_act.setShortcut(QKeySequence("Ctrl+O"))
        open_act.triggered.connect(self._open_file)
        self.addAction(open_act)

    # ========== 播放器初始化 ========== #

    def _init_player(self):
        try:
            wid = int(self.video_widget.winId())
            self.player = PlayerCore(wid)
            self.player.set_position_callback(self._on_position_changed)
            self.player.set_duration_callback(self._on_duration_changed)
            # 使用 lambda 发射信号，避免跨线程直接调用
            self.player.set_eof_callback(lambda: self.videoEndedSignal.emit())
            self.player.set_file_loaded_callback(lambda: self.fileLoadedSignal.emit())
        except Exception as e:
            QMessageBox.critical(self, "错误", f"初始化播放器失败：{e}\n请确认 mpv 已正确安装。")
    
    def _on_file_loaded(self):
        """文件加载完成 - 在主线程中执行"""
        # 确保开始播放
        if self.player:
            self.player.play()
            
            # 恢复播放进度
            if self._current_file and self.player.duration:
                saved_progress = folder_settings.get_progress(self._current_file)
                if saved_progress > 0 and saved_progress < 95:
                    # 有保存的进度且未播放完，跳转到该位置
                    target_pos = (saved_progress / 100) * self.player.duration
                    # 确保不会跳到片尾区域
                    if self.player.skip_outro > 0:
                        max_pos = self.player.duration - self.player.skip_outro - 5
                        target_pos = min(target_pos, max_pos)
                    if target_pos > 0:
                        self.player.seek_to(target_pos)
                        self._show_toast(f"已恢复到 {saved_progress:.0f}%")
                # 如果进度 >= 95%，视为已播完，从头开始（跳过片头）
                
        # 更新按钮图标为暂停（表示正在播放）
        self.play_btn.setIcon(qta.icon('fa5s.pause', color='#ffffff'))
        self._update_fullscreen_title()
    
    def _on_video_ended(self):
        """视频播放结束（包括片尾跳过触发）- 在主线程中执行"""
        # 如果有文件夹列表，自动播放下一个
        if self._folder_files and self._current_index >= 0:
            if self._current_index < len(self._folder_files) - 1:
                # 还有下一集，自动播放
                self._current_index += 1
                self._load_file(self._folder_files[self._current_index])
            else:
                # 已经是最后一个视频
                self._show_toast("已播放完最后一个视频")
                self.play_btn.setIcon(qta.icon('fa5s.play', color='#ffffff'))

    # ========== 文件操作 ========== #

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.m4v *.mpeg *.mpg *.3gp);;所有文件 (*.*)"
        )
        if file_path:
            self._current_folder = None
            self._folder_files = []
            self._current_index = -1
            self._load_file(file_path)

    def _open_folder(self):
        """打开文件夹，加载其中所有视频文件"""
        folder_path = QFileDialog.getExistingDirectory(self, "选择视频文件夹", "")
        if folder_path:
            self._load_folder(folder_path)
    
    def _load_folder(self, folder_path: str):
        """加载文件夹中的视频文件"""
        video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpeg', '.mpg', '.3gp'}
        files = []
        
        for f in sorted(os.listdir(folder_path)):
            ext = os.path.splitext(f)[1].lower()
            if ext in video_extensions:
                files.append(os.path.join(folder_path, f))
        
        if not files:
            QMessageBox.warning(self, "提示", "该文件夹中没有找到视频文件")
            return
        
        self._current_folder = folder_path
        self._folder_files = files
        self._current_index = 0
        
        # 更新播放列表数据（但不显示）
        self.playlist_widget.set_files(folder_path, files, 0)
        
        self._load_file(files[0])
    
    def _show_playlist_panel(self):
        """显示播放列表悬浮面板"""
        self._update_playlist_geometry()
        self.playlist_widget.show()
        self.playlist_widget.raise_()
    
    def _play_next(self):
        """播放下一个视频"""
        if not self._folder_files or self._current_index < 0:
            self._show_toast("请先添加文件夹")
            return
        if self._current_index < len(self._folder_files) - 1:
            self._current_index += 1
            self._load_file(self._folder_files[self._current_index])
        else:
            self._show_toast("已经是最后一个了")
    
    def _play_prev(self):
        """播放上一个视频"""
        if not self._folder_files or self._current_index < 0:
            self._show_toast("请先添加文件夹")
            return
        if self._current_index > 0:
            self._current_index -= 1
            self._load_file(self._folder_files[self._current_index])
        else:
            self._show_toast("已经是第一个了")

    def _load_file(self, file_path: str):
        if not self.player:
            return
        
        # 保存上一个文件的播放进度
        self._save_current_progress()
        
        self._current_file = file_path
        self.setWindowTitle(f"视频播放器 - {os.path.basename(file_path)}")
        
        # 切换到播放页
        self.stacked_widget.setCurrentIndex(1)
        self.control_widget.show()
        
        # 加载全局设置（速度、快进步长）
        g_settings = global_settings.load()
        self.player.speed = g_settings.speed
        self.player.seek_step = g_settings.seek_step
        
        # 加载文件夹设置（片头片尾）
        f_settings = folder_settings.load_settings(file_path)
        self.player.skip_intro = f_settings.skip_intro
        self.player.skip_outro = f_settings.skip_outro
        
        # 更新UI显示（图标按钮通过 tooltip 显示当前状态）
        self.speed_btn.setToolTip(f"播放速度（当前 {g_settings.speed}x）" if g_settings.speed != 1.0 else "播放速度")
        self.skip_intro_btn.setToolTip(f"跳过片头（当前 {f_settings.skip_intro}s，点击设置）" if f_settings.skip_intro > 0 else "跳过片头（点击设置）")
        self.skip_outro_btn.setToolTip(f"跳过片尾（当前 {f_settings.skip_outro}s，点击设置）" if f_settings.skip_outro > 0 else "跳过片尾（点击设置）")
        
        # 更新播放列表当前项
        if self._folder_files:
            self.playlist_widget.update_current(self._current_index, self._folder_files)
        
        self.player.load(file_path)
        self.fullscreen_title.hide()
        # 按钮图标会在 _on_file_loaded 中根据实际播放状态更新
        self._show_controls()
        self._maybe_start_hide_timer()

    # ========== 播放控制 ========== #

    def _toggle_play(self):
        if not self.player:
            return
        self.player.toggle_pause()
        icon_name = 'fa5s.play' if self.player.is_paused else 'fa5s.pause'
        self.play_btn.setIcon(qta.icon(icon_name, color='#ffffff'))
        if self.player.is_paused:
            self._show_controls(persist=True)
        else:
            self._maybe_start_hide_timer()
        self._update_fullscreen_title()

    def _stop(self):
        if self.player:
            # 保存播放进度
            self._save_current_progress()
            self.player.stop()
            self.play_btn.setIcon(qta.icon('fa5s.play', color='#ffffff'))
            self.progress_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")
            self.fullscreen_title.hide()
    
    def _save_current_progress(self):
        """保存当前文件的播放进度"""
        try:
            if self._current_file and self.player and self.player.duration:
                percentage = (self.player.position / self.player.duration) * 100
                if percentage > 1:  # 只保存播放超过1%的进度
                    folder_settings.save_progress(self._current_file, percentage)
        except Exception:
            # mpv 核心可能已关闭
            pass

    def _go_home(self):
        """返回主页"""
        self._stop()
        self._current_file = None
        self._current_folder = None
        self._folder_files = []
        self._current_index = -1
        self.setWindowTitle("视频播放器")
        self.stacked_widget.setCurrentIndex(0)
        self.control_widget.hide()
        self.fullscreen_title.hide()

    def _seek_forward(self):
        if self.player:
            self.player.seek_forward()

    def _seek_backward(self):
        if self.player:
            self.player.seek_backward()

    def _replay(self):
        """重播当前视频"""
        if self.player:
            # 跳转到开头（考虑片头跳过）
            start_pos = self.player.skip_intro if self.player.skip_intro > 0 else 0
            self.player.seek_to(start_pos)
            self.player.play()
            self.play_btn.setIcon(qta.icon('fa5s.pause', color='#ffffff'))
            self._update_fullscreen_title()
            self._show_toast("重新播放")

    # ========== 进度 ========== #

    def _on_seek_start(self):
        self._is_seeking = True
        self._show_controls(persist=True)

    def _on_seek_end(self):
        self._is_seeking = False
        if self.player and self.player.duration:
            pos = self.progress_slider.value() / 1000 * self.player.duration
            self.player.seek_to(pos)
        self._maybe_start_hide_timer()

    def _on_seek_move(self, value):
        if self.player and self.player.duration:
            pos = value / 1000 * self.player.duration
            self.time_label.setText(f"{self._format_time(pos)} / {self._format_time(self.player.duration)}")

    def _update_progress(self):
        self._update_fullscreen_title()
        if not self.player or self._is_seeking:
            return
        duration = self.player.duration
        if duration > 0:
            pos = self.player.position
            self.progress_slider.setValue(int(pos / duration * 1000))
            self.time_label.setText(f"{self._format_time(pos)} / {self._format_time(duration)}")

    def _on_position_changed(self, position: float):
        # 实时进度更新由定时器完成
        pass

    def _on_duration_changed(self, duration: float):
        self.time_label.setText(f"00:00 / {self._format_time(duration)}")

    # ========== 音量 ========== #

    def _on_volume_changed(self, value: int):
        if self.player:
            self.player.volume = value
        icon_name = 'fa5s.volume-mute' if value == 0 else 'fa5s.volume-up'
        self.mute_btn.setIcon(qta.icon(icon_name, color='#ffffff'))

    def _toggle_mute(self):
        if not self.player:
            return
        self.player.muted = not self.player.muted
        icon_name = 'fa5s.volume-mute' if self.player.muted else 'fa5s.volume-up'
        self.mute_btn.setIcon(qta.icon(icon_name, color='#ffffff'))

    def _toggle_volume_popup(self):
        """点击音量按钮时显示/隐藏音量滑块弹出面板"""
        if self.volume_popup.isVisible():
            self.volume_popup.hide()
        else:
            self._position_volume_popup()
            self.volume_popup.show()
            self.volume_popup.raise_()

    def _position_volume_popup(self):
        """将音量弹出面板定位到音量按钮正上方"""
        btn_top_left = self.mute_btn.mapTo(self.centralWidget(), self.mute_btn.rect().topLeft())
        x = btn_top_left.x() + (self.mute_btn.width() - self.volume_popup.width()) // 2
        y = btn_top_left.y() - self.volume_popup.height() - 6
        self.volume_popup.move(max(0, x), max(0, y))

    # ========== 播放列表 ========== #

    def _show_playlist(self):
        """切换播放列表悬浮面板"""
        if self.playlist_widget.isVisible():
            self.playlist_widget.hide()
        else:
            if self._folder_files:
                self.playlist_widget.set_files(
                    self._current_folder or "",
                    self._folder_files,
                    self._current_index
                )
            self._update_playlist_geometry()
            self.playlist_widget.show()
            self.playlist_widget.raise_()
    
    def _on_playlist_select(self, index: int):
        """播放列表选中文件"""
        if 0 <= index < len(self._folder_files):
            self._current_index = index
            self._load_file(self._folder_files[index])

    # ========== 设置 ========== #

    def _show_speed_menu(self):
        """显示倍速选择菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #222;
                color: #fff;
                border: 1px solid #444;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
            }
            QMenu::item:selected {
                background: #00a1d6;
            }
        """)
        
        speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
        current_speed = self.player.speed if self.player else 1.0
        
        for speed in speeds:
            label = f"{'✓ ' if abs(speed - current_speed) < 0.01 else '   '}{speed}x"
            action = menu.addAction(label)
            action.setData(speed)
        
        action = menu.exec(self.speed_btn.mapToGlobal(self.speed_btn.rect().topLeft()))
        if action and self.player:
            speed = action.data()
            self.player.speed = speed
            self.speed_btn.setToolTip(f"播放速度（当前 {speed}x）" if speed != 1.0 else "播放速度")
            # 只影响当前播放，不保存到全局设置

    def _show_audio_menu(self):
        """显示音轨选择菜单"""
        if not self.player:
            return
        
        tracks = self.player.get_audio_tracks()
        if not tracks:
            QMessageBox.information(self, "提示", "当前视频没有可用的音轨")
            return
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #222;
                color: #fff;
                border: 1px solid #444;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
            }
            QMenu::item:selected {
                background: #00a1d6;
            }
        """)
        
        current_aid = self.player.current_audio_track
        
        for track in tracks:
            tid = track['id']
            title = track['title'] or f"音轨 {tid}"
            lang = track['lang']
            if lang:
                title = f"{title} [{lang}]"
            
            label = f"{'✓ ' if tid == current_aid else '   '}{title}"
            action = menu.addAction(label)
            action.setData(tid)
        
        action = menu.exec(self.audio_btn.mapToGlobal(self.audio_btn.rect().topLeft()))
        if action and self.player:
            track_id = action.data()
            self.player.set_audio_track(track_id)
            # 更新按钮提示
            for track in tracks:
                if track['id'] == track_id:
                    lang = track['lang'] or ""
                    self.audio_btn.setToolTip(f"选择音轨（当前 {lang}）" if lang else "选择音轨")
                    break

    def _show_subtitle_menu(self):
        """显示字幕选择菜单"""
        if not self.player:
            return
        
        tracks = self.player.get_subtitle_tracks()
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #222;
                color: #fff;
                border: 1px solid #444;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
            }
            QMenu::item:selected {
                background: #00a1d6;
            }
            QMenu::separator {
                height: 1px;
                background: #444;
                margin: 5px 0;
            }
        """)
        
        current_sid = self.player.current_subtitle_track
        
        # 添加"关闭字幕"选项
        label = f"{'✓ ' if current_sid == 0 else '   '}关闭字幕"
        action = menu.addAction(label)
        action.setData(0)
        
        if tracks:
            menu.addSeparator()
            
            for track in tracks:
                tid = track['id']
                title = track['title'] or f"字幕 {tid}"
                lang = track['lang']
                external = track['external']
                
                # 构建显示标签
                parts = [title]
                if lang:
                    parts.append(f"[{lang}]")
                if external:
                    parts.append("(外挂)")
                
                label = f"{'✓ ' if tid == current_sid else '   '}{' '.join(parts)}"
                action = menu.addAction(label)
                action.setData(tid)
        
        menu.addSeparator()
        
        # 添加"加载外部字幕"选项
        load_action = menu.addAction("   📁 加载外部字幕...")
        load_action.setData(-1)
        
        # 添加字幕延迟设置
        delay_action = menu.addAction(f"   ⏱ 字幕延迟 ({self.player.subtitle_delay:+.1f}s)")
        delay_action.setData(-2)
        
        action = menu.exec(self.subtitle_btn.mapToGlobal(self.subtitle_btn.rect().topLeft()))
        if action and self.player:
            data = action.data()
            if data == -1:
                # 加载外部字幕
                self._load_external_subtitle()
            elif data == -2:
                # 设置字幕延迟
                self._set_subtitle_delay()
            else:
                # 选择字幕轨道
                self.player.set_subtitle_track(data)
                # 更新按钮显示
                if data == 0:
                    self.subtitle_btn.setToolTip("选择字幕")
                else:
                    for track in tracks:
                        if track['id'] == data:
                            lang = track['lang'] or ""
                            self.subtitle_btn.setToolTip(f"选择字幕（当前 {lang}）" if lang else "选择字幕")
                            break
    
    def _load_external_subtitle(self):
        """加载外部字幕文件"""
        if not self.player:
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择字幕文件",
            os.path.dirname(self._current_file) if self._current_file else "",
            "字幕文件 (*.srt *.ass *.ssa *.sub *.vtt *.idx);;所有文件 (*.*)"
        )
        if file_path:
            self.player.load_external_subtitle(file_path)
            self._show_toast(f"已加载字幕: {os.path.basename(file_path)}")
    
    def _set_subtitle_delay(self):
        """设置字幕延迟"""
        if not self.player:
            return
        
        from PyQt6.QtWidgets import QInputDialog
        current_delay = self.player.subtitle_delay
        value, ok = QInputDialog.getDouble(
            self, "字幕延迟",
            "设置字幕延迟（秒）：\n正值表示字幕延后显示，负值表示字幕提前显示",
            current_delay, -30.0, 30.0, 1
        )
        if ok:
            self.player.subtitle_delay = value
            self._show_toast(f"字幕延迟: {value:+.1f}s")

    def _show_settings(self):
        """显示全局设置对话框"""
        g_settings = global_settings.load()
        self.settings_dialog.speed_spin.setValue(g_settings.speed)
        self.settings_dialog.seek_spin.setValue(g_settings.seek_step)
        
        if self.settings_dialog.exec() == QDialog.DialogCode.Accepted:
            speed = self.settings_dialog.speed_spin.value()
            seek_step = self.settings_dialog.seek_spin.value()
            
            # 保存到全局设置
            global_settings.update(speed=speed, seek_step=seek_step)
            
            # 应用到当前播放器
            if self.player:
                self.player.speed = speed
                self.player.seek_step = seek_step
                self.speed_btn.setToolTip(f"播放速度（当前 {speed}x）" if speed != 1.0 else "播放速度")

    def _show_cast_dialog(self):
        if not self._current_file:
            self._show_toast("请先打开视频")
            return
        try:
            if self._cast_manager is None:
                from casting import CastManager
                from cast_dialog import CastDialog
                self._cast_manager = CastManager(self)
                self._cast_manager.started.connect(self._on_cast_started)
                self._cast_manager.stopped.connect(self._on_cast_stopped)
                self._cast_dialog = CastDialog(self._cast_manager, self._cast_media, self)
            self._cast_dialog.refresh_context()
            self._cast_dialog.show()
            self._cast_dialog.raise_()
            self._cast_dialog.activateWindow()
        except Exception as error:
            QMessageBox.warning(self, "投屏不可用", str(error))

    def _cast_media(self):
        return (self._current_file, self.player.position if self.player else 0,
            self.player.duration if self.player else 0)

    def _on_cast_started(self, session):
        self.cast_btn.setIcon(qta.icon('fa5s.tv', color='#00a1d6'))
        self.cast_btn.setToolTip("投屏中：" + session['device'])
        if self.player and self._current_file == session['file']:
            self.player.pause()
            self.play_btn.setIcon(qta.icon('fa5s.play', color='#ffffff'))
            self._update_fullscreen_title()

    def _on_cast_stopped(self, previous):
        self.cast_btn.setIcon(qta.icon('fa5s.tv', color='#ffffff'))
        self.cast_btn.setToolTip("投屏（DLNA）")
        if self.player and self._current_file == previous.get('file'):
            self.player.seek_to(previous.get('position', 0))
            if previous.get('state') == 'PLAYING':
                self.player.play()
                self.play_btn.setIcon(qta.icon('fa5s.pause', color='#ffffff'))
            self._update_fullscreen_title()
    
    def _set_skip_intro(self):
        """设置跳过片头时间 - 默认值为当前播放位置"""
        if not self._current_file or not self.player:
            return
        
        # 获取当前播放位置作为默认值
        current_pos = int(self.player.position) if self.player.position else 0
        value, ok = self._ask_skip_seconds(
            "跳过片头",
            "设置跳过片头的秒数（针对当前文件夹，范围 0~600 秒）：\n当前播放位置已自动填入",
            current_pos
        )
        if ok:
            self.player.skip_intro = value
            folder_settings.update_settings(self._current_file, skip_intro=value)
            self.skip_intro_btn.setToolTip(f"跳过片头（当前 {value}s，点击设置）" if value > 0 else "跳过片头（点击设置）")
    
    def _set_skip_outro(self):
        """设置跳过片尾时间 - 默认值为距离视频结尾的时间"""
        if not self._current_file or not self.player:
            return
        
        # 获取距离视频结尾的时间作为默认值
        duration = self.player.duration or 0
        current_pos = self.player.position or 0
        time_to_end = int(duration - current_pos) if duration > current_pos else 0
        value, ok = self._ask_skip_seconds(
            "跳过片尾",
            "设置跳过片尾的秒数（针对当前文件夹，范围 0~600 秒）：\n距视频结尾的时间已自动填入",
            time_to_end
        )
        if ok:
            self.player.skip_outro = value
            folder_settings.update_settings(self._current_file, skip_outro=value)
            self.skip_outro_btn.setToolTip(f"跳过片尾（当前 {value}s，点击设置）" if value > 0 else "跳过片尾（点击设置）")

    def _ask_skip_seconds(self, title: str, hint: str, default_value: int) -> tuple[int, bool]:
        """弹出中文数字输入对话框，用于设置跳过秒数（0~600，无上下箭头）"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(340, 170)
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            dialog.setWindowIcon(QIcon(icon_path))
        dialog.setStyleSheet("""
            QDialog { background-color: #1a1a1a; color: #e0e0e0; font-family: "OPPO Sans 4.0", "Microsoft YaHei", "Segoe UI", sans-serif; }
            QLabel { font-size: 13px; color: #e0e0e0; background: transparent; }
            QSpinBox {
                background: #2a2a2a;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 8px 12px;
                color: #fff;
                font-size: 13px;
            }
            QSpinBox:focus { border-color: #00a1d6; }
            QSpinBox::up-button, QSpinBox::down-button { width: 0px; border: none; }
            QPushButton {
                background: #00a1d6;
                color: #fff;
                border: none;
                border-radius: 4px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background: #00b5e5; }
            QPushButton#cancelBtn { background: #444; }
            QPushButton#cancelBtn:hover { background: #666; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(14)

        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        spin = QSpinBox()
        spin.setRange(0, 600)
        spin.setSuffix(" 秒")
        spin.setValue(max(0, min(600, default_value)))
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        layout.addWidget(spin)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(dialog.reject)
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        return spin.value(), accepted

    # ========== 全屏 ========== #

    def _update_fullscreen_title(self):
        if not hasattr(self, 'fullscreen_title'):
            return
        central = self.centralWidget()
        in_title_corner = self.isActiveWindow() and QRect(0, 0, min(320, central.width()), 50).contains(
            central.mapFromGlobal(QCursor.pos())
        )
        visible = bool(
            self._is_fullscreen and self._current_file and self.player
            and (self.player.is_paused or in_title_corner) and self.player.duration > 0
            and self.stacked_widget.currentIndex() == 1
        )
        if not visible:
            self.fullscreen_title.hide()
            return
        self.fullscreen_title.setGeometry(0, 0, self.centralWidget().width(), 50)
        filename = os.path.basename(self._current_file)
        self.fullscreen_title.setText(self.fullscreen_title.fontMetrics().elidedText(
            filename, Qt.TextElideMode.ElideMiddle,
            max(0, self.fullscreen_title.contentsRect().width())
        ))
        self.fullscreen_title.show()
        self.fullscreen_title.raise_()

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._is_fullscreen = True
        # Windows 11 会给窗口绘制一条 1px 的 DWM 强调色边框，即使调用了
        # showFullScreen() 该边框依然可见（表现为四周的白边）。这里在进入
        # 全屏前显式去掉边框颜色（不改变窗口原生边框标志，不影响 mpv 嵌入
        # 的子窗口句柄），从根源上消除该边框。
        self._set_dwm_border(enabled=False)
        self._set_dwm_corner(rounded=False)
        self.showFullScreen()
        self.full_btn.setIcon(qta.icon('fa5s.compress', color='#ffffff'))
        self._maybe_start_hide_timer()
        # showFullScreen() 切换时（尤其是在扩展屏/不同DPI的情况下）resizeEvent
        # 可能会用过渡态的旧尺寸触发一次，导致控制栏悬浮位置计算错误。
        # 这里立即重新计算一次，并在事件循环空闲后再校正一次，确保最终尺寸生效。
        self._update_control_bar_geometry()
        QTimer.singleShot(0, self._update_control_bar_geometry)

    def _exit_fullscreen(self):
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.showNormal()
            self._set_dwm_border(enabled=True)
            self._set_dwm_corner(rounded=True)
            self.full_btn.setIcon(qta.icon('fa5s.expand', color='#ffffff'))
            self._show_controls(persist=True)
            self._update_control_bar_geometry()
            QTimer.singleShot(0, self._update_control_bar_geometry)

    def _set_dwm_border(self, enabled: bool):
        """启用/禁用 Windows 11 窗口的 DWM 强调色边框（全屏时需要禁用，
        否则四周会露出一条 1px 的亮色边框）"""
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            # DWMWA_BORDER_COLOR = 34；DWMWA_COLOR_NONE = 0xFFFFFFFE（不绘制边框）
            # DWMWA_COLOR_DEFAULT = 0xFFFFFFFF（恢复系统默认边框）
            color = ctypes.c_int(-1 if enabled else -2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 34,
                ctypes.byref(color), ctypes.sizeof(color)
            )
        except Exception:
            pass

    def _set_dwm_corner(self, rounded: bool):
        """设置/恢复 Windows 11 窗口圆角（全屏时需要关闭圆角，否则窗口
        左右下角仍是圆角，会露出下方桌面背景，表现为底部两角漏色）"""
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33
            # DWMWCP_DEFAULT = 0（系统默认，圆角）；DWMWCP_DONOTROUND = 1（直角）
            preference = ctypes.c_int(0 if rounded else 1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()), 33,
                ctypes.byref(preference), ctypes.sizeof(preference)
            )
        except Exception:
            pass

    # ========== 拖放 ========== #

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self._load_folder(path)
            elif os.path.isfile(path):
                self._current_folder = None
                self._folder_files = []
                self._current_index = -1
                self._load_file(path)

    def mouseMoveEvent(self, event):
        # 检测鼠标是否在底部控制栏区域（底部80像素）
        window_height = self.height()
        mouse_y = event.position().y()
        in_control_area = mouse_y >= window_height - 80
        
        if in_control_area:
            self._mouse_in_control_area = True
            self._show_controls()
            self._hide_timer.stop()
        else:
            self._mouse_in_control_area = False
            # 不在控制区域，启动隐藏定时器
            self._maybe_start_hide_timer()
        
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        """鼠标离开窗口时启动隐藏定时器"""
        self._mouse_in_control_area = False
        self._maybe_start_hide_timer()
        super().leaveEvent(event)

    def enterEvent(self, event):
        """鼠标进入窗口"""
        # 不自动显示控制栏，只有移动到底部才显示
        super().enterEvent(event)

    def mousePressEvent(self, event):
        """点击音量弹出面板和音量按钮之外的区域时，自动收起音量面板"""
        if hasattr(self, 'volume_popup') and self.volume_popup.isVisible():
            central = self.centralWidget()
            pos = central.mapFromGlobal(event.globalPosition().toPoint())
            in_popup = self.volume_popup.geometry().contains(pos)
            btn_rect = QRect(self.mute_btn.mapTo(central, self.mute_btn.rect().topLeft()), self.mute_btn.size())
            in_btn = btn_rect.contains(pos)
            if not in_popup and not in_btn:
                self.volume_popup.hide()
        super().mousePressEvent(event)

    # ========== 工具 ========== #

    @staticmethod
    def _format_time(seconds: float) -> str:
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _maybe_start_hide_timer(self):
        """启动隐藏控制栏的定时器"""
        if self._mouse_in_control_area or self._is_seeking:
            self._hide_timer.stop()
            return
        self._hide_timer.start(self._hide_delay_ms)

    def _show_controls(self, persist: bool = False):
        """显示控制栏"""
        # 先刷新一次几何位置，避免使用过时的窗口尺寸导致控制栏悬浮在错误位置
        self._update_control_bar_geometry()
        if not self._controls_visible:
            self.control_widget.show()
            self._controls_visible = True
        if persist:
            self._hide_timer.stop()

    def _hide_controls(self):
        """隐藏控制栏"""
        if self._mouse_in_control_area or self._is_seeking:
            return
        self.control_widget.hide()
        self._controls_visible = False
        if hasattr(self, 'volume_popup'):
            self.volume_popup.hide()

    def resizeEvent(self, event):
        """窗口大小改变时更新控制栏和播放列表位置"""
        super().resizeEvent(event)
        self._update_control_bar_geometry()
        self._update_playlist_geometry()
        self._update_control_bar_responsive()
        if hasattr(self, 'volume_popup'):
            self.volume_popup.hide()
    
    def _update_control_bar_geometry(self):
        """更新控制栏位置和大小"""
        # 控制栏覆盖整个底部
        self.control_widget.setGeometry(
            0, 
            self.centralWidget().height() - 50, 
            self.centralWidget().width(), 
            50
        )
        self._update_fullscreen_title()

    def _update_control_bar_responsive(self):
        """窗口宽度不足时，按优先级隐藏部分按钮以节省空间"""
        width = self.centralWidget().width()

        # 宽度不足时，依次隐藏：音轨/字幕 -> 快进/快退
        show_audio_subtitle = width >= 1090
        show_seek = width >= 990

        for btn in (self.audio_btn, self.subtitle_btn):
            btn.setVisible(show_audio_subtitle)
        for btn in (self.back_btn, self.fwd_btn):
            btn.setVisible(show_seek)
    
    def _update_playlist_geometry(self):
        """更新播放列表位置（右侧悬浮）"""
        if self.playlist_widget.isVisible():
            # 定位到右侧，距离底部留出控制栏空间
            x = self.centralWidget().width() - self.playlist_widget.width() - 10
            y = 10
            self.playlist_widget.move(x, y)
            self.playlist_widget.raise_()

    def closeEvent(self, event):
        self._save_current_progress()
        self._timer.stop()
        self._hide_timer.stop()
        if self._cast_manager is not None:
            self._cast_manager.close()
        if self.player:
            try:
                # 先清除所有回调，防止 mpv 事件线程在 terminate() 后访问已销毁的 handle
                self.player._on_position_changed = None
                self.player._on_duration_changed = None
                self.player._on_eof_reached = None
                self.player._on_file_loaded = None
                self.player.stop()
            except Exception:
                pass
            self.player = None
        event.accept()
