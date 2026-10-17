# -*- coding: utf-8 -*-
"""外部驱动探针：不接触 EdgeDock 进程内部，只用真实鼠标点它。

用途：验证「用户实际运行的那个实例」到底收不收得到点击 —— 之前几次
进程内探针都通了、用户那边却没反应，所以必须从外面点。

用法（参数是动作序列，逐步截屏）：
    python tools/ext_drive.py hover-right        # 鼠标移到右边缘唤出抽屉
    python tools/ext_drive.py shot NAME          # 截屏存 _ext_NAME.png
    python tools/ext_drive.py click X Y [r]      # 在(逻辑坐标)点一下,r=右键
    python tools/ext_drive.py move X Y           # 移过去停 1 秒
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

u = ctypes.WinDLL("user32", use_last_error=True)
g = ctypes.WinDLL("gdi32", use_last_error=True)
u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
u.GetSystemMetrics.restype = ctypes.c_int

# 进程是 DPI 不感知的，GetSystemMetrics 给的是缩放后的逻辑尺寸
SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
ROOT = r"D:\Program Files (x86)\EdgeDrawer"


def shot(name: str) -> None:
    from PIL import Image
    hdc = u.GetDC(0)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, SW, SH)
    g.SelectObject(mem, bmp)
    g.BitBlt(mem, 0, 0, SW, SH, hdc, 0, 0, 0x00CC0020)

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long),
                    ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    bi = BMI()
    bi.biSize = ctypes.sizeof(BMI)
    bi.biWidth, bi.biHeight = SW, -SH
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(SW * SH * 4)
    g.GetDIBits(mem, bmp, 0, SH, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGBA", (SW, SH), buf, "raw", "BGRA", 0, 1) \
         .convert("RGB").save("%s\\_ext_%s.png" % (ROOT, name))
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(0, hdc)
    print("截屏:", "%s\\_ext_%s.png" % (ROOT, name))


def move(x: int, y: int) -> None:
    u.SetCursorPos(x, y)
    time.sleep(0.9)


def click(x: int, y: int, right: bool = False) -> None:
    u.SetCursorPos(x, y)
    time.sleep(0.25)
    down, up = (8, 16) if right else (2, 4)     # WM_R/U*BUTTON*
    u.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.5)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "hover-right":
        # 右边缘竖直居中往里挪一点点，唤醒抽屉
        move(SW - 2, SH // 2)
        shot("hover")
    elif cmd == "shot":
        shot(rest[0])
    elif cmd == "move":
        move(int(rest[0]), int(rest[1]))
    elif cmd == "click":
        click(int(rest[0]), int(rest[1]),
              right=(len(rest) > 2 and rest[2] == "r"))
    elif cmd == "screen":
        print("逻辑屏尺寸:", SW, "x", SH)
    else:
        print("不认识的命令:", cmd)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
