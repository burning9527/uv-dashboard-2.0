#!/usr/bin/env python3
"""生成 UV Dashboard 应用图标 (.icns)"""
import subprocess
import os

BUILD_DIR = os.path.dirname(os.path.abspath(__file__))
ICONSET_DIR = os.path.join(BUILD_DIR, 'AppIcon.iconset')
ICNS_PATH = os.path.join(BUILD_DIR, 'AppIcon.icns')

os.makedirs(ICONSET_DIR, exist_ok=True)

# 用 macOS sips 工具从 SVG 生成各尺寸 PNG
# 先生成一个 1024x1024 的主图标 PNG
# 我们用 Python + Pillow 生成一个简洁的图标

from PIL import Image, ImageDraw, ImageFont

def create_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 圆角矩形背景 - UV 蓝色主题
    margin = int(size * 0.05)
    radius = int(size * 0.18)
    
    # 绘制圆角矩形
    x0, y0 = margin, margin
    x1, y1 = size - margin, size - margin
    
    # 背景色: #378add (UV Dashboard 主色)
    bg_color = (55, 138, 221, 255)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=bg_color)
    
    # UV 文字
    font_size = int(size * 0.38)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/SFNSText-Bold.otf', font_size)
    except:
        try:
            font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Helvetica Bold.ttf', font_size)
        except:
            font = ImageFont.load_default()
    
    text = "UV"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2
    ty = (size - th) // 2 - int(size * 0.05)
    
    # 白色文字
    draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)
    
    # 底部小字 "台帐"
    small_size = int(size * 0.10)
    try:
        small_font = ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', small_size)
    except:
        try:
            small_font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Songti.ttc', small_size)
        except:
            small_font = ImageFont.load_default()
    
    small_text = "台帐"
    sbbox = draw.textbbox((0, 0), small_text, font=small_font)
    sw = sbbox[2] - sbbox[0]
    sx = (size - sw) // 2
    sy = ty + th + int(size * 0.06)
    draw.text((sx, sy), small_text, fill=(255, 255, 255, 200), font=small_font)
    
    return img

# macOS iconset 需要以下尺寸
sizes_map = {
    'icon_16x16.png': 16,
    'icon_16x16@2x.png': 32,
    'icon_32x32.png': 32,
    'icon_32x32@2x.png': 64,
    'icon_128x128.png': 128,
    'icon_128x128@2x.png': 256,
    'icon_256x256.png': 256,
    'icon_256x256@2x.png': 512,
    'icon_512x512.png': 512,
    'icon_512x512@2x.png': 1024,
}

for filename, px in sizes_map.items():
    icon = create_icon(px)
    icon.save(os.path.join(ICONSET_DIR, filename))

# 用 iconutil 转换为 .icns
subprocess.run(['iconutil', '-c', 'icns', ICONSET_DIR, '-o', ICNS_PATH], check=True)
print(f'Created icon: {ICNS_PATH}')
