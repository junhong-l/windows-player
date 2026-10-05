import os
import sys

import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, QSize, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSlider, QSizePolicy, QCheckBox, QApplication, QInputDialog, QComboBox,
)


class CastDialog(QDialog):
    def __init__(self, manager, get_media, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.get_media = get_media
        self._state = {}
        self._last_error = ''
        self._manual_location = ''
        self._selected_device_protocol = None
        self.setWindowTitle("投屏（DLNA / AirPlay）")
        self.setMinimumSize(460, 550)
        self.resize(520, 600)
        self.setStyleSheet("""
            QDialog { background: #1a1a1a; }
            QLabel { color: #e0e0e0; font-size: 13px; }
            QCheckBox { color: #e0e0e0; font-size: 13px; }
            QComboBox { color: #e0e0e0; background: #222; border: 1px solid #444; padding: 5px 8px; }
            QComboBox QAbstractItemView { color: #e0e0e0; background: #222; selection-background-color: #006b8f; }
            QComboBox QLineEdit { color: #e0e0e0; background: transparent; border: none; }
            QComboBox QLineEdit:disabled { color: #888; }
            QListWidget { background: #222; border: 1px solid #444; }
            QListWidget::item { padding: 10px; }
            QListWidget::item:selected { background: #006b8f; }
            QPushButton { padding: 7px 12px; background: #333; border: none; border-radius: 4px; }
            QPushButton:hover { background: #444; }
            QPushButton:disabled { color: #777; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        self.file_label = QLabel()
        self.file_label.setFixedHeight(24)
        self.file_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.file_label)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("设备"))
        search_row.addStretch()
        self.debug_checkbox = QCheckBox("调试日志")
        self.debug_checkbox.setChecked('--debug' in sys.argv or os.environ.get('VIDEO_PLAYER_DEBUG') == '1')
        self.debug_checkbox.toggled.connect(manager.set_debug)
        manager.set_debug(self.debug_checkbox.isChecked())
        search_row.addWidget(self.debug_checkbox)
        self.log_btn = self._icon_button('fa5s.file-alt', "打开运行日志")
        self.log_btn.clicked.connect(self._open_log)
        search_row.addWidget(self.log_btn)
        self.copy_error_btn = self._icon_button('fa5s.copy', "复制完整错误")
        self.copy_error_btn.setEnabled(False)
        self.copy_error_btn.clicked.connect(self._copy_error)
        search_row.addWidget(self.copy_error_btn)
        self.add_device_btn = self._icon_button('fa5s.plus', "按 DLNA 描述地址或 AirPlay 地址添加")
        self.add_device_btn.clicked.connect(self._add_device)
        search_row.addWidget(self.add_device_btn)
        self.refresh_btn = self._icon_button('fa5s.sync-alt', "搜索设备")
        self.refresh_btn.setToolTip("搜索同一局域网中的 DLNA 和旧版 AirPlay 视频接收设备")
        self.refresh_btn.clicked.connect(self._search)
        search_row.addWidget(self.refresh_btn)
        layout.addLayout(search_row)
        self.device_list = QListWidget()
        self.device_list.setMinimumHeight(120)
        self.device_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.device_list.itemSelectionChanged.connect(self._on_device_selection)
        self.device_list.itemDoubleClicked.connect(lambda item: self._start())
        layout.addWidget(self.device_list, 1)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("投屏画质"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("720p（兼容）", 720)
        self.quality_combo.addItem("1080p（兼容）", 1080)
        self.quality_combo.addItem("2K（1440p）", 1440)
        self.quality_combo.addItem("4K（2160p）", 2160)
        self.quality_combo.addItem("原画（直传）", None)
        self.quality_combo.setToolTip("兼容模式转为 H.264 8-bit、30fps、AAC 双声道；4K 上限为 3840×2160，需接收设备支持 H.264 Level 5.1")
        quality_row.addWidget(self.quality_combo, 1)
        self.delivery_combo = QComboBox()
        self.delivery_combo.addItem("实时（边转边播）", 'stream')
        self.delivery_combo.addItem("完整缓存（备用）", 'file')
        self.delivery_combo.setToolTip("实时模式发送 MPEG-TS 流；不支持时可手动改用完整 MP4 缓存")
        quality_row.addWidget(self.delivery_combo, 1)
        self.quality_combo.currentIndexChanged.connect(self._refresh_controls)
        self.delivery_combo.currentIndexChanged.connect(self._refresh_controls)
        layout.addLayout(quality_row)

        encoder_row = QHBoxLayout()
        encoder_row.addWidget(QLabel("编码器"))
        self.encoder_combo = QComboBox()
        self.encoder_combo.addItem("自动（GPU 优先）", 'auto')
        self.encoder_combo.addItem("CPU（软件编码）", 'cpu')
        self.encoder_combo.setToolTip("仅显示通过驱动试编码的 GPU；解码和缩放仍使用 CPU")
        encoder_row.addWidget(self.encoder_combo, 1)
        self.encoder_status = QLabel("检测中…")
        encoder_row.addWidget(self.encoder_status)
        layout.addLayout(encoder_row)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("投屏倍速"))
        self.speed_combo = QComboBox()
        for speed in (0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3):
            self.speed_combo.addItem(f'{speed:g}x', speed)
        self.speed_combo.setCurrentIndex(self.speed_combo.findData(1))
        self.speed_combo.currentIndexChanged.connect(self._change_speed)
        speed_row.addWidget(self.speed_combo, 1)
        layout.addLayout(speed_row)

        connect_row = QHBoxLayout()
        self.status_label = QLabel("等待搜索")
        self.status_label.setWordWrap(True)
        self.status_label.setMaximumHeight(52)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        connect_row.addWidget(self.status_label, 1)
        self.connect_btn = QPushButton(qta.icon('fa5s.tv', color='#ffffff'), "投屏")
        self.connect_btn.setFixedWidth(90)
        self.connect_btn.clicked.connect(self._start)
        connect_row.addWidget(self.connect_btn)
        layout.addLayout(connect_row)

        self.session_label = QLabel("未连接")
        self.session_label.setFixedHeight(44)
        self.session_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.session_label.setTextFormat(Qt.TextFormat.PlainText)
        session_row = QHBoxLayout()
        session_row.addWidget(self.session_label, 1)
        self.rate_label = QLabel("推送 0.00 Mbps")
        self.rate_label.setFixedWidth(150)
        self.rate_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.rate_label.setToolTip("最近 1 秒向 HTTP 连接写入的视频数据速率；不含协议开销，不代表接收端已播放或网络带宽上限")
        session_row.addWidget(self.rate_label)
        layout.addLayout(session_row)
        self.progress = QSlider(Qt.Orientation.Horizontal)
        self.progress.setRange(0, 1000)
        self.progress.sliderReleased.connect(self._seek)
        layout.addWidget(self.progress)
        control_row = QHBoxLayout()
        self.play_btn = self._icon_button('fa5s.play', "播放/暂停")
        self.play_btn.clicked.connect(self._toggle_play)
        control_row.addWidget(self.play_btn)
        self.stop_btn = self._icon_button('fa5s.stop', "停止投屏")
        self.stop_btn.clicked.connect(self._stop)
        control_row.addWidget(self.stop_btn)
        self.sync_btn = self._icon_button('fa5s.sync-alt', "同步设备状态和进度")
        self.sync_btn.clicked.connect(manager.update)
        control_row.addWidget(self.sync_btn)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(112)
        control_row.addWidget(self.time_label)
        control_row.addStretch()
        self.volume_btn = self._icon_button('fa5s.volume-up', "静音/恢复音量")
        self.volume_btn.clicked.connect(self._toggle_mute)
        control_row.addWidget(self.volume_btn)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(50)
        self.volume.setFixedWidth(100)
        self.volume.setToolTip("设备音量")
        self.volume.valueChanged.connect(self._schedule_volume)
        control_row.addWidget(self.volume)
        layout.addLayout(control_row)

        self._previous_volume = 50
        self._volume_timer = QTimer(self)
        self._volume_timer.setSingleShot(True)
        self._volume_timer.timeout.connect(self._set_volume)
        manager.devicesFound.connect(self._on_devices)
        manager.sessionChanged.connect(self._on_state)
        manager.started.connect(self._on_started)
        manager.stopped.connect(self._on_stopped)
        manager.failed.connect(self._on_error)
        manager.stageChanged.connect(self._on_stage)
        manager.encodersFound.connect(self._on_encoders)
        manager.busyChanged.connect(self._refresh_controls)
        self.refresh_context()
        self._refresh_controls()
        QTimer.singleShot(0, self._search)
        QTimer.singleShot(0, manager.scan_encoders)

    def _icon_button(self, name, tooltip):
        button = QPushButton(qta.icon(name, color='#ffffff'), "")
        button.setFixedSize(32, 32)
        button.setIconSize(QSize(16, 16))
        button.setToolTip(tooltip)
        return button

    def refresh_context(self):
        path, *_ = self.get_media()
        self.file_label.setText(self._elide(os.path.basename(path)) if path else "未打开视频")
        self.file_label.setToolTip(path or "")

    def _elide(self, text, width=None):
        return self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle,
                                            max(0, self.width() - 36 if width is None else width))

    def _refresh_session_label(self):
        if self.manager.connected:
            self.session_label.setText(self._elide(self.manager.device.name, self.session_label.width()) + "\n" +
                                       self._elide(os.path.basename(self.manager.file_path), self.session_label.width()))
            self.session_label.setToolTip(self.manager.device.name + "\n" + self.manager.file_path)
        else:
            self.session_label.setText("未连接")
            self.session_label.setToolTip("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'session_label'):
            self.refresh_context()
            self._refresh_session_label()

    def _search(self):
        if self.manager.search():
            self.status_label.setText("正在搜索…")

    def _add_device(self):
        location, accepted = QInputDialog.getText(
            self, "添加投屏设备", "DLNA 描述地址 / AirPlay 地址（airplay://IP:端口）", text=self._manual_location
        )
        if accepted and location.strip() and self.manager.add_device(location):
            self._manual_location = location.strip()
            self.status_label.setText("正在读取设备信息…")

    def _on_devices(self, devices):
        current = self.device_list.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole).udn if current else None
        self.device_list.clear()
        for device in devices:
            protocol = 'AirPlay' if device.protocol == 'airplay' else 'DLNA'
            item = QListWidgetItem(qta.icon('fa5s.tv', color='#ffffff'), f"{device.name}\n{device.host}  |  {protocol}")
            item.setToolTip(device.name + "\n" + device.host)
            item.setData(Qt.ItemDataRole.UserRole, device)
            self.device_list.addItem(item)
            if device.udn == selected:
                self.device_list.setCurrentItem(item)
        if not self.device_list.selectedItems() and devices:
            self.device_list.setCurrentRow(0)
        self.status_label.setText(f"发现 {len(devices)} 台设备" if devices else "未发现设备")
        self.status_label.setToolTip("请打开电视的投屏接收页面，并与电脑处于同一局域网；防火墙需允许局域网访问")
        self._refresh_controls()

    def _on_device_selection(self):
        item = self.device_list.currentItem()
        if item is not None:
            protocol = item.data(Qt.ItemDataRole.UserRole).protocol
            if protocol != self._selected_device_protocol:
                self._selected_device_protocol = protocol
                self.quality_combo.setCurrentIndex(self.quality_combo.findData(None if protocol == 'airplay' else 720))
                self.delivery_combo.setCurrentIndex(self.delivery_combo.findData('stream'))
        self._refresh_controls()

    def _on_encoders(self, available):
        selected = self.encoder_combo.currentData()
        self.encoder_combo.clear()
        self.encoder_combo.addItem("自动（GPU 优先）", 'auto')
        names = {'nvenc': 'NVIDIA NVENC', 'amf': 'AMD AMF', 'qsv': 'Intel QSV'}
        for encoder, name in names.items():
            if encoder in available:
                self.encoder_combo.addItem(name, encoder)
        self.encoder_combo.addItem("CPU（软件编码）", 'cpu')
        index = self.encoder_combo.findData(selected)
        self.encoder_combo.setCurrentIndex(max(0, index))
        self.encoder_status.setText("GPU 可用" if any(encoder in available for encoder in names) else "仅 CPU")
        self.encoder_status.setToolTip(" / ".join(names[encoder] for encoder in names if encoder in available))
        self._refresh_controls()

    def _start(self):
        item = self.device_list.currentItem()
        path, position, *details = self.get_media()
        if not path or not os.path.isfile(path):
            self._on_error("请先打开本地视频")
            return
        if item and self.manager.start(item.data(Qt.ItemDataRole.UserRole), path, position,
                                       resolution=self.quality_combo.currentData(),
                                       delivery=self.delivery_combo.currentData(), duration=details[0] if details else 0,
                                       encoder=self.encoder_combo.currentData(), speed=self.speed_combo.currentData()):
            self.status_label.setText("正在连接…")

    def _stop(self):
        if self.manager.busy and not self.manager.connected:
            if self.manager.cancel():
                self.status_label.setText("正在取消…")
        else:
            self.manager.command('stop')

    def _on_started(self, session):
        self.status_label.setText("已连接")
        self._refresh_session_label()
        self._refresh_controls()

    @staticmethod
    def _time(seconds):
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'

    def _on_state(self, state):
        self._state = state
        self.rate_label.setText(f"推送 {state.get('transfer_mbps', 0):.2f} Mbps")
        self._set_speed(state.get('speed', 1))
        position, duration = state['position'], state['duration']
        self.time_label.setText(f"{self._time(position)} / {self._time(duration)}")
        if not self.progress.isSliderDown():
            self.progress.setValue(int(position / duration * 1000) if duration else 0)
        if state['volume'] is not None and not self.volume.isSliderDown() and not self._volume_timer.isActive():
            self.volume.blockSignals(True)
            self.volume.setValue(round(state['volume'] * 100))
            self.volume.blockSignals(False)
        playing = state['state'] == 'PLAYING'
        self.play_btn.setIcon(qta.icon('fa5s.pause' if playing else 'fa5s.play', color='#ffffff'))
        self.volume_btn.setIcon(qta.icon('fa5s.volume-mute' if self.volume.value() == 0 else 'fa5s.volume-up', color='#ffffff'))
        labels = {'PLAYING': '正在播放', 'PAUSED_PLAYBACK': '已暂停',
                  'STOPPED': '已停止', 'TRANSITIONING': '正在加载', 'NO_MEDIA_PRESENT': '无媒体'}
        sync_mode = "推送" if state.get('status_sync') == 'events' else "手动同步"
        self.status_label.setText(labels.get(state['state'], "已连接") + f"（{sync_mode}）")
        self.progress.setToolTip("本地估算进度；点击同步按钮可读取设备实际进度" if state.get('position_estimated') else "设备报告的播放进度")
        self._refresh_controls()

    def _on_stopped(self, previous):
        self._state = {}
        self._volume_timer.stop()
        self.session_label.setText("未连接")
        self.status_label.setText("投屏已停止")
        self.rate_label.setText("推送 0.00 Mbps")
        self.progress.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self._refresh_controls()

    def _on_error(self, message):
        self._last_error = message
        self.copy_error_btn.setEnabled(True)
        self.status_label.setText(message if message == '已取消投屏' else "操作失败：" + message[:250])
        self.status_label.setToolTip(message)

    def _on_stage(self, stage):
        if self.manager.busy:
            self.status_label.setText(stage + "…")

    def _open_log(self):
        path = self.manager.log_path
        if not path or not os.path.isfile(path):
            self._on_error("未找到运行日志，请通过主程序启动播放器")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            self._on_error("无法打开运行日志：" + path)

    def _copy_error(self):
        QApplication.clipboard().setText(self._last_error)

    def _refresh_controls(self, *args):
        available = not self.manager.busy
        connected = self.manager.connected
        item = self.device_list.currentItem()
        airplay = item is not None and item.data(Qt.ItemDataRole.UserRole).protocol == 'airplay'
        self.delivery_combo.setToolTip("AirPlay 实时模式使用 HLS 分段转码；不支持时可手动选择完整 MP4 缓存" if airplay
                                       else "实时模式发送 MPEG-TS 流；不支持时可手动改用完整 MP4 缓存")
        self.refresh_btn.setEnabled(available)
        self.add_device_btn.setEnabled(available and not connected)
        self.device_list.setEnabled(available and not connected)
        self.connect_btn.setEnabled(available and not connected and self.device_list.currentItem() is not None)
        self.quality_combo.setEnabled(available and not connected)
        self.delivery_combo.setEnabled(available and not connected and self.quality_combo.currentData() is not None)
        self.encoder_combo.setEnabled(available and not connected and self.quality_combo.currentData() is not None)
        compatible = self.quality_combo.currentData() is not None
        self.delivery_combo.setItemText(self.delivery_combo.findData('stream'), "实时（边转边播）" if compatible else "原文件直传")
        self.delivery_combo.setItemText(self.delivery_combo.findData('file'), "完整缓存（备用）" if compatible else "原文件直传")
        if not compatible:
            self._set_speed(1)
        self.speed_combo.setEnabled(available and compatible and (not connected or self._state.get('can_speed', False)))
        for combo in (self.delivery_combo, self.encoder_combo, self.speed_combo):
            combo.setEditable(not compatible)
            if not compatible:
                combo.lineEdit().setReadOnly(True)
                combo.lineEdit().setText("此模式不可修改")
        self.encoder_status.setVisible(compatible)
        if not compatible:
            self.speed_combo.setToolTip("当前原画投屏不支持倍速控制；选择兼容画质后可通过转码设置倍速")
        else:
            self.speed_combo.setToolTip("实时投屏切换倍速会从当前进度重建视频流；音频保持音调" if self.delivery_combo.currentData() == 'stream'
                                       else "完整缓存可在投屏前选择倍速；播放中需停止后重新选择")
        self.stop_btn.setEnabled((available and connected) or (self.manager.busy and not connected))
        self.sync_btn.setEnabled(available and connected)
        self.stop_btn.setToolTip("取消投屏准备" if self.manager.busy and not connected else "停止投屏")
        self.play_btn.setEnabled(available and connected and
                                (self._state.get('can_pause', False) or self._state.get('state') != 'PLAYING'))
        self.progress.setEnabled(available and connected and self._state.get('can_seek', False)
                                 and self._state.get('duration', 0) > 0)
        self.volume.setEnabled(available and connected and self._state.get('can_volume', False))
        self.volume_btn.setEnabled(self.volume.isEnabled())

    def _set_speed(self, speed):
        index = self.speed_combo.findData(speed)
        if index >= 0:
            self.speed_combo.blockSignals(True)
            self.speed_combo.setCurrentIndex(index)
            self.speed_combo.blockSignals(False)

    def _change_speed(self):
        if self.manager.connected:
            if not self.manager.command('speed', self.speed_combo.currentData()):
                self._set_speed(self._state.get('speed', 1))

    def _toggle_play(self):
        self.manager.command('pause' if self._state.get('state') == 'PLAYING' else 'play')

    def _seek(self):
        duration = self._state.get('duration', 0)
        if duration:
            self.manager.command('seek', duration * self.progress.value() / 1000)

    def _schedule_volume(self, value):
        self._volume_timer.start(300)

    def _set_volume(self):
        if not self.manager.connected:
            return
        if not self.manager.command('volume', self.volume.value() / 100):
            self._volume_timer.start(300)

    def _toggle_mute(self):
        if self.volume.value() > 0:
            self._previous_volume = self.volume.value()
            self.volume.setValue(0)
        else:
            self.volume.setValue(self._previous_volume or 50)