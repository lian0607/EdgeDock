# -*- coding: utf-8 -*-
"""生成 assets/拖动排序示意.png。

把「拖到一半」的状态真实渲染出来：被拖的图标抬起、空出的槽位是琥珀橙虚线凹槽、
其余图标已经让位。复用 make_preview 里的合成壁纸与渲染函数，不碰使用者的配置。

用法：.venv\\Scripts\\python.exe tools\\make_reorder_preview.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from PySide6.QtCore import QPointF, QRectF, Qt              # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter   # noqa: E402
from PySide6.QtWidgets import QApplication                  # noqa: E402

from edgedock import config as cfg_mod                      # noqa: E402
from edgedock import theme as theme_mod                     # noqa: E402
from edgedock.drawer import DrawerWindow                    # noqa: E402
from edgedock.icons import IconStore                        # noqa: E402

import make_preview as mp                                   # noqa: E402

OUT = os.path.join(ROOT, "assets", "拖动排序示意.png")
W, H = 1280, 470
SCALE = 2.0            # 面板放大倍数，不然在整屏里太小看不清


def build(theme_name, items, drag_i, drop_i, workdir):
    """渲染「拖动中」的一帧：面板 + 抬起图标 + 虚线凹槽。

    返回 (面板图, 被拖图标左上角, 凹槽矩形)，坐标都是面板逻辑坐标。
    """
    cfg_path = os.path.join(workdir, "cfg_%s.json" % theme_name)
    base = dict(cfg_mod.DEFAULTS)
    base.update({"theme": theme_name, "items": [dict(i) for i in items],
                 "pin": True, "icon_size": 44, "padding": 14, "gap": 5,
                 "panel_opacity": 100, "seeded": True})
    import json
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False)

    cfg = cfg_mod.Config(cfg_path)
    store = IconStore(cfg_mod.CACHE_DIR)
    win = DrawerWindow(cfg, store)
    size = int(cfg["icon_size"])
    for _ in range(240):
        QApplication.processEvents()
        if all(store.png_of(i["path"]) for i in items):
            break
        time.sleep(0.05)
    for it in items:
        store.pixmap(it["path"], size, 1.0)
    win.rebuild()

    win.reveal = 1.0
    win.target = 1.0
    win._on_reveal(1.0)

    # 摆成「正在拖第 drag_i 个、落在第 drop_i 个槽位」的样子
    btn = win.buttons[drag_i]
    win.drag_index = drag_i
    win.drop_index = drop_i
    btn.dragging = True
    btn._hover = 1.0
    hole = QRectF(win.slot_rect(drop_i))
    win._place_buttons()
    # 往右偏一点，好让虚线凹槽从左边露出来（完全盖住就看不出占位了）
    pos = hole.topLeft() + QPointF(26, 0)
    btn.move(int(pos.x()), int(pos.y()))
    win.panel.update()
    QApplication.processEvents()

    img = win.panel.grab().toImage()
    win.close()
    win.deleteLater()
    QApplication.processEvents()
    return img, QPointF(pos), hole


def main() -> int:
    app = QApplication([])

    live = cfg_mod.Config()
    items = [i for i in live.items if i.get("path")]
    if len(items) < 6:
        print("图标太少（%d 个），跳过。" % len(items))
        return 1

    items = items[:6]
    print("示意用图标: %s" % [i["name"] for i in items])

    import tempfile
    workdir = tempfile.mkdtemp(prefix="edgedock_reorder_prev_")

    canvas = QImage(W, H, QImage.Format_ARGB32)
    canvas.fill(QColor("#11161F"))
    p = QPainter(canvas)
    bg = mp.make_wallpaper_scaled(W, H) if hasattr(mp, "make_wallpaper_scaled") \
        else mp.make_wallpaper().scaled(W, H, Qt.IgnoreAspectRatio,
                                        Qt.SmoothTransformation)
    p.drawImage(0, 0, bg)

    shot, drag_pos, hole = build("light", items, 0, 3, workdir)
    sw, sh = mp.logical_size(shot)
    x = int((W - sw * SCALE) / 2)
    y = 132
    p.drawImage(QRectF(x, y, sw * SCALE, sh * SCALE), shot)

    def cx(px):
        """面板逻辑 x -> 画布 x"""
        return x + px * SCALE

    def cy(py):
        return y + py * SCALE

    box_w, box_h = hole.width() * SCALE, hole.height() * SCALE

    # ---- 凹槽标注（从上方引下来）----------------------------------------
    f = QFont("Microsoft YaHei UI", 10)
    p.setFont(f)
    p.setPen(QColor(255, 138, 66, 250))
    hx, hy = cx(hole.left()), cy(hole.top())
    p.drawLine(QPointF(hx + 12, hy - 26), QPointF(hx + 12, hy - 6))
    p.drawLine(QPointF(hx + 12, hy - 6), QPointF(hx + 4, hy + 4))
    p.drawText(QRectF(hx - 46, hy - 54, 320, 26), Qt.AlignLeft | Qt.AlignTop,
               "虚线凹槽 = 将要落下的位置")

    # ---- 抬起图标标注（从下方引上去）------------------------------------
    dx, dy = cx(drag_pos.x()), cy(drag_pos.y())
    p.drawLine(QPointF(dx + box_w / 2, dy + box_h + 24),
               QPointF(dx + box_w / 2, dy + box_h + 5))
    p.drawLine(QPointF(dx + box_w / 2, dy + box_h + 5),
               QPointF(dx + box_w / 2 - 8, dy + box_h - 6))
    p.drawText(QRectF(dx - 10, dy + box_h + 26, 320, 26),
               Qt.AlignLeft | Qt.AlignTop, "按住图标拖动，图标会「抬起」")

    cap = QFont("Microsoft YaHei UI", 13)
    cap.setBold(True)
    p.setFont(cap)
    p.setPen(QColor(232, 240, 248, 245))
    p.drawText(QRectF(0, 40, W, 30), Qt.AlignHCenter | Qt.AlignVCenter,
               "在抽屉里按住图标拖动，松手即换位")
    f2 = QFont("Microsoft YaHei UI", 10)
    p.setFont(f2)
    p.setPen(QColor(178, 194, 212, 205))
    p.drawText(QRectF(0, 74, W, 26), Qt.AlignHCenter | Qt.AlignTop,
               "旁边的图标实时让位 · 拖到两端会自动滚动 · 顺序立刻写入 config.json")
    p.end()

    canvas.save(OUT, "PNG")
    import shutil
    shutil.rmtree(workdir, ignore_errors=True)
    print("已写入 %s  (%dx%d)" % (OUT, canvas.width(), canvas.height()))
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
