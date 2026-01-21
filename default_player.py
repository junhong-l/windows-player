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
                
                # 设置图标 - 使用 exe 图标或 ico 文件
                with winreg.CreateKey(key, "DefaultIcon") as icon_key:
                    # 优先使用 exe 自带图标（打包后）
                    if getattr(sys, 'frozen', False):
                        # 打包后的 exe，使用 exe 文件本身的图标
                        winreg.SetValue(icon_key, "", winreg.REG_SZ, f'"{self.app_path}",0')
                    else:
                        # 开发环境，使用 ico 文件
                        winreg.SetValue(icon_key, "", winreg.REG_SZ, icon_path)
                
                # 设置打开命令
                with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                    winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{self.app_path}" "%1"')
            
            # 为每个扩展名注册 ProgID 和图标
            for ext in self.VIDEO_EXTENSIONS:
                # 注册扩展名关联
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                    f"Software\\Classes\\{ext}") as key:
                    winreg.SetValue(key, "", winreg.REG_SZ, self.prog_id)
                
                # 为每个扩展名单独注册图标（某些Windows版本需要）
                ext_prog_id = f"VideoPlayer{ext.upper().replace('.', '')}"
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                    f"Software\\Classes\\{ext_prog_id}") as key:
                    winreg.SetValue(key, "", winreg.REG_SZ, f"视频文件 ({ext})")
                    
                    with winreg.CreateKey(key, "DefaultIcon") as icon_key:
                        if getattr(sys, 'frozen', False):
                            winreg.SetValue(icon_key, "", winreg.REG_SZ, f'"{self.app_path}",0')
                        else:
                            winreg.SetValue(icon_key, "", winreg.REG_SZ, icon_path)
                    
                    with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                        winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{self.app_path}" "%1"')
            
            # 注册应用程序
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                f"Software\\Classes\\Applications\\{os.path.basename(self.app_path)}") as key:
                winreg.SetValueEx(key, "FriendlyAppName", 0, winreg.REG_SZ, "视频播放器")
                
                # 为应用程序设置图标
                with winreg.CreateKey(key, "DefaultIcon") as icon_key:
                    if getattr(sys, 'frozen', False):
                        winreg.SetValue(icon_key, "", winreg.REG_SZ, f'"{self.app_path}",0')
                    else:
                        winreg.SetValue(icon_key, "", winreg.REG_SZ, icon_path)
                
                with winreg.CreateKey(key, "shell\\open\\command") as cmd_key:
                    winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{self.app_path}" "%1"')
                
                # 支持的文件类型
                with winreg.CreateKey(key, "SupportedTypes") as types_key:
                    for ext in self.VIDEO_EXTENSIONS:
                        winreg.SetValueEx(types_key, ext, 0, winreg.REG_SZ, "")
            
            # 刷新图标缓存
            self._refresh_icon_cache()
            
            return True
        except Exception as e:
            print(f"注册文件类型失败: {e}")
            return False
    
    def _refresh_icon_cache(self):
        """刷新 Windows 图标缓存"""
        try:
            import ctypes
            # 通知 Shell 文件关联已更改
            SHCNE_ASSOCCHANGED = 0x08000000
            SHCNF_IDLIST = 0x0000
            ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        except:
            pass
    
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
