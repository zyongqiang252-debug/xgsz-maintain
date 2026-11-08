# -*- coding: utf-8 -*-
"""xgsz-maintain 品牌图标生成器

用法：
    python tools/brand/generate_icons.py

产物：
    frontend/public/logo-icon.png        512×512 圆角透明（顶栏/侧栏/登录页/favicon）
    frontend/public/apple-touch-icon.png 180×180 满幅方形（iOS 主屏）
    tools/brand/logo-icon-32.png         32×32 小尺寸自检
    tools/brand/preview.png              三方案对比图

依赖：Pillow、numpy（仅设计期需要，运行期前端不依赖）
配色沿用公司 logo 的蓝青渐变：#0A3896 → #106ED6 → #00D0E8
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PUBLIC = os.path.join(REPO, "frontend", "public")

S = 2048                      # 绘制画布（超采样后缩到目标尺寸）
C_DARK = (10, 56, 150)
C_MID = (16, 110, 214)
C_CYAN = (0, 208, 232)
FONT_BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_CJK = r"C:\Windows\Fonts\msyh.ttc"


# ---------------------------------------------------------------- 基础绘制

def gradient(size):
    """135° 线性渐变"""
    ys = np.linspace(0, 1, size).reshape(-1, 1)
    xs = np.linspace(0, 1, size).reshape(1, -1)
    t = (xs + ys) / 2.0
    stops = np.array([C_DARK, C_MID, C_CYAN], dtype=float)
    out = np.zeros((size, size, 3), dtype=float)
    for i in range(3):
        out[:, :, i] = np.interp(t, [0, 0.5, 1], stops[:, i])
    return Image.fromarray(out.astype("uint8"), "RGB")


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def gear_polygon(cx, cy, r_base, tooth_len, teeth, tip_ratio=0.44, slope_ratio=0.32):
    step = 2 * math.pi / teeth
    pts = []
    for i in range(teeth):
        a = i * step
        for ang, r in ((a - step * (tip_ratio + slope_ratio) / 2, r_base),
                       (a - step * tip_ratio / 2, r_base + tooth_len),
                       (a + step * tip_ratio / 2, r_base + tooth_len),
                       (a + step * (tip_ratio + slope_ratio) / 2, r_base)):
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def gear_mask(size, cx, cy, r_base, tooth, hole, teeth=9):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.polygon(gear_polygon(cx, cy, r_base, tooth, teeth), fill=255)
    d.ellipse([cx - r_base, cy - r_base, cx + r_base, cy + r_base], fill=255)
    if hole:
        d.ellipse([cx - hole, cy - hole, cx + hole, cy + hole], fill=0)
    return m


def wrench_mask(size_box, angle_deg=0, height_ratio=0.72):
    """开口扳手：圆角矩形头 + 锥形手柄 + U 型开口，按包围盒归一化后旋转"""
    R = size_box * 0.055
    W = int(size_box * 3)
    m = Image.new("L", (W, W), 0)
    d = ImageDraw.Draw(m)
    cx, top = W / 2, W * 0.10
    head_w, head_h = 2.45 * R, 2.0 * R
    jaw_w, jaw_depth = 1.15 * R, 1.30 * R
    handle_w, handle_len, taper = 0.78 * R, 3.6 * R, 0.72

    d.rounded_rectangle([cx - head_w / 2, top, cx + head_w / 2, top + head_h],
                        radius=head_w * 0.30, fill=255)
    hy = top + head_h * 0.62
    d.polygon([(cx - handle_w / 2, hy), (cx + handle_w / 2, hy),
               (cx + handle_w * taper / 2, hy + handle_len),
               (cx - handle_w * taper / 2, hy + handle_len)], fill=255)
    d.ellipse([cx - handle_w * taper / 2, hy + handle_len - handle_w * taper / 2,
               cx + handle_w * taper / 2, hy + handle_len + handle_w * taper / 2], fill=255)
    # U 型开口
    d.rectangle([cx - jaw_w / 2, top - jaw_depth * 0.4, cx + jaw_w / 2,
                 top + jaw_depth - jaw_w / 2], fill=0)
    d.ellipse([cx - jaw_w / 2, top + jaw_depth - jaw_w, cx + jaw_w / 2, top + jaw_depth], fill=0)

    bb = m.getbbox()
    m = m.crop(bb)
    th = int(size_box * height_ratio)
    m = m.resize((max(1, int(m.width * th / m.height)), th), Image.LANCZOS)
    canvas = Image.new("L", (size_box, size_box), 0)
    canvas.paste(m, ((size_box - m.width) // 2, (size_box - m.height) // 2))
    if angle_deg:
        canvas = canvas.rotate(angle_deg, resample=Image.BICUBIC)
    return canvas


def shift(mask, dx, dy):
    return mask.transform(mask.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy), resample=Image.BICUBIC)


def add(*masks):
    out = np.zeros_like(np.array(masks[0]))
    for m in masks:
        out = np.maximum(out, np.array(m))
    return Image.fromarray(out.astype("uint8"))


# ---------------------------------------------------------------- 三套方案

def design_a():
    """方案 A（定稿）：白色扳手 + 右下小齿轮"""
    w = shift(wrench_mask(S, angle_deg=-42, height_ratio=0.66), -S * 0.060, -S * 0.055)
    g = gear_mask(S, S * 0.700, S * 0.720, S * 0.125, S * 0.042, S * 0.046, teeth=9)
    return add(w, g)


def design_b():
    """方案 B：齿轮盘 + XG 镂空"""
    cx = cy = S / 2
    g = gear_mask(S, cx, cy, S * 0.285, S * 0.058, 0, teeth=14)
    letters = Image.new("L", (S, S), 0)
    dl = ImageDraw.Draw(letters)
    font = ImageFont.truetype(FONT_BOLD, int(S * 0.180))
    dl.text((cx - S * 0.074, cy + S * 0.010), "X", font=font, fill=255, anchor="mm")
    dl.text((cx + S * 0.074, cy + S * 0.010), "G", font=font, fill=255, anchor="mm")
    white = np.clip(np.array(g).astype(int) - np.array(letters).astype(int), 0, 255)
    return Image.fromarray(white.astype("uint8"))


def design_c():
    """方案 C：白色圆盘 + 反白扳手与齿轮"""
    disc = Image.new("L", (S, S), 0)
    ImageDraw.Draw(disc).ellipse([S * 0.075, S * 0.075, S * 0.925, S * 0.925], fill=255)
    w = shift(wrench_mask(S, angle_deg=-42, height_ratio=0.60), -S * 0.055, -S * 0.050)
    g = gear_mask(S, S * 0.672, S * 0.692, S * 0.098, S * 0.033, S * 0.037, teeth=9)
    white = np.clip(np.array(disc).astype(int) - np.array(add(w, g)).astype(int), 0, 255)
    return Image.fromarray(white.astype("uint8"))


# ---------------------------------------------------------------- 合成输出

def compose(white, rounded=True, radius_ratio=0.225):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    tile = rounded_mask(S, int(S * radius_ratio)) if rounded else Image.new("L", (S, S), 255)
    img.paste(gradient(S), (0, 0), tile)
    img.paste(Image.new("RGBA", (S, S), (255, 255, 255, 255)), (0, 0), white)
    return img


def save(img, path, size):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(path)
    print("  ->", os.path.relpath(path, REPO))


def main():
    os.makedirs(os.path.join(HERE), exist_ok=True)
    print("生成定稿图标（方案 A）")
    save(compose(design_a()), os.path.join(PUBLIC, "logo-icon.png"), 512)
    save(compose(design_a(), rounded=False).convert("RGB"),
         os.path.join(PUBLIC, "apple-touch-icon.png"), 180)
    save(compose(design_a()), os.path.join(HERE, "logo-icon-32.png"), 32)

    print("生成备选方案留档")
    save(compose(design_b()), os.path.join(HERE, "candidate-b-gear-xg.png"), 512)
    save(compose(design_c()), os.path.join(HERE, "candidate-c-badge.png"), 512)

    print("生成对比图")
    pics = [compose(fn()).resize((512, 512), Image.LANCZOS)
            for fn in (design_a, design_b, design_c)]
    names = ["A 扳手+齿轮（定稿）", "B 齿轮盘+XG", "C 圆盘反白"]
    sheet = Image.new("RGB", (3 * 560 + 40, 512 + 60 + 150 + 20), (247, 248, 250))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT_CJK, 22)
    for i, (im, nm) in enumerate(zip(pics, names)):
        x = 20 + i * 560
        sheet.paste(im, (x, 20), im)
        d.text((x, 20 + 512 + 14), nm, font=f, fill=(60, 65, 75))
        px, py = x, 20 + 512 + 56
        for sz in (48, 32, 24, 16):
            big = sz * 2 if sz >= 24 else sz * 3
            sheet.paste(im.resize((sz, sz), Image.LANCZOS).resize((big, big), Image.NEAREST), (px, py))
            px += big + 16
    sheet.save(os.path.join(HERE, "preview.png"))
    print("  ->", os.path.relpath(os.path.join(HERE, "preview.png"), REPO))


if __name__ == "__main__":
    main()
