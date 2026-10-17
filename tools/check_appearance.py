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

# 鼠标先放到屏幕中下部，保证抽屉处于收起态
u32.SetCursorPos(int(geo.width() * 0.5 * DPR), int(geo.height() * 0.72 * DPR))
time.sleep(0.4)

proc = subprocess.Popen([PYW, MAIN], cwd=ROOT,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5.5)

img_peek = screen.grabWindow(0).toImage()
img_peek.save(os.path.join(OUT, "A_peek.png"), "PNG")

# 触发展开：鼠标贴到屏幕顶边中央
u32.SetCursorPos(int(geo.width() // 2 * DPR), 0)
time.sleep(1.4)

img_open = screen.grabWindow(0).toImage()
img_open.save(os.path.join(OUT, "B_open_full.png"), "PNG")

# 按真实配置算面板区域，再裁切放大
from edgedock import config as cfg_mod          # noqa: E402
from edgedock.drawer import Geo                 # noqa: E402

cfg = cfg_mod.Config()
g = Geo(cfg)
n = len([i for i in cfg.items if i.get("path")])
wr = g.window_rect(n)
CROP_H = g.thick + 60                            # 下方多留 60px 看有没有倒影

crop = img_open.copy(int(wr.x() * DPR), int(wr.y() * DPR),
                     int(wr.width() * DPR), int(CROP_H * DPR))
crop = crop.scaled(int(crop.width() * 1.6), int(crop.height() * 1.6),
                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
crop.save(os.path.join(OUT, "C_panel_zoom.png"), "PNG")

print("\n图标数 = %d   面板 = %dx%d   窗口逻辑 x=%d y=%d"
      % (n, g.panel_len(n), g.thick, wr.x(), wr.y()))
pts = [
    ("左端留白", wr.x() + 7, g.thick // 2),
    ("右端留白", wr.x() + g.panel_len(n) - 7, g.thick // 2),
    ("面板正中", wr.x() + g.panel_len(n) // 2, g.thick // 2),
    ("面板下方 +6", wr.x() + g.panel_len(n) // 2, g.thick + 6),
    ("面板下方 +24", wr.x() + g.panel_len(n) // 2, g.thick + 24),
]
for label, lx, ly in pts:
    c = img_open.pixelColor(int(lx * DPR), int(ly * DPR))
    print("  %-14s (%4d,%3d) -> #%02X%02X%02X"
          % (label, lx, ly, c.red(), c.green(), c.blue()))

proc.terminate()
time.sleep(0.6)
subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
print("\n截图已写入 _shots\\")
