"""
默认播放器设置模块
用于检测和设置应用为默认视频播放器
"""
import os
import sys
import json
import winreg
import subprocess
from pathlib import Path


class DefaultPlayerManager:
    """默认播放器管理器"""
    
    # 支持的视频扩展名
    VIDEO_EXTENSIONS = [
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', 
        '.webm', '.m4v', '.mpeg', '.mpg', '.3gp'
    ]
    
    def __init__(self):
        self.app_path = self._get_app_path()
        self.app_name = "VideoPlayer"
        self.prog_id = "VideoPlayer.File"
        self.config_file = os.path.join(os.path.dirname(self.app_path), 'default_player.json')
    
    def _get_app_path(self) -> str:
        """获取应用程序路径"""
        if getattr(sys, 'frozen', False):
            # 打包后的 exe
            return sys.executable
        else:
            # 开发环境
            return os.path.abspath(sys.argv[0])
    
    def _load_config(self) -> dict:
        """加载配置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_config(self, config: dict):
        """保存配置"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except:
            pass
    
    def should_ask_default(self) -> bool:
        """是否应该询问用户设置默认播放器"""
        config = self._load_config()
        # 如果用户选择了"不再提示"，则不询问
        if config.get('never_ask', False):
            return False
        # 如果已经是默认播放器，不询问
        if self.is_default_player():
            return False
        return True
    
    def set_never_ask(self, value: bool = True):
        """设置不再询问"""
        config = self._load_config()
        config['never_ask'] = value
        self._save_config(config)
    
    def is_default_player(self) -> bool:
        """检查是否为默认视频播放器（检查 .mp4 关联）"""
        try:
            # 检查 .mp4 文件的默认程序
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                              r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.mp4\UserChoice") as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                return prog_id == self.prog_id
        except:
            return False
    
    def register_file_types(self) -> bool:
        """注册文件类型关联"""
        try:
            icon_path = os.path.join(os.path.dirname(self.app_path), 'icon.ico')
            
            # 注册 ProgID
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                f"Software\\Classes\\{self.prog_id}") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, "视频文件")
                
                # 设置图标
                with winreg.CreateKey(key, "DefaultIcon") as icon_key:
                    winreg.SetValue(icon_key, "", winreg.REG_SZ, f'"{icon_path}"')
                
                # 设置打开命令
                with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                    winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{self.app_path}" "%1"')
            
            # 为每个扩展名注册
            for ext in self.VIDEO_EXTENSIONS:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                    f"Software\\Classes\\{ext}") as key:
                    winreg.SetValue(key, "", winreg.REG_SZ, self.prog_id)
            
            # 注册应用程序
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                f"Software\\Classes\\Applications\\{os.path.basename(self.app_path)}") as key:
                winreg.SetValueEx(key, "FriendlyAppName", 0, winreg.REG_SZ, "视频播放器")
                
                with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                    winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{self.app_path}" "%1"')
                
                # 支持的文件类型
                with winreg.CreateKey(key, "SupportedTypes") as types_key:
                    for ext in self.VIDEO_EXTENSIONS:
                        winreg.SetValueEx(types_key, ext, 0, winreg.REG_SZ, "")
            
            return True
        except Exception as e:
            print(f"注册文件类型失败: {e}")
            return False
    
    def open_default_apps_settings(self):
        """打开 Windows 默认应用设置"""
        try:
            # Windows 10/11 打开默认应用设置
            subprocess.run(['start', 'ms-settings:defaultapps'], shell=True)
        except:
            try:
                # 备用方案：打开控制面板默认程序
                subprocess.run(['control', '/name', 'Microsoft.DefaultPrograms'], shell=True)
            except:
                pass
    
    def set_as_default(self) -> bool:
        """设置为默认播放器"""
        # 先注册文件类型
        if self.register_file_types():
            # 打开系统设置让用户确认
            self.open_default_apps_settings()
            return True
        return False


# 全局实例
default_player_manager = DefaultPlayerManager()
