# -*- coding: utf-8 -*-
"""生成 assets/预览效果.png。

用一张合成壁纸当背景，把抽屉面板（深色 / 浅色两套）真实渲染后叠上去，
这样既能展示浅色的半透明效果，又不会把使用者的真实桌面内容带进来。

用法：.venv\\Scripts\\python.exe tools\\make_preview.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter,
                           QPainterPath, QRadialGradient)
from PySide6.QtWidgets import QApplication

from edgedock import config as cfg_mod
from edgedock import theme as theme_mod
from edgedock.drawer import DrawerWindow
from edgedock.icons import IconStore

OUT = os.path.join(ROOT, "assets", "预览效果.png")
W, H = 1600, 512


def make_wallpaper() -> QImage:
    """合成一张有明暗层次的壁纸，方便看出面板的半透明。"""
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(QColor("#20293A"))

    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)

    g = QLinearGradient(0, 0, W, H)
    g.setColorAt(0.00, QColor("#12324F"))
    g.setColorAt(0.38, QColor("#1E5A6B"))
    g.setColorAt(0.66, QColor("#3F7F72"))
    g.setColorAt(1.00, QColor("#101820"))
    p.fillRect(img.rect(), g)

    # 几个柔和光斑，模拟真实壁纸的层次
    for cx, cy, rad, col, a in [
        (0.22, 0.18, 0.42, "#7FD4E8", 120),
        (0.78, 0.30, 0.36, "#FFD08A", 96),
        (0.55, 0.86, 0.50, "#0C2A3C", 150),
        (0.06, 0.74, 0.34, "#2FBF9E", 70),
    ]:
        rg = QRadialGradient(QPointF(cx * W, cy * H), rad * W)
        c = QColor(col)
        c.setAlpha(a)
        rg.setColorAt(0.0, c)
        c2 = QColor(col)
        c2.setAlpha(0)
        rg.setColorAt(1.0, c2)
        p.fillRect(img.rect(), rg)

    # 一点淡淡的网格，证明面板下方的东西能透出来
    p.setPen(QColor(255, 255, 255, 12))
    step = 64
    for x in range(0, W, step):
        p.drawLine(x, 0, x, H)
    for y in range(0, H, step):
        p.drawLine(0, y, W, y)
    p.end()
    return img


def render_panel(theme_name: str, items: list[dict], workdir: str) -> QImage:
    """把抽屉面板真实渲染成一张带 alpha 的图。"""
    cfg_path = os.path.join(workdir, "cfg_%s.json" % theme_name)
    base = dict(cfg_mod.DEFAULTS)
    base.update({
        "theme": theme_name,
        "items": [dict(i) for i in items],
        "pin": True,
        "icon_size": 44,
        "padding": 14,
        "gap": 5,
        "panel_opacity": 100,
        "seeded": True,
    })
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False)

    cfg = cfg_mod.Config(cfg_path)
    # 直接用程序自己的图标缓存，省得重新提取
    store = IconStore(cfg_mod.CACHE_DIR)
    win = DrawerWindow(cfg, store)

    # 等所有图标就绪（缓存命中时几乎是瞬间）
    size = int(cfg["icon_size"])
    for _ in range(240):                     # 最多等 ~12 秒
        QApplication.processEvents()
        store.pixmap(items[0]["path"], size, 1.0)   # 触发一次缓存
        if all(store.png_of(i["path"]) for i in items):
            break
        time.sleep(0.05)
    missing = [i["name"] for i in items if not store.png_of(i["path"])]
    if missing:
        print("  警告：%d 个图标没取到 -> %s" % (len(missing), missing))
    for it in items:                          # 预热 pixmap 缓存 + 刷新按钮
        store.pixmap(it["path"], size, 1.0)
    win.rebuild()
    QApplication.processEvents()

    win.reveal = 1.0
    win.target = 1.0
    win._on_reveal(1.0)
    QApplication.processEvents()

    panel = win.panel
    pm = panel.grab()
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    win.close()
    win.deleteLater()
    QApplication.processEvents()
    return img


def logical_size(img: QImage) -> tuple[int, int]:
    """grab() 出来的图带着 DPR(1.5)，绘制时按逻辑尺寸算才居中。"""
    dpr = img.devicePixelRatio() or 1.0
    return int(round(img.width() / dpr)), int(round(img.height() / dpr))


def draw_caption(p: QPainter, y: float, text: str, color: QColor) -> None:
    f = QFont("Microsoft YaHei UI", 12)
    f.setBold(True)
    p.setFont(f)
    p.setPen(color)
    p.drawText(QRectF(0, y, W, 26), Qt.AlignHCenter | Qt.AlignVCenter, text)


def main() -> int:
    app = QApplication([])

    live = cfg_mod.Config()                     # 读真实配置，用真实图标列表
    items = [i for i in live.items if i.get("path")][:11]
    if not items:
        print("说明：真实配置里没有图标，无法生成预览。")
        return 1
    print("使用 %d 个真实图标生成预览。" % len(items))

    workdir = tempfile.mkdtemp(prefix="edgedock_prev_")
    bg = make_wallpaper()

    canvas = QImage(W, H, QImage.Format_ARGB32)
    canvas.fill(QColor("#11161F"))
    p = QPainter(canvas)
    p.drawImage(0, 0, bg)

    # ---- 浅色（半透明）面板：叠在壁纸亮部 ---------------------------------
    light = render_panel("light", items, workdir)
    lw, lh = logical_size(light)
    lx = int((W - lw) / 2)
    ly = 74
    p.drawImage(lx, ly, light)
    draw_caption(p, ly + lh + 18, "浅色主题 · 半透明磨砂白",
                 QColor(240, 245, 250, 235))

    # ---- 深色面板 ---------------------------------------------------------
    dark = render_panel("dark", items, workdir)
    dw, dh = logical_size(dark)
    dx = int((W - dw) / 2)
    dy = ly + lh + 74
    p.drawImage(dx, dy, dark)
    draw_caption(p, dy + dh + 18, "深色主题", QColor(190, 200, 214, 220))
    print("  浅色面板 %dx%d @ (%d,%d)  深色 %dx%d @ (%d,%d)"
          % (lw, lh, lx, ly, dw, dh, dx, dy))

    # 底部说明
    f = QFont("Microsoft YaHei UI", 11)
    f.setBold(True)
    p.setFont(f)
    foot = dy + dh + 96
    p.setPen(QColor(228, 236, 245, 240))
    p.drawText(QRectF(0, foot, W, 30), Qt.AlignHCenter | Qt.AlignTop,
               "EdgeDock · 边缘抽屉 — 吸附屏幕边缘，只显示图标")
    f2 = QFont("Microsoft YaHei UI", 10)
    p.setFont(f2)
    p.setPen(QColor(196, 210, 226, 205))
    p.drawText(QRectF(0, foot + 26, W, 30), Qt.AlignHCenter | Qt.AlignTop,
               "鼠标碰一下屏幕边缘就滑出 · 把快捷方式直接拖进来即可添加")

    p.end()
    canvas.save(OUT, "PNG")

    import shutil
    shutil.rmtree(workdir, ignore_errors=True)
    print("已写入 %s  (%dx%d)" % (OUT, canvas.width(), canvas.height()))
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
