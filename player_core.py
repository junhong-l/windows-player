"""
视频播放器核心模块
基于 mpv 播放器
"""
import mpv
from typing import Callable, Optional


class PlayerCore:
    """MPV播放器核心封装类"""
    
    def __init__(self, wid: int = None):
        """
        初始化播放器
        Args:
            wid: 窗口ID，用于嵌入到GUI中
        """
        self.player = mpv.MPV(
            wid=wid,
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=False,  # 禁用默认OSC，使用自定义控制
            keep_open=True,
            idle=True,
        )
        
        # 播放设置
        self._skip_intro = 0  # 跳过片头时间（秒）
        self._skip_outro = 0  # 跳过片尾时间（秒）
        self._seek_step = 10  # 快进/快退步长（秒）
        self._speed = 1.0  # 播放速度
        
        # 回调函数
        self._on_position_changed: Optional[Callable] = None
        self._on_duration_changed: Optional[Callable] = None
        self._on_eof_reached: Optional[Callable] = None
        self._on_file_loaded: Optional[Callable] = None
        self._is_loading = False  # 标记是否正在加载新文件
        
        # 注册事件观察器
        self._setup_observers()
    
    def _setup_observers(self):
        """设置属性观察器"""
        @self.player.property_observer('time-pos')
        def time_observer(_name, value):
            if value is not None and self._on_position_changed:
                # 检查是否需要跳过片尾
                duration = self.duration
                if duration and self._skip_outro > 0 and not self._is_loading:
                    # 确保已经播放了至少10秒或10%，避免刚加载就触发
                    min_played = max(10, duration * 0.1)
                    if value >= min_played and value >= duration - self._skip_outro:
                        self.stop()
                        if self._on_eof_reached:
                            self._on_eof_reached()
                        return
                self._on_position_changed(value)
        
        @self.player.property_observer('duration')
        def duration_observer(_name, value):
            if value is not None and self._on_duration_changed:
                self._on_duration_changed(value)
        
        @self.player.event_callback('end-file')
        def eof_callback(event):
            # 只有在非加载状态时才触发（避免切换视频时误触发）
            if not self._is_loading and self._on_eof_reached:
                self._on_eof_reached()
        
        @self.player.event_callback('file-loaded')
        def file_loaded_callback(event):
            self._is_loading = False
            # 跳过片头
            if self._skip_intro > 0:
                self.seek_to(self._skip_intro)
            if self._on_file_loaded:
                self._on_file_loaded()
    
    # ========== 基本播放控制 ==========
    
    def load(self, filepath: str):
        """加载视频文件"""
        self._is_loading = True
        self.player.play(filepath)
    
    def play(self):
        """播放"""
        self.player.pause = False
    
    def pause(self):
        """暂停"""
        self.player.pause = True
    
    def toggle_pause(self):
        """切换播放/暂停状态"""
        self.player.pause = not self.player.pause
    
    def stop(self):
        """停止播放"""
        self.player.stop()
    
    @property
    def is_paused(self) -> bool:
        """是否暂停"""
        return self.player.pause
    
    @property
    def is_playing(self) -> bool:
        """是否正在播放"""
        return not self.player.pause and self.player.time_pos is not None
    
    # ========== 进度控制 ==========
    
    @property
    def position(self) -> float:
        """当前播放位置（秒）"""
        return self.player.time_pos or 0
    
    @property
    def duration(self) -> float:
        """视频总时长（秒）"""
        return self.player.duration or 0
    
    def seek_to(self, position: float):
        """跳转到指定位置"""
        self.player.seek(position, reference='absolute')
    
    def seek_forward(self):
        """快进"""
        self.player.seek(self._seek_step, reference='relative')
    
    def seek_backward(self):
        """快退"""
        self.player.seek(-self._seek_step, reference='relative')
    
    @property
    def seek_step(self) -> int:
        """快进/快退步长"""
        return self._seek_step
    
    @seek_step.setter
    def seek_step(self, value: int):
        """设置快进/快退步长"""
        self._seek_step = max(1, min(300, value))  # 限制在1-300秒
    
    # ========== 速度控制 ==========
    
    @property
    def speed(self) -> float:
        """播放速度"""
        return self._speed
    
    @speed.setter
    def speed(self, value: float):
        """设置播放速度（0.25-3.0）"""
        self._speed = max(0.25, min(3.0, value))
        self.player.speed = self._speed
    
    # ========== 跳过片头片尾 ==========
    
    @property
    def skip_intro(self) -> int:
        """跳过片头时间（秒）"""
        return self._skip_intro
    
    @skip_intro.setter
    def skip_intro(self, value: int):
        """设置跳过片头时间"""
        self._skip_intro = max(0, min(600, value))  # 最大10分钟
    
    @property
    def skip_outro(self) -> int:
        """跳过片尾时间（秒）"""
        return self._skip_outro
    
    @skip_outro.setter
    def skip_outro(self, value: int):
        """设置跳过片尾时间"""
        self._skip_outro = max(0, min(600, value))  # 最大10分钟
    
    # ========== 音量控制 ==========
    
    @property
    def volume(self) -> int:
        """音量（0-100）"""
        return int(self.player.volume or 100)
    
    @volume.setter
    def volume(self, value: int):
        """设置音量"""
        self.player.volume = max(0, min(100, value))
    
    @property
    def muted(self) -> bool:
        """是否静音"""
        return self.player.mute
    
    @muted.setter
    def muted(self, value: bool):
        """设置静音"""
        self.player.mute = value
    
