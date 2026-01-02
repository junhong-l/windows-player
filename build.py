"""
打包脚本
运行方法: python build.py
"""
import os
import sys
import shutil
import subprocess

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
        'icon.ico',
        'build.spec',
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
    """执行打包"""
    print("\n🔨 开始打包...\n")
    
    result = subprocess.run([
        sys.executable, '-m', 'PyInstaller',
        'build.spec',
        '--clean',
        '--noconfirm',
    ])
    
    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("✅ 打包成功!")
        print("=" * 50)
        print(f"\n📦 输出文件: dist/视频播放器.exe")
        
        # 显示文件大小
        exe_path = os.path.join('dist', '视频播放器.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"📊 文件大小: {size_mb:.1f} MB")
    else:
        print("\n❌ 打包失败，请检查错误信息")

def main():
    print("=" * 50)
    print("🎬 视频播放器打包工具")
    print("=" * 50)
    
    # 切换到脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # 检查文件
    if not check_files():
        sys.exit(1)
    
    # 询问是否清理
    clean()
    
    # 执行打包
    build()

if __name__ == '__main__':
    main()
