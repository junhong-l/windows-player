"""
视频播放器主界面（精简美观版）
基于 PyQt6 + mpv
"""
import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QSpinBox,
    QDoubleSpinBox, QFrame, QSizePolicy, QMessageBox, QApplication,
    QDialog, QFormLayout, QMenu, QListWidget, QSplitter, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QAction, QKeySequence, QIcon
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
        self.setFixedSize(360, 260)
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 设置深色标题栏（Windows 10/11）
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
        
        self.setStyleSheet(
            """
            QDialog { background-color: #1a1a1a; color: #e0e0e0; font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }
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
            QPushButton#clearBtn {
                background: #444;
            }
            QPushButton#clearBtn:hover { background: #666; }
            """
        )
        self._build()

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

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("应用")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)
    
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
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 设置深色标题栏（Windows 10/11）
        self._set_dark_titlebar()

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
        self._folder_files = []  # 文件夹中的视频文件列表
        self._current_index = -1  # 当前播放的文件索引
        self._is_seeking = False
        self._is_fullscreen = False
        self._controls_visible = True
        self._mouse_in_control_area = False
        self._hide_delay_ms = 2500
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_controls)
        
        # 连接视频结束信号（用于跨线程）
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
    
    def _set_dark_titlebar(self):
        """设置深色标题栏（Windows 10/11）"""
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

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #000; }
            QWidget { background-color: transparent; color: #fff; font-family: "Microsoft YaHei", "Segoe UI", sans-serif; }
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
        self.setCentralWidget(central)
        self.setMouseTracking(True)
        central.setMouseTracking(True)
        self.video_widget.setMouseTracking(True)
        
        # 使用 stacked widget 切换欢迎页和播放页
        from PyQt6.QtWidgets import QStackedWidget
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setMouseTracking(True)
        
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
        
        self.stacked_widget.addWidget(self.welcome_page)
        
        # ===== 播放页 =====
        self.player_page = QWidget()
        self.player_page.setMouseTracking(True)
        player_layout = QVBoxLayout(self.player_page)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.setSpacing(0)
        
        # 视频区域
        player_layout.addWidget(self.video_widget, 1)
        
        self.stacked_widget.addWidget(self.player_page)
        
        # 播放列表悬浮面板（作为 central widget 的子组件）
        self.playlist_widget.setParent(central)
        self.playlist_widget.hide()
        
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
        self.skip_intro_btn = self._mk_text_btn("片头 0s", "跳过片头（点击设置）")
        self.skip_intro_btn.clicked.connect(self._set_skip_intro)
        btn_row.addWidget(self.skip_intro_btn)
        
        self.skip_outro_btn = self._mk_text_btn("片尾 0s", "跳过片尾（点击设置）")
        self.skip_outro_btn.clicked.connect(self._set_skip_outro)
        btn_row.addWidget(self.skip_outro_btn)
        
        self.list_btn = self._mk_icon_btn("fa5s.list", "播放列表")
        self.list_btn.clicked.connect(self._show_playlist)
        btn_row.addWidget(self.list_btn)
        
        self.speed_btn = self._mk_text_btn("倍速", "播放速度")
        self.speed_btn.clicked.connect(self._show_speed_menu)
        btn_row.addWidget(self.speed_btn)
        
        self.audio_btn = self._mk_text_btn("音轨", "选择音轨")
        self.audio_btn.clicked.connect(self._show_audio_menu)
        btn_row.addWidget(self.audio_btn)

        self.settings_btn = self._mk_icon_btn("fa5s.cog", "设置")
        self.settings_btn.clicked.connect(self._show_settings)
        btn_row.addWidget(self.settings_btn)

        self.mute_btn = self._mk_icon_btn("fa5s.volume-up", "静音")
        self.mute_btn.clicked.connect(self._toggle_mute)
        btn_row.addWidget(self.mute_btn)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(80)
        self.volume_slider.setFixedHeight(20)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        btn_row.addWidget(self.volume_slider)

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
        
        # 更新UI显示
        self.speed_btn.setText(f"{g_settings.speed}x" if g_settings.speed != 1.0 else "倍速")
        self.skip_intro_btn.setText(f"片头 {f_settings.skip_intro}s" if f_settings.skip_intro > 0 else "片头")
        self.skip_outro_btn.setText(f"片尾 {f_settings.skip_outro}s" if f_settings.skip_outro > 0 else "片尾")
        
        # 更新播放列表当前项
        if self._folder_files:
            self.playlist_widget.update_current(self._current_index, self._folder_files)
        
        self.player.load(file_path)
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

    def _stop(self):
        if self.player:
            # 保存播放进度
            self._save_current_progress()
            self.player.stop()
            self.play_btn.setIcon(qta.icon('fa5s.play', color='#ffffff'))
            self.progress_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")
    
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
            self.speed_btn.setText(f"{speed}x" if speed != 1.0 else "倍速")
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
            # 更新按钮显示
            for track in tracks:
                if track['id'] == track_id:
                    lang = track['lang'] or ""
                    self.audio_btn.setText(f"音轨 {lang}" if lang else "音轨")
                    break

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
                self.speed_btn.setText(f"{speed}x" if speed != 1.0 else "倍速")
    
    def _set_skip_intro(self):
        """设置跳过片头时间 - 默认值为当前播放位置"""
        if not self._current_file or not self.player:
            return
        
        from PyQt6.QtWidgets import QInputDialog
        # 获取当前播放位置作为默认值
        current_pos = int(self.player.position) if self.player.position else 0
        value, ok = QInputDialog.getInt(
            self, "跳过片头", 
            "设置跳过片头秒数（针对当前文件夹）：\n当前位置已自动填入",
            current_pos, 0, 600, 1
        )
        if ok:
            self.player.skip_intro = value
            folder_settings.update_settings(self._current_file, skip_intro=value)
            self.skip_intro_btn.setText(f"片头 {value}s" if value > 0 else "片头")
    
    def _set_skip_outro(self):
        """设置跳过片尾时间 - 默认值为距离视频结尾的时间"""
        if not self._current_file or not self.player:
            return
        
        from PyQt6.QtWidgets import QInputDialog
        # 获取距离视频结尾的时间作为默认值
        duration = self.player.duration or 0
        current_pos = self.player.position or 0
        time_to_end = int(duration - current_pos) if duration > current_pos else 0
        value, ok = QInputDialog.getInt(
            self, "跳过片尾", 
            "设置跳过片尾秒数（针对当前文件夹）：\n距结尾时间已自动填入",
            time_to_end, 0, 600, 1
        )
        if ok:
            self.player.skip_outro = value
            folder_settings.update_settings(self._current_file, skip_outro=value)
            self.skip_outro_btn.setText(f"片尾 {value}s" if value > 0 else "片尾")

    # ========== 全屏 ========== #

    def _toggle_fullscreen(self):
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        self._is_fullscreen = True
        self.showFullScreen()
        self.full_btn.setIcon(qta.icon('fa5s.compress', color='#ffffff'))
        self._maybe_start_hide_timer()

    def _exit_fullscreen(self):
        if self._is_fullscreen:
            self._is_fullscreen = False
            self.showNormal()
            self.full_btn.setIcon(qta.icon('fa5s.expand', color='#ffffff'))
            self._show_controls(persist=True)

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

    def resizeEvent(self, event):
        """窗口大小改变时更新控制栏和播放列表位置"""
        super().resizeEvent(event)
        self._update_control_bar_geometry()
        self._update_playlist_geometry()
    
    def _update_control_bar_geometry(self):
        """更新控制栏位置和大小"""
        # 控制栏覆盖整个底部
        self.control_widget.setGeometry(
            0, 
            self.centralWidget().height() - 50, 
            self.centralWidget().width(), 
            50
        )
    
    def _update_playlist_geometry(self):
        """更新播放列表位置（右侧悬浮）"""
        if self.playlist_widget.isVisible():
            # 定位到右侧，距离底部留出控制栏空间
            x = self.centralWidget().width() - self.playlist_widget.width() - 10
            y = 10
            self.playlist_widget.move(x, y)
            self.playlist_widget.raise_()

    def closeEvent(self, event):
        # 保存播放进度
        self._save_current_progress()
        if self.player:
            self.player.terminate()
        event.accept()
