; 视频播放器 - Inno Setup 安装脚本
; 使用 Inno Setup 6 编译：https://jrsoftware.org/isinfo.php
; 编译前请先运行 python build.py 生成 dist\视频播放器\ 目录

#define MyAppName "视频播放器"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "Player"
#define MyAppExeName "视频播放器.exe"
#define MyAppID "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"

[Setup]
; 应用程序标识符（请勿更改，用于检测已安装版本）
AppId={{{#MyAppID}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}

; 安装目录：默认装到用户 AppData\Local\Programs\（不需要 UAC 权限）
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
; 允许用户修改安装目录
DisableDirPage=no
; 不强制要求管理员权限
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 输出配置
OutputDir=dist
OutputBaseFilename=视频播放器_安装包_v{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
; 安装程序图标
SetupIconFile=icon.ico

; 显示设置
WizardStyle=modern
WizardSizePercent=120
; 版本信息
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

; 卸载后删除安装目录
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
; 桌面快捷方式（默认勾选）
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; 主程序及所有依赖（PyInstaller 6 一目录模式下，依赖在 _internal\ 子目录）
Source: "dist\{#MyAppName}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyAppName}\_internal\*"; DestDir: "{app}\_internal"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
; 桌面快捷方式
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Registry]
; 注册文件类型关联（可选，程序自身也会在首次启动时提示注册）
; 如果不想在安装时注册，可以注释掉下面的内容

; 注册 ProgID
Root: HKCU; Subkey: "Software\Classes\VideoPlayer.File"; \
    ValueType: string; ValueName: ""; ValueData: "视频文件"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VideoPlayer.File\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\VideoPlayer.File\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; 注册各视频扩展名（只注册到当前用户，不需要管理员权限）
Root: HKCU; Subkey: "Software\Classes\.mp4"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.mkv"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.avi"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.mov"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.wmv"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.flv"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.webm"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.m4v"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.mpg"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.mpeg"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"
Root: HKCU; Subkey: "Software\Classes\.3gp"; ValueType: string; ValueName: ""; ValueData: "VideoPlayer.File"

; 将程序加入"打开方式"列表
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}"; \
    ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#MyAppName}"
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExeName}\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
; 安装完成后运行程序（可选）
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时清理（可选）

[Code]
// 通知 Windows Shell 文件关联已更改（刷新图标）
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 刷新文件关联图标缓存
    RegWriteStringValue(HKCU, 'Software\Classes', '', '');
    // 通知 Shell（通过设置一个临时注册表项触发）
  end;
end;
