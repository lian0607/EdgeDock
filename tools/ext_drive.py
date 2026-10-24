# -*- coding: utf-8 -*-
"""外部驱动探针：不接触 EdgeDock 进程内部，只用真实鼠标点它。

用途：验证「用户实际运行的那个实例」到底收不收得到点击 —— 之前几次
进程内探针都通了、用户那边却没反应，所以必须从外面点。

用法（参数是动作序列，逐步截屏）：
    python tools/ext_drive.py hover-right        # 鼠标移到右边缘唤出抽屉
    python tools/ext_drive.py shot NAME          # 截屏存 _ext_NAME.png
    python tools/ext_drive.py click X Y [r]      # 在(截图上量的坐标)点一下,r=右键
    python tools/ext_drive.py move X Y           # 移过去停 1 秒
    python tools/ext_drive.py key down 7         # 敲 7 次方向下键（菜单里选条目用）
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

# GetSystemMetrics 给的是**逻辑**尺寸（进程 DPI 不感知，看到的是缩放后的世界）
SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)


def _phys_size() -> tuple[int, int]:
    class _DM(ctypes.Structure):
        _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                    ("dmSpecVersion", ctypes.c_ushort),
                    ("dmDriverVersion", ctypes.c_ushort),
                    ("dmSize", ctypes.c_ushort),
                    ("dmDriverExtra", ctypes.c_ushort),
                    ("dmFields", ctypes.c_uint),
                    ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                    ("dmDisplayOrientation", ctypes.c_uint),
                    ("dmDisplayFixedOutput", ctypes.c_uint),
                    ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
                    ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                    ("dmFormName", ctypes.c_wchar * 32),
                    ("dmLogPixels", ctypes.c_ushort), ("dmBitsPerPel", ctypes.c_uint),
                    ("dmPelsWidth", ctypes.c_uint), ("dmPelsHeight", ctypes.c_uint),
                    ("dmDisplayFlags", ctypes.c_uint),
                    ("dmDisplayFrequency", ctypes.c_uint),
                    ("dmICMMethod", ctypes.c_uint), ("dmICMIntent", ctypes.c_uint),
                    ("dmMediaType", ctypes.c_uint), ("dmDitherType", ctypes.c_uint),
                    ("dmReserved1", ctypes.c_uint), ("dmReserved2", ctypes.c_uint),
                    ("dmPanningWidth", ctypes.c_uint),
                    ("dmPanningHeight", ctypes.c_uint)]

    dm = _DM()
    dm.dmSize = ctypes.sizeof(_DM)
    if u.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):
        return dm.dmPelsWidth, dm.dmPelsHeight
    return SW, SH


PW, PH = _phys_size()
SCALE = PW / float(SW) if PW > SW else 1.0

# 两个坐标系不一样，这里踩过坑：
#   * 截图（BitBlt 桌面）拿到的是**物理像素**，而且被裁到 1707x960 就停
#     （本进程以为屏幕只有这么大），所以画面右下角其实是缺的；
#   * SetCursorPos 收的却是**逻辑坐标**（设 2000 会被夹到 1706）。
# 于是：截图上的坐标要**除以**缩放倍数才是该传给 SetCursorPos 的值。
# 拿 GetWindowRect 量菜单验证过：菜单真实矩形 (846,53,1032,316)，
# 在截图上量出来是 (1269,79,1548,474) —— 正好差 1.5 倍。
ROOT = r"D:\Program Files (x86)\EdgeDrawer"


def shot(name: str) -> None:
    from PIL import Image
    hdc = u.GetDC(0)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, PW, PH)
    g.SelectObject(mem, bmp)
    g.BitBlt(mem, 0, 0, PW, PH, hdc, 0, 0, 0x00CC0020)

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
    bi.biWidth, bi.biHeight = PW, -PH
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(PW * PH * 4)
    g.GetDIBits(mem, bmp, 0, PH, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGBA", (PW, PH), buf, "raw", "BGRA", 0, 1) \
         .convert("RGB").save("%s\\_ext_%s.png" % (ROOT, name))
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(0, hdc)
    print("截屏:", "%s\\_ext_%s.png" % (ROOT, name), "(%dx%d)" % (PW, PH))


def _to_cursor(x: float, y: float) -> tuple[int, int]:
    """截图坐标 -> SetCursorPos 要的逻辑坐标。"""
    return int(round(x / SCALE)), int(round(y / SCALE))


def move(x: int, y: int) -> None:
    u.SetCursorPos(*_to_cursor(x, y))
    time.sleep(0.9)


def click(x: int, y: int, right: bool = False) -> None:
    u.SetCursorPos(*_to_cursor(x, y))
    time.sleep(0.25)
    down, up = (8, 16) if right else (2, 4)     # WM_R/U*BUTTON*
    u.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.06)
    u.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.5)


def key(name: str, times: int = 1) -> None:
    """敲键。菜单每次弹的位置都差几个像素，用键盘选条目比猜坐标稳。"""
    code = {"down": 0x28, "up": 0x26, "left": 0x25, "right": 0x27,
            "enter": 0x0D, "esc": 0x1B}[name]
    for _ in range(times):
        u.keybd_event(code, 0, 0, 0)
        time.sleep(0.03)
        u.keybd_event(code, 0, 2, 0)
        time.sleep(0.10)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "hover-right":
        # 右边缘竖直居中往里挪一点点，唤醒抽屉（用物理尺寸才对得上截图）
        move(PW - 2, PH // 2)
        shot("hover")
    elif cmd == "shot":
        shot(rest[0])
    elif cmd == "move":
        move(int(rest[0]), int(rest[1]))
    elif cmd == "click":
        click(int(rest[0]), int(rest[1]),
              right=(len(rest) > 2 and rest[2] == "r"))
    elif cmd == "key":
        key(rest[0], int(rest[1]) if len(rest) > 1 else 1)
    elif cmd == "screen":
        print("逻辑屏尺寸:", SW, "x", SH, " 物理:", PW, "x", PH,
              " 缩放:", round(SCALE, 3))
        print("（click/move 收的就是截图上的像素坐标，内部已换算）")
    else:
        print("不认识的命令:", cmd)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
