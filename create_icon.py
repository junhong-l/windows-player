"""
生成视频播放器图标
"""
from PIL import Image, ImageDraw

def create_player_icon():
    """创建一个简洁的播放器图标"""
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        # 创建透明背景图像
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # 背景圆角矩形 - 深色渐变效果
        padding = size // 16 or 1
        radius = size // 6
        
        # 绘制背景（深蓝色）
        bg_color = (26, 26, 36, 255)  # 深色背景
        draw.rounded_rectangle(
            [padding, padding, size - padding - 1, size - padding - 1],
            radius=radius,
            fill=bg_color
        )
        
        # 绘制播放三角形（B站蓝色）
        play_color = (0, 161, 214, 255)  # #00a1d6
        
        # 计算三角形坐标（稍微偏右以视觉居中）
        center_x = size // 2 + size // 20
        center_y = size // 2
        triangle_size = size // 3
        
        # 三角形顶点
        points = [
            (center_x - triangle_size // 2, center_y - triangle_size // 2),  # 左上
            (center_x - triangle_size // 2, center_y + triangle_size // 2),  # 左下
            (center_x + triangle_size // 2, center_y),  # 右中
        ]
        
        draw.polygon(points, fill=play_color)
        
        images.append(img)
    
    # 保存为 ICO 文件
    images[0].save(
        'icon.ico',
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print("图标已生成: icon.ico")
    
    # 同时保存 PNG 版本（用于其他用途）
    images[-1].save('icon.png', format='PNG')
    print("PNG 版本已生成: icon.png")

if __name__ == '__main__':
    create_player_icon()
