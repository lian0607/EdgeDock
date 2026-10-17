# -*- coding: utf-8 -*-
"""自检：抽屉收起时鼠标穿透，展开后能接收输入（拖放才落得下来）。

做法是直接读窗口的扩展样式 WS_EX_TRANSPARENT，比 WindowFromPoint 可靠
（Qt 的半透明窗口是 layered window，逐像素 alpha 会影响命中判断）。

用法：.venv\\Scripts\\python.exe tools\\check_hittest.py
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtGui import QGuiApplication

PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
MAIN = os.path.join(ROOT, "main.pyw")

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020

ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                              ctypes.POINTER(wintypes.LPARAM))

app = QGuiApplication([])
screen = QGuiApplication.primaryScreen()
geo = screen.geometry()
DPR = screen.devicePixelRatio()

from edgedock import config as cfg_mod          # noqa: E402
from edgedock.drawer import Geo                 # noqa: E402

cfg = cfg_mod.Config()
g = Geo(cfg)
n = len([i for i in cfg.items if i.get("path")])
wr = g.window_rect(n)
print("图标 %d 个 · 面板 %dx%d · 窗口逻辑 x=%d y=%d"
      % (n, g.panel_len(n), g.thick, wr.x(), wr.y()))


# 抽屉主体窗口的期望位置（物理像素）
EXPECT_W = int(g.panel_len(n) * DPR)
EXPECT_H = int(g.thick * DPR)
EXPECT_X = int(wr.x() * DPR)
EXPECT_Y = int(wr.y() * DPR)


def app_windows():
    """按几何位置找出抽屉窗口。

    不能按 PID 找：venv 的 pythonw.exe 是个启动器，真正跑界面的是它的子进程。
    """
    out = []

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        if abs(w - EXPECT_W) <= 8 and abs(h - EXPECT_H) <= 8 \
                and abs(r.left - EXPECT_X) <= 8 and abs(r.top - EXPECT_Y) <= 8:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            out.append((int(hwnd), r, ex, pid.value))
        return True

    user32.EnumWindows(ENUMPROC(cb), None)
    return out


subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
time.sleep(1.0)
user32.SetCursorPos(int(geo.width() * 0.5 * DPR), int(geo.height() * 0.7 * DPR))
time.sleep(0.3)

# 上面只清得掉 pythonw.exe 起的实例。要是还有别的 EdgeDock 在跑
# （比如用 python.exe 起的），它会把下面按几何找窗口的结果整个带偏 ——
# 那种情况下量到的是**旧实例**的状态，结论毫无意义，先停手。
leftover = app_windows()
if leftover:
    print("\n检测到 %d 个残留的 EdgeDock 窗口（pid=%s）。"
          % (len(leftover), ", ".join(str(p) for *_, p in leftover)))
    print("本脚本只能结束 pythonw.exe 起的实例。请先把其他实例退出再跑，"
          "否则量到的是旧实例的状态。")
    sys.exit(2)

proc = subprocess.Popen([PYW, MAIN], cwd=ROOT,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5.5)
app_pid = proc.pid


def report(tag):
    wins = app_windows()
    print("  [%s] 匹配到抽屉窗口 %d 个：" % (tag, len(wins)))
    for hwnd, r, ex, pid in wins:
        print("      hwnd=%-9d %4dx%-4d at (%d,%d) pid=%d  "
              "WS_EX_TRANSPARENT=%s"
              % (hwnd, r.right - r.left, r.bottom - r.top, r.left, r.top,
                 pid, bool(ex & WS_EX_TRANSPARENT)))
    return wins


def drawer_state():
    """返回抽屉主体窗口的 (是否存在, 是否穿透)。"""
    for hwnd, r, ex, pid in app_windows():
        return True, bool(ex & WS_EX_TRANSPARENT)
    return False, None


print("\n== 收起态（鼠标远离顶边）==")
report("收起")
found, trans = drawer_state()
ok1 = found and trans is True
print("  -> 抽屉应处于穿透状态: %s" % ("OK" if ok1 else "FAIL"))

# 鼠标贴到屏幕顶边中央 -> 展开
user32.SetCursorPos(int(geo.width() // 2 * DPR), 0)
time.sleep(1.6)

print("\n== 展开态（鼠标贴住顶边）==")
report("展开")
found2, trans2 = drawer_state()
ok2 = found2 and trans2 is False
print("  -> 抽屉应可接收输入(不穿透): %s" % ("OK" if ok2 else "FAIL"))

# 再确认面板确实画出来了
img = screen.grabWindow(0).toImage()
cx = int((wr.x() + wr.width() / 2) * DPR)
cy = int((g.thick / 2) * DPR)
c = img.pixelColor(cx, cy)
print("\n  面板中心像素 (%d,%d) = #%02X%02X%02X"
      % (cx, cy, c.red(), c.green(), c.blue()))

ok = ok1 and ok2
print("\n结果: %s" % ("通过 —— 拖放落点可正常命中" if ok else "失败"))

proc.terminate()
time.sleep(0.6)
subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
sys.exit(0 if ok else 1)
