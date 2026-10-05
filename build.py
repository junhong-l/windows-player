"""
打包脚本（一目录模式 PyInstaller 构建 + Inno Setup 生成安装包）
运行方法:
  python build.py            # 打包并生成安装包（默认，输出 dist\视频播放器_安装包_vX.X.X.exe）
  python build.py --dir-only # 仅 PyInstaller 打包，不生成安装包，输出 dist\视频播放器\ 目录
"""
import os
import sys
import shutil
import subprocess

# 输出目录名（与 build.spec 中的 name 一致）
APP_NAME = "视频播放器"
DIST_DIR = os.path.join("dist", APP_NAME)
EXE_NAME = f"{APP_NAME}.exe"


def clean():
    """清理之前的构建文件"""
    dirs_to_remove = ['build', 'dist', '__pycache__']
    for d in dirs_to_remove:
        if os.path.exists(d):
            print(f"清理 {d}...")
            shutil.rmtree(d)

    # 清理 .pyc 文件
    for root, dirs, files in os.walk('.'):
        for f in files:
            if f.endswith('.pyc'):
                os.remove(os.path.join(root, f))


def check_files():
    """检查必要文件是否存在"""
    required_files = [
        'main.py',
        'main_window.py',
        'player_core.py',
        'folder_settings.py',
        'casting.py',
        'airplay_receiver.py',
        'cast_dialog.py',
        'icon.ico',
        'build.spec',
        'third_party/SFTA.ps1',
        'third_party/set-default-player.ps1',
        'third_party/PS-SFTA-LICENSE.txt',
    ]

    # libmpv-2.dll 是关键文件，单独检查
    critical_files = {
        'libmpv-2.dll': '从 https://sourceforge.net/projects/mpv-player-windows/files/libmpv/ 下载'
    }

    missing = []
    for f in required_files:
        if not os.path.exists(f):
            missing.append(f)

    missing_critical = []
    for f, hint in critical_files.items():
        if not os.path.exists(f):
            missing_critical.append((f, hint))

    if missing or missing_critical:
        print("❌ 缺少以下文件:")
        for f in missing:
            print(f"   - {f}")

        if missing_critical:
            print("\n⚠️  关键文件缺失:")
            for f, hint in missing_critical:
                print(f"   - {f}")
                print(f"     获取方式: {hint}")

        print("\n请确保所有文件都存在后再打包。")
        return False

    print("✅ 所有必要文件已就绪")
    return True


def build():
    """执行 PyInstaller 打包（一目录模式）"""
    print("\n🔨 开始 PyInstaller 打包...\n")

    result = subprocess.run([
        sys.executable, '-m', 'PyInstaller',
        'build.spec',
        '--clean',
        '--noconfirm',
    ])

    if result.returncode != 0:
        print("\n❌ 打包失败，请检查错误信息")
        return False

    # 验证输出
    exe_path = os.path.join(DIST_DIR, EXE_NAME)
    if not os.path.exists(exe_path):
        print(f"\n❌ 未找到输出文件: {exe_path}")
        return False

    # 统计目录大小
    total_size = 0
    for dirpath, _, filenames in os.walk(DIST_DIR):
        for f in filenames:
            total_size += os.path.getsize(os.path.join(dirpath, f))
    size_mb = total_size / (1024 * 1024)

    print("\n" + "=" * 50)
    print("✅ PyInstaller 打包成功!")
    print("=" * 50)
    print(f"\n📁 输出目录: {DIST_DIR}")
    print(f"📊 目录总大小: {size_mb:.1f} MB")
    return True


def find_inno_setup() -> str:
    """查找 Inno Setup 编译器路径"""
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
        r"C:\Program Files\Inno Setup 7\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    # 尝试通过 PATH 查找
    try:
        result = subprocess.run(['where', 'ISCC'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0]
    except Exception:
        pass

    return ""


def build_installer():
    """使用 Inno Setup 生成安装程序"""
    if not os.path.exists('installer.iss'):
        print("\n❌ 未找到 installer.iss，请先创建 Inno Setup 脚本")
        return False

    iscc = find_inno_setup()
    if not iscc:
        print("\n❌ 未找到 Inno Setup 编译器 (ISCC.exe)")
        print("   请从 https://jrsoftware.org/isdl.php 下载并安装 Inno Setup（6 或以上版本均可）")
        print("\n💡 安装后重新运行: python build.py --installer")
        return False

    # 从 version.py 读取版本号并自动同步到 installer.iss
    import importlib.util
    spec = importlib.util.spec_from_file_location('version', 'version.py')
    ver_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ver_mod)
    version = ver_mod.__version__

    iss_text = open('installer.iss', encoding='utf-8').read()
    import re
    iss_text = re.sub(r'(#define MyAppVersion\s+")[^"]*(")', rf'\g<1>{version}\2', iss_text)
    open('installer.iss', 'w', encoding='utf-8').write(iss_text)
    print(f"🔧 installer.iss 版本号已同步为 {version}")
    result = subprocess.run([iscc, 'installer.iss'])

    if result.returncode != 0:
        print("\n❌ 安装包生成失败")
        return False

    # 查找生成的安装包
    import glob
    installers = glob.glob(os.path.join('dist', f'{APP_NAME}_安装包_*.exe'))
    if installers:
        installer_path = installers[-1]
        size_mb = os.path.getsize(installer_path) / (1024 * 1024)
        print("\n" + "=" * 50)
        print("✅ 安装包生成成功!")
        print("=" * 50)
        print(f"\n📦 安装包: {installer_path}")
        print(f"📊 大小: {size_mb:.1f} MB")
    else:
        print("\n✅ 安装包生成完成（请在 dist 目录查找）")

    return True


def main():
    # 默认打包并生成安装包；--dir-only 时仅保留 PyInstaller 的一目录输出，不生成安装包
    dir_only = '--dir-only' in sys.argv

    print("=" * 50)
    print("🎬 视频播放器打包工具")
    if dir_only:
        print("   模式：仅 PyInstaller 一目录打包")
    else:
        print("   模式：PyInstaller + Inno Setup 安装包")
    print("=" * 50)

    # 切换到脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 检查文件
    if not check_files():
        sys.exit(1)

    # 清理
    clean()

    # PyInstaller 打包
    if not build():
        sys.exit(1)

    # 生成安装包（默认行为）
    if not dir_only:
        if not build_installer():
            sys.exit(1)
        # 安装包已生成，删除中间产物（PyInstaller 输出目录 + 中间 exe）
        if os.path.exists(DIST_DIR):
            shutil.rmtree(DIST_DIR)
        mid_exe = os.path.join('dist', EXE_NAME)
        if os.path.exists(mid_exe):
            os.remove(mid_exe)
    else:
        print(f"\n⚠️  注意：--dir-only 模式需将整个 '{APP_NAME}' 目录发给用户才能运行。")
        print("💡 提示：直接运行 'python build.py'（不带参数）可生成完整安装包。")


if __name__ == '__main__':
    main()
