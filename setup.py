"""
一键设置脚本 - 安装依赖并下载必要文件
使用方法: python setup.py
"""
import os
import sys
import subprocess

def print_header(text):
    """打印标题"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")

def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print("❌ Python 版本过低，需要 Python 3.10 或更高版本")
        print(f"   当前版本: {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python 版本: {version.major}.{version.minor}.{version.micro}")
    return True

def install_dependencies():
    """安装 Python 依赖"""
    print_header("步骤 1: 安装 Python 依赖")
    
    if not os.path.exists('requirements.txt'):
        print("❌ 找不到 requirements.txt 文件")
        return False
    
    print("📦 正在安装依赖包...")
    result = subprocess.run([
        sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'
    ])
    
    if result.returncode != 0:
        print("❌ 依赖安装失败")
        return False
    
    # 安装 PyInstaller
    print("\n📦 正在安装 PyInstaller...")
    result = subprocess.run([
        sys.executable, '-m', 'pip', 'install', 'pyinstaller'
    ])
    
    if result.returncode != 0:
        print("❌ PyInstaller 安装失败")
        return False
    
    print("✅ 所有依赖已安装")
    return True

def check_libmpv():
    """检查 libmpv-2.dll"""
    print_header("步骤 2: 检查 libmpv-2.dll")
    
    if os.path.exists('libmpv-2.dll'):
        size_mb = os.path.getsize('libmpv-2.dll') / (1024 * 1024)
        print(f"✅ libmpv-2.dll 已存在 ({size_mb:.1f} MB)")
        return True
    
    print("❌ libmpv-2.dll 不存在")
    print("\n⚠️  这是播放器的核心文件，必须手动下载！")
    print("\n📥 下载步骤：")
    print("   1. 访问: https://sourceforge.net/projects/mpv-player-windows/files/libmpv/")
    print("   2. 下载最新版本的 mpv-dev-x86_64-*.7z")
    print("   3. 解压后找到 libmpv-2.dll")
    print("   4. 将 libmpv-2.dll 复制到项目根目录")
    print("\n💡 或者，如果你已经安装了 mpv 播放器：")
    print("   - 在安装目录找到 libmpv-2.dll")
    print("   - 通常位于: C:\\Program Files\\mpv\\libmpv-2.dll")
    
    return False

def check_all_files():
    """检查所有必要文件"""
    print_header("步骤 3: 检查必要文件")
    
    required_files = {
        'main.py': '主程序',
        'main_window.py': '主窗口',
        'player_core.py': '播放器核心',
        'folder_settings.py': '文件夹设置',
        'icon.ico': '图标文件',
        'build.py': '打包脚本',
        'build.spec': '打包配置',
    }
    
    all_exist = True
    for file, desc in required_files.items():
        if os.path.exists(file):
            print(f"✅ {file:20s} - {desc}")
        else:
            print(f"❌ {file:20s} - {desc} (缺失)")
            all_exist = False
    
    return all_exist

def test_imports():
    """测试关键模块导入"""
    print_header("步骤 4: 测试模块导入")
    
    modules = [
        ('PyQt6', 'PyQt6 界面库'),
        ('darkdetect', '深色模式检测'),
        ('qtawesome', '图标库'),
        ('PyInstaller', '打包工具'),
    ]
    
    all_ok = True
    for module_name, desc in modules:
        try:
            __import__(module_name)
            print(f"✅ {module_name:20s} - {desc}")
        except ImportError:
            print(f"❌ {module_name:20s} - {desc} (导入失败)")
            all_ok = False
    
    # mpv 单独测试，因为它需要 dll 文件
    try:
        import mpv
        print(f"✅ mpv                  - python-mpv 播放器库")
    except OSError:
        print(f"⚠️  mpv                  - python-mpv 播放器库 (缺少 libmpv-2.dll)")
        # 不算失败，因为这是预期的
    except ImportError:
        print(f"❌ mpv                  - python-mpv 播放器库 (导入失败)")
        all_ok = False
    
    return all_ok

def main():
    print("=" * 60)
    print("  🎬 视频播放器 - 环境设置工具")
    print("=" * 60)
    
    # 切换到脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # 检查 Python 版本
    if not check_python_version():
        sys.exit(1)
    
    # 安装依赖
    if not install_dependencies():
        print("\n⚠️  请手动安装依赖: pip install -r requirements.txt")
        sys.exit(1)
    
    # 检查 libmpv
    has_libmpv = check_libmpv()
    
    # 检查文件
    all_files = check_all_files()
    
    # 测试导入
    all_imports = test_imports()
    
    # 总结
    print_header("设置总结")
    
    if all_files and all_imports and has_libmpv:
        print("✅ 环境设置完成！所有检查通过。")
        print("\n📦 可以开始打包:")
        print("   python build.py")
        print("\n🎮 或者运行开发版本:")
        print("   python main.py")
    else:
        print("⚠️  环境设置未完成，请解决上述问题。")
        if not has_libmpv:
            print("\n❗ 最重要的是下载 libmpv-2.dll 文件！")
        sys.exit(1)

if __name__ == '__main__':
    main()