# ========== 音轨控制 ==========

    def get_audio_tracks(self) -> list:
        """获取音轨列表
        返回: [{"id": int, "title": str, "lang": str, "selected": bool}, ...]
        """
        tracks = []
        try:
            track_list = self.player.track_list
            for track in track_list:
                if track.get('type') == 'audio':
                    tracks.append({
                        'id': track.get('id', 0),
                        'title': track.get('title', ''),
                        'lang': track.get('lang', ''),
                        'selected': track.get('selected', False)
                    })
        except:
            pass
        return tracks
    
    def set_audio_track(self, track_id: int):
        """设置当前音轨"""
        try:
            self.player.aid = track_id
        except:
            pass
    
    @property
    def current_audio_track(self) -> int:
        """获取当前音轨ID"""
        try:
            return self.player.aid or 1
        except:
            return 1

    # ========== 字幕控制 ==========

    def get_subtitle_tracks(self) -> list:
        """获取字幕轨道列表
        返回: [{"id": int, "title": str, "lang": str, "selected": bool, "external": bool}, ...]
        """
        tracks = []
        try:
            track_list = self.player.track_list
            for track in track_list:
                if track.get('type') == 'sub':
                    tracks.append({
                        'id': track.get('id', 0),
                        'title': track.get('title', ''),
                        'lang': track.get('lang', ''),
                        'selected': track.get('selected', False),
                        'external': track.get('external', False)
                    })
        except:
            pass
        return tracks
    
    def set_subtitle_track(self, track_id: int):
        """设置当前字幕轨道（0表示关闭字幕）"""
        try:
            if track_id == 0:
                self.player.sid = 'no'
            else:
                self.player.sid = track_id
        except:
            pass
    
    @property
    def current_subtitle_track(self) -> int:
        """获取当前字幕轨道ID（0表示无字幕）"""
        try:
            sid = self.player.sid
            if sid == 'no' or sid is False or sid is None:
                return 0
            return int(sid) if sid else 0
        except:
            return 0
    
    def load_external_subtitle(self, subtitle_path: str):
        """加载外部字幕文件"""
        try:
            self.player.sub_add(subtitle_path)
        except:
            pass
    
    @property
    def subtitle_delay(self) -> float:
        """获取字幕延迟（秒）"""
        try:
            return self.player.sub_delay or 0
        except:
            return 0
    
    @subtitle_delay.setter
    def subtitle_delay(self, value: float):
        """设置字幕延迟（正值表示字幕延后，负值表示字幕提前）"""
        try:
            self.player.sub_delay = value
        except:
            pass
    
    @property
    def subtitle_visibility(self) -> bool:
        """获取字幕可见性"""
        try:
            return self.player.sub_visibility
        except:
            return True
    
    @subtitle_visibility.setter
    def subtitle_visibility(self, value: bool):
        """设置字幕可见性"""
        try:
            self.player.sub_visibility = value
        except:
            pass

    # ========== 回调设置 ==========
    
    def set_position_callback(self, callback: Callable):
        """设置进度变化回调"""
        self._on_position_changed = callback
    
    def set_duration_callback(self, callback: Callable):
        """设置时长变化回调"""
        self._on_duration_changed = callback
    
    def set_eof_callback(self, callback: Callable):
        """设置播放结束回调"""
        self._on_eof_reached = callback
    
    def set_file_loaded_callback(self, callback: Callable):
        """设置文件加载完成回调"""
        self._on_file_loaded = callback
    
    # ========== 资源释放 ==========
    
    def terminate(self):
        """终止播放器"""
        self.player.terminate()
    
    def __del__(self):
        """析构函数"""
        try:
            self.terminate()
        except:
            pass
