"""
播放设置管理
- 全局设置：播放速度、快进步长
- 文件夹设置：跳过片头、跳过片尾、播放进度
所有设置都保存在程序目录
"""
import os
import sys
import json
import hashlib
from dataclasses import dataclass, asdict
from typing import Optional


# 程序目录（兼容 PyInstaller 打包）
if getattr(sys, 'frozen', False):
    # 打包后，使用 exe 所在目录
    APP_DIR = os.path.dirname(sys.executable)
else:
    # 开发时，使用脚本所在目录
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

# 设置目录
SETTINGS_DIR = os.path.join(APP_DIR, "settings")


def ensure_settings_dir():
    """确保设置目录存在"""
    if not os.path.exists(SETTINGS_DIR):
        os.makedirs(SETTINGS_DIR)


def get_folder_id(folder_path: str) -> str:
    """根据文件夹路径生成唯一ID"""
    # 使用 MD5 哈希生成短 ID
    return hashlib.md5(folder_path.encode('utf-8')).hexdigest()[:16]


@dataclass
class GlobalSettings:
    """全局设置（应用级别）"""
    speed: float = 1.0
    seek_step: int = 10

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GlobalSettings":
        return cls(
            speed=data.get("speed", 1.0),
            seek_step=data.get("seek_step", 10),
        )


@dataclass
class FolderPlaySettings:
    """文件夹设置（针对视频文件夹）"""
    folder_path: str = ""  # 原始文件夹路径
    skip_intro: int = 0
    skip_outro: int = 0
    progress: dict = None  # 每个文件的播放进度 {filename: percentage}

    def __post_init__(self):
        if self.progress is None:
            self.progress = {}

    def to_dict(self) -> dict:
        return {
            "folder_path": self.folder_path,
            "skip_intro": self.skip_intro,
            "skip_outro": self.skip_outro,
            "progress": self.progress
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FolderPlaySettings":
        return cls(
            folder_path=data.get("folder_path", ""),
            skip_intro=data.get("skip_intro", 0),
            skip_outro=data.get("skip_outro", 0),
            progress=data.get("progress", {}),
        )


class GlobalSettingsManager:
    """全局设置管理器"""
    
    SETTINGS_FILE = "global_settings.json"
    
    def __init__(self):
        self._settings: GlobalSettings | None = None
        # 保存在 settings 目录中
        ensure_settings_dir()
        self._settings_path = os.path.join(SETTINGS_DIR, self.SETTINGS_FILE)
        
        # 兼容旧版本：如果旧位置有配置文件，迁移到新位置
        old_path = os.path.join(APP_DIR, self.SETTINGS_FILE)
        if os.path.exists(old_path) and not os.path.exists(self._settings_path):
            try:
                import shutil
                shutil.move(old_path, self._settings_path)
            except:
                pass
    
    def load(self) -> GlobalSettings:
        """加载全局设置"""
        if self._settings:
            return self._settings
        
        if os.path.exists(self._settings_path):
            try:
                with open(self._settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._settings = GlobalSettings.from_dict(data)
            except (json.JSONDecodeError, IOError):
                self._settings = GlobalSettings()
        else:
            self._settings = GlobalSettings()
        
        return self._settings
    
    def save(self, settings: GlobalSettings) -> None:
        """保存全局设置"""
        try:
            with open(self._settings_path, "w", encoding="utf-8") as f:
                json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)
            self._settings = settings
        except IOError as e:
            print(f"保存全局设置失败: {e}")
    
    def update(self, **kwargs) -> GlobalSettings:
        """更新并保存设置"""
        settings = self.load()
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        self.save(settings)
        return settings


class FolderSettingsManager:
    """文件夹设置管理器 - 所有设置保存在程序目录"""
    
    def __init__(self):
        self._cache: dict[str, FolderPlaySettings] = {}
        ensure_settings_dir()
    
    def _get_settings_path(self, folder_path: str) -> str:
        """获取设置文件路径（保存在程序目录的 settings 文件夹中）"""
        folder_id = get_folder_id(folder_path)
        return os.path.join(SETTINGS_DIR, f"folder_{folder_id}.json")
    
    def get_folder_path(self, file_path: str) -> str:
        """从文件路径获取文件夹路径"""
        return os.path.dirname(os.path.abspath(file_path))
    
    def load_settings(self, file_path: str) -> FolderPlaySettings:
        """加载文件所在文件夹的设置"""
        folder_path = self.get_folder_path(file_path)
        
        # 检查缓存
        if folder_path in self._cache:
            return self._cache[folder_path]
        
        settings_path = self._get_settings_path(folder_path)
        
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    settings = FolderPlaySettings.from_dict(data)
            except (json.JSONDecodeError, IOError):
                settings = FolderPlaySettings(folder_path=folder_path)
        else:
            settings = FolderPlaySettings(folder_path=folder_path)
        
        self._cache[folder_path] = settings
        return settings
    
    def save_settings(self, file_path: str, settings: FolderPlaySettings) -> None:
        """保存设置到程序目录"""
        folder_path = self.get_folder_path(file_path)
        settings_path = self._get_settings_path(folder_path)
        settings.folder_path = folder_path
        
        try:
            ensure_settings_dir()
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings.to_dict(), f, indent=2, ensure_ascii=False)
            self._cache[folder_path] = settings
        except IOError as e:
            print(f"保存设置失败: {e}")
    
    def update_settings(self, file_path: str, **kwargs) -> FolderPlaySettings:
        """更新并保存设置"""
        settings = self.load_settings(file_path)
        
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        self.save_settings(file_path, settings)
        return settings
    
    def save_progress(self, file_path: str, percentage: float) -> None:
        """保存单个文件的播放进度"""
        filename = os.path.basename(file_path)
        settings = self.load_settings(file_path)
        settings.progress[filename] = round(percentage, 1)
        self.save_settings(file_path, settings)
    
    def get_progress(self, file_path: str) -> float:
        """获取单个文件的播放进度（百分比）"""
        filename = os.path.basename(file_path)
        settings = self.load_settings(file_path)
        return settings.progress.get(filename, 0)
    
    def get_all_progress(self, folder_path: str) -> dict:
        """获取文件夹中所有文件的播放进度"""
        # 标准化路径，确保哈希一致
        folder_path = os.path.abspath(folder_path)
        settings_path = self._get_settings_path(folder_path)
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("progress", {})
            except:
                pass
        return {}
    
    def clear_all_settings(self) -> int:
        """清理所有文件夹设置
        返回: 清理的文件数量
        """
        count = 0
        if os.path.exists(SETTINGS_DIR):
            for filename in os.listdir(SETTINGS_DIR):
                if filename.startswith("folder_") and filename.endswith(".json"):
                    try:
                        os.remove(os.path.join(SETTINGS_DIR, filename))
                        count += 1
                    except IOError:
                        pass
        # 清空缓存
        self._cache.clear()
        return count


# 全局实例
global_settings = GlobalSettingsManager()
folder_settings = FolderSettingsManager()
