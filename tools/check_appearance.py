# -*- coding: utf-8 -*-
"""外观自检：启动 EdgeDock，先拍「收起态」，再强制展开拍一张，然后裁切放大。

改过配色 / 内边距 / 面板透明度之后，跑一下这个脚本就能直观看到效果，
不用自己截屏对像素。

用法：
    .venv\\Scripts\\python.exe tools\\check_appearance.py

产物都在程序目录的 _shots\\ 下：
    A_peek.png        收起态整屏
    B_open_full.png   展开态整屏
    C_panel_zoom.png  面板区域放大裁切
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage

PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
MAIN = os.path.join(ROOT, "main.pyw")
OUT = os.path.join(ROOT, "_shots")
os.makedirs(OUT, exist_ok=True)

app = QGuiApplication([])
screen = QGuiApplication.primaryScreen()
geo = screen.geometry()
DPR = screen.devicePixelRatio()
u32 = ctypes.windll.user32
print("屏幕逻辑 %dx%d  DPR=%s" % (geo.width(), geo.height(), DPR))

# 只清理 app 用的 pythonw（本脚本自己是 python.exe，不能误杀）
subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
time.sleep(0.9)

from edgedock import config as cfg_mod          # noqa: E402
from edgedock.drawer import Geo                 # noqa: E402

cfg = cfg_mod.Config()
g = Geo(cfg)
# 条目有两种寻址方式（应用标识 / 文件路径），两种都算数
n = len(cfg.items)

# 触发展开的位置必须落在**实际吸附的那条边**上 —— 吸附在右边却去碰顶边，
# 抽屉当然不会弹出来，截到的就只是一张收起态的图
if g.edge == "top":
    trigger = (geo.width() // 2, 0)
elif g.edge == "bottom":
    trigger = (geo.width() // 2, geo.height() - 1)
elif g.edge == "left":
    trigger = (0, geo.height() // 2)
else:
    trigger = (geo.width() - 1, geo.height() // 2)
print("吸附边 = %s   触发展开点 = %s" % (g.edge, trigger))

# 鼠标先放到屏幕中下部，保证抽屉处于收起态
u32.SetCursorPos(int(geo.width() * 0.5 * DPR), int(geo.height() * 0.72 * DPR))
time.sleep(0.4)

proc = subprocess.Popen([PYW, MAIN], cwd=ROOT,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5.5)

img_peek = screen.grabWindow(0).toImage()
img_peek.save(os.path.join(OUT, "A_peek.png"), "PNG")

# 触发展开
u32.SetCursorPos(int(trigger[0] * DPR), int(trigger[1] * DPR))
time.sleep(1.4)

img_open = screen.grabWindow(0).toImage()
img_open.save(os.path.join(OUT, "B_open_full.png"), "PNG")

wr = g.window_rect(n)
EXTRA = 60                                       # 面板外侧多留 60px，看有没有多余投影
if g.horizontal:
    box = (wr.x(), wr.y(), wr.width(), g.thick + EXTRA)
else:
    box = (wr.x(), wr.y(), g.thick + EXTRA, wr.height())
crop = img_open.copy(int(box[0] * DPR), int(box[1] * DPR),
                     int(box[2] * DPR), int(box[3] * DPR))
crop = crop.scaled(int(crop.width() * 1.6), int(crop.height() * 1.6),
                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
crop.save(os.path.join(OUT, "C_panel_zoom.png"), "PNG")

print("\n图标数 = %d   面板 = %dx%d   窗口逻辑 x=%d y=%d"
      % (n, g.panel_len(n), g.thick, wr.x(), wr.y()))
# 取样点：沿边方向取左/中/右（横）或上/中/下（竖），再在面板外侧取两个点
L = g.panel_len(n)
mid = g.thick // 2
if g.horizontal:
    pts = [("起点留白", wr.x() + 7, mid),
           ("末端留白", wr.x() + L - 7, mid),
           ("面板正中", wr.x() + L // 2, mid),
           ("面板外侧 +6", wr.x() + L // 2, g.thick + 6),
           ("面板外侧 +24", wr.x() + L // 2, g.thick + 24)]
else:
    pts = [("起点留白", wr.x() + mid, wr.y() + 7),
           ("末端留白", wr.x() + mid, wr.y() + L - 7),
           ("面板正中", wr.x() + mid, wr.y() + L // 2),
           ("面板外侧 +6", wr.x() + g.thick + 6, wr.y() + L // 2),
           ("面板外侧 +24", wr.x() + g.thick + 24, wr.y() + L // 2)]
for label, lx, ly in pts:
    c = img_open.pixelColor(int(lx * DPR), int(ly * DPR))
    print("  %-14s (%4d,%3d) -> #%02X%02X%02X"
          % (label, lx, ly, c.red(), c.green(), c.blue()))

proc.terminate()
time.sleep(0.6)
subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
print("\n截图已写入 _shots\\")
