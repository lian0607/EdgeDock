# -*- coding: utf-8 -*-
"""实机验证：在真实桌面上按住图标拖动，确认排序真的生效。

跟前两个脚本不同，这个检验的是最后一层 —— Windows 把「按住左键移动」的
消息真的送到了 Qt 窗口里（进程内发事件是测不出这一点的）。

它用 EDGEDOCK_CONFIG 指到临时配置来启动一份 EdgeDock，所以**不会改动
你自己那份 config.json**。跑之前会先关掉正在运行的实例，跑完再拉起来。

用法：.venv\\Scripts\\python.exe tools\\check_reorder_live.py
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from edgedock import config as cfg_mod
from edgedock import winapi
from edgedock.drawer import Geo

PYW = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
MAIN = os.path.join(ROOT, "main.pyw")

user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

app = QGuiApplication([])
screen = QGuiApplication.primaryScreen()
screen_geo = screen.geometry()
DPR = screen.devicePixelRatio()

TMP = tempfile.mkdtemp(prefix="edgedock_live_")
ok = True


def check(label, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", label, extra))


def phys(x_logical, y_logical):
    return int(round(x_logical * DPR)), int(round(y_logical * DPR))


def move_to(x_logical, y_logical):
    px, py = phys(x_logical, y_logical)
    user32.SetCursorPos(px, py)
    time.sleep(0.03)


def kill_all():
    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
    time.sleep(1.0)


def launch(cfg_path: str | None):
    env = dict(os.environ)
    if cfg_path:
        env["EDGEDOCK_CONFIG"] = cfg_path
    else:
        env.pop("EDGEDOCK_CONFIG", None)
    p = subprocess.Popen([PYW, MAIN], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5.5)
    return p


def order_of(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return [os.path.splitext(os.path.basename(i["path"]))[0]
            for i in data.get("items", [])]


def main() -> int:
    # ---- 临时配置：6 个假快捷方式 -----------------------------------------
    desk = os.path.join(TMP, "desk")
    os.makedirs(desk, exist_ok=True)
    items = []
    for nm in "ABCDEF":
        p = os.path.join(desk, "实机%s.lnk" % nm)
        winapi.create_lnk(p, os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                          "notepad.exe"), "", "", "live")
        items.append({"path": p, "name": "实机%s" % nm, "args": ""})
    cfg_path = os.path.join(TMP, "config.json")
    base = dict(cfg_mod.DEFAULTS)
    base.update({"items": items, "theme": "light", "pin": True,
                 "icon_size": 40, "padding": 13, "gap": 4,
                 "seeded": True,
                 # 置 true：让 app 的 sync_autostart 认为无需改动注册表，
                 # 免得测试顺手把使用者的开机自启关掉
                 "autostart": True})
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False)

    before = order_of(cfg_path)
    print("起始顺序: %s" % before)

    # ---- 几何（和 app 里一致）-------------------------------------------
    cfg = cfg_mod.Config(cfg_path)
    g = Geo(cfg)
    n = len(items)
    wr = g.window_rect(n)
    step = g.btn + g.gap
    content = g.content_len(n)
    base_along = (g.panel_len(n) - (content - 2 * g.pad)) // 2
    print("面板 %dx%d @ (%d,%d)  槽位间距 %d"
          % (g.panel_len(n), g.thick, wr.x(), wr.y(), step))

    kill_all()
    move_to(screen_geo.width() * 0.5, screen_geo.height() * 0.7)
    proc = launch(cfg_path)

    try:
        # ---- 触发展开 ------------------------------------------------------
        move_to(screen_geo.width() // 2, 0)
        time.sleep(1.5)

        def slot_center_global(i):
            """第 i 个槽位中心的全局逻辑坐标。"""
            along = base_along + i * step + g.btn // 2
            cross = g.pad + (g.thick - 2 * g.pad - g.btn) // 2
            if g.horizontal:
                return wr.x() + along, wr.y() + cross + g.btn // 2
            return wr.x() + cross + g.btn // 2, wr.y() + along

        sx, sy = slot_center_global(1)
        ex, ey = slot_center_global(4)

        # ---- 真·按住拖动 ---------------------------------------------------
        move_to(sx, sy)
        time.sleep(0.25)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.08)
        steps = 10
        for k in range(1, steps + 1):
            t = k / float(steps)
            move_to(sx + (ex - sx) * t, sy + (ey - sy) * t)
        time.sleep(0.35)
        img = screen.grabWindow(0).toImage()
        out = os.path.join(ROOT, "_shots")
        os.makedirs(out, exist_ok=True)
        crop = img.copy(int(wr.x() * DPR), int(wr.y() * DPR),
                        int(wr.width() * DPR), int((g.thick + 40) * DPR))
        crop = crop.scaled(int(crop.width() * 1.6), int(crop.height() * 1.6),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        crop.save(os.path.join(out, "R_live_dragging.png"), "PNG")
        print("  拖动中的实机截图 -> _shots\\R_live_dragging.png")
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(1.0)

        after = order_of(cfg_path)
        print("\n拖动后顺序: %s" % after)
        # 拖的是第 1 个「实机B」，落到第 4 位 -> A C D E B F
        want = ["实机A", "实机C", "实机D", "实机E", "实机B", "实机F"]
        check("实机拖动改变了顺序", after != before, "%s -> %s" % (before, after))
        check("落点是第 4 位（ACDEBF）", after == want, after)
        check("项目数没变", len(after) == n, "-> %d" % len(after))

        # 窗口没被拖坏
        still = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pythonw.exe"],
                               capture_output=True).stdout
        check("程序还活着", b"pythonw.exe" in still)
    finally:
        proc.terminate()
        kill_all()
        # 把使用者自己的实例拉回来
        launch(None)
        print("已重新启动正式实例（用你自己的 config.json）")
        shutil.rmtree(TMP, ignore_errors=True)

    print("\n结果: %s" % ("通过 —— 真实拖动能排序" if ok else "失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
