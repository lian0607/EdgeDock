# -*- coding: utf-8 -*-
"""全屏让路的**外部**验收：真开一个全屏窗口，看正在运行的 EdgeDock 藏不藏。

和 check_game_mode.py 不同，这个不碰进程内部 —— 只从窗口层面观察，
所以测的就是用户实际在跑的那个实例。

流程：记下边栏窗口 -> 开全屏 -> 等 1.2s -> 边栏应不可见 -> 关全屏 -> 等 1.5s -> 回来。

用法：.venv\\Scripts\\python.exe tools\\check_game_live.py
（屏幕会被全屏窗口占住两三秒，属正常）
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

u = ctypes.WinDLL("user32", use_last_error=True)
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.c_void_p]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def _exe_name(pid: int) -> str:
    """pid 对应的可执行文件名。用来把 EdgeDock 的 pythonw 从别的 Qt 程序里挑出来。

    （微信、Snipaste 这些也是 Qt 写的窗口类名一样，只看类名会认错。）
    """
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                              wintypes.LPWSTR,
                                              ctypes.POINTER(wintypes.DWORD)]
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        n = wintypes.DWORD(512)
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return ""
        return buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        k32.CloseHandle(h)


def windows_of_other_pythonw() -> list[tuple[int, int, str, str, bool, RECT]]:
    """列出 EdgeDock 进程（pythonw）的 Qt 窗口。"""
    found = []

    def cb(hwnd, _):
        pid = wintypes.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return True
        cls = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cls, 256)
        if not cls.value.startswith("Qt"):
            return True
        if not _exe_name(pid.value).startswith("pythonw"):
            return True
        txt = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(hwnd, txt, 256)
        rc = RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rc))
        found.append((hwnd, pid.value, cls.value, txt.value,
                      bool(u.IsWindowVisible(hwnd)), rc))
        return True

    u.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def drawer_hwnd() -> int:
    """边栏 = 标题为 EdgeDock 的那个 Qt 工具窗口（设置窗口叫「EdgeDock 设置」）。"""
    for hwnd, _pid, _cls, txt, _vis, _rc in windows_of_other_pythonw():
        if txt == "EdgeDock":
            return hwnd
    # 标题万一变了，退而求其次：又窄又长的那个
    for hwnd, _pid, _cls, txt, _vis, rc in windows_of_other_pythonw():
        if "TrayIcon" in txt:
            continue
        if width_narrow(rc.right - rc.left, rc.bottom - rc.top):
            return hwnd
    return 0


def width_narrow(w: int, h: int) -> bool:
    return (0 < w <= 400 and h > 200) or (0 < h <= 400 and w > 200)


app = None


def main() -> int:
    global app
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    app = QApplication([])

    before = drawer_hwnd()
    print("边栏窗口:", hex(before) if before else "没找到（EdgeDock 在跑吗？）")
    if not before:
        return 1
    print("  现在可见:", bool(u.IsWindowVisible(before)))

    # --- 开一个无边框全屏窗口冒充游戏 ---
    scr = app.primaryScreen().geometry()
    game = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    game.setStyleSheet("background:#101418;")
    game.setGeometry(scr)
    game.show()
    game.raise_()
    game.activateWindow()
    end = time.time() + 1.2
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    hidden = not u.IsWindowVisible(before)
    print("全屏后边栏可见: %s  -> %s" % (not hidden, "藏起来了 ✅" if hidden else "没反应 ❌"))

    game.close()
    end = time.time() + 1.6
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)
    back = bool(u.IsWindowVisible(before))
    print("退出全屏后可见: %s  -> %s" % (back, "回来了 ✅" if back else "没回来 ❌"))

    ok = hidden and back
    print("\n结论:", "全屏让路工作正常 ✅" if ok else "有问题 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
