"""
默认播放器设置模块
用于检测和设置应用为默认视频播放器
"""
import os
import sys
import json
import winreg
import subprocess
import hashlib
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
        self.last_error = ""
    
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
        """检查所有支持的视频格式的实际默认关联"""
        for extension in self.VIDEO_EXTENSIONS:
            prog_id = self._get_default_prog_id(extension)
            if prog_id not in (self.prog_id, f"VideoPlayer{extension[1:].upper()}"):
                return False
        return True

    def _get_default_prog_id(self, extension: str) -> str:
        try:
            import ctypes
            from ctypes import wintypes
            query = ctypes.windll.shlwapi.AssocQueryStringW
            query.argtypes = [
                wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR,
                wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
            ]
            query.restype = ctypes.c_long
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if query(0, 20, extension, None, buffer, ctypes.byref(length)) == 0:
                return buffer.value
        except (OSError, AttributeError):
            pass
        return ""
    
    def register_file_types(self) -> bool:
        """注册文件类型关联"""
        try:
            icon_path = os.path.join(os.path.dirname(self.app_path), 'icon.ico')
            open_command = f'"{self.app_path}" "%1"'
            if not getattr(sys, 'frozen', False):
                open_command = f'"{sys.executable}" "{self.app_path}" "%1"'
            
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
                    winreg.SetValue(cmd_key, "", winreg.REG_SZ, open_command)
            
            # 为每个扩展名注册 ProgID 和图标
            for ext in self.VIDEO_EXTENSIONS:
                # 注册扩展名关联
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 
                                    f"Software\\Classes\\{ext}\\OpenWithProgids") as key:
                    winreg.SetValueEx(key, self.prog_id, 0, winreg.REG_SZ, "")
                
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
                        winreg.SetValue(cmd_key, "", winreg.REG_SZ, open_command)
            
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
                    winreg.SetValue(cmd_key, "", winreg.REG_SZ, open_command)
                
                # 支持的文件类型
                with winreg.CreateKey(key, "SupportedTypes") as types_key:
                    for ext in self.VIDEO_EXTENSIONS:
                        winreg.SetValueEx(types_key, ext, 0, winreg.REG_SZ, "")
            
            capabilities_path = f"Software\\{self.app_name}\\Capabilities"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, capabilities_path) as key:
                winreg.SetValueEx(key, "ApplicationName", 0, winreg.REG_SZ, "视频播放器")
                winreg.SetValueEx(key, "ApplicationDescription", 0, winreg.REG_SZ, "视频播放器")
                with winreg.CreateKey(key, "FileAssociations") as associations_key:
                    for ext in self.VIDEO_EXTENSIONS:
                        winreg.SetValueEx(associations_key, ext, 0, winreg.REG_SZ, self.prog_id)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as key:
                winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, capabilities_path)

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
    
    def open_default_apps_settings(self) -> bool:
        """打开 Windows 默认应用设置"""
        try:
            os.startfile(f'ms-settings:defaultapps?registeredAppUser={self.app_name}')
            return True
        except OSError:
            try:
                os.startfile('ms-settings:defaultapps')
                return True
            except OSError:
                try:
                    subprocess.run(['control', '/name', 'Microsoft.DefaultPrograms'], check=True)
                    return True
                except (OSError, subprocess.CalledProcessError):
                    return False
    
    def set_as_default(self) -> bool:
        """设置为默认播放器"""
        self.last_error = ""
        if not self.register_file_types():
            self.last_error = "注册播放器失败"
            return False
        try:
            for extension in self.VIDEO_EXTENSIONS:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                      f"Software\\Classes\\{extension}") as key:
                    winreg.SetValue(key, "", winreg.REG_SZ, self.prog_id)
            self._refresh_icon_cache()
        except OSError as error:
            self.last_error = str(error)
            return False
        if self.is_default_player():
            return True
        return self._set_user_choice()

    def _set_user_choice(self) -> bool:
        resource_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        script_dir = resource_dir / 'third_party'
        source = script_dir / 'SFTA.ps1'
        runner = script_dir / 'set-default-player.ps1'
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
        try:
            expected_hash = '3eb6f6dee3fd8c91604042060b9d658f08ec85d3fd0a14769119dfd78bc30851'
            if hashlib.sha256(source.read_bytes()).hexdigest() != expected_hash:
                self.last_error = "关联组件完整性检查失败，请重新安装播放器"
                return False
            result = subprocess.run(
                [str(powershell), '-NoProfile', '-NonInteractive',
                 '-ExecutionPolicy', 'Bypass', '-File', str(runner),
                 '-ProgId', self.prog_id, '-Extensions', ','.join(self.VIDEO_EXTENSIONS)],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=120, creationflags=subprocess.CREATE_NO_WINDOW
            )
            self._refresh_icon_cache()
            pending = [extension for extension in self.VIDEO_EXTENSIONS
                       if self._get_default_prog_id(extension) != self.prog_id]
            if pending:
                self.last_error = "以下格式未设置成功：" + ", ".join(pending)
                details = (result.stderr or result.stdout).strip()
                if details:
                    self.last_error += "\n" + details[-2000:]
                return False
            return True
        except (OSError, subprocess.TimeoutExpired) as error:
            self.last_error = "无法运行文件关联组件：" + str(error)
            return False


# 全局实例
default_player_manager = DefaultPlayerManager()
