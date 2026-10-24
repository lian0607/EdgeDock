# -*- coding: utf-8 -*-
"""全屏游戏让路（hide_in_game）自检。

三层：
  1) 判定本身 —— 矩形判定是纯函数，直接喂数；最大化窗口贴的是工作区，
     必须判成「不是全屏」，不然开着最大化浏览器边栏也没了。
  2) 真窗口判定 —— 临时开一个无边框全屏窗口顶到前台，看能不能认出来；
     再开一个带标题栏的普通窗口，确认不会误判。
  3) 抽屉让路 —— set_suspended 之后窗口隐藏、贴边/快捷键都不再唤出，
     恢复后原样回来；EdgeDock._poll_fullscreen 的联动也过一遍。

真窗口那部分必须在真实平台上跑（不设 QT_QPA_PLATFORM）。
用法：.venv\\Scripts\\python.exe tools\\check_game_mode.py
"""
from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import Qt                          # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget    # noqa: E402

from edgedock import winapi                            # noqa: E402

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (name, detail))


def rect(l, t, r, b) -> winapi._RECT:
    x = winapi._RECT()
    x.left, x.top, x.right, x.bottom = l, t, r, b
    return x


def pump(app, sec: float = 0.4) -> None:
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


print("== 1. 矩形覆盖判定 ==")
mon = rect(0, 0, 2560, 1440)
work = rect(0, 0, 2560, 1392)          # 任务栏占掉 48px
check("正正好铺满 -> 全屏", winapi._covers(rect(0, 0, 2560, 1440), mon))
check("差 2px 以内仍算全屏", winapi._covers(rect(2, 1, 2558, 1439), mon))
check("差 40px -> 不是全屏", not winapi._covers(rect(0, 0, 2520, 1440), mon))
check("最大化窗口只贴工作区 -> 不是全屏",
      not winapi._covers(rect(0, 0, 2560, 1392), mon), "浏览器最大化不该误伤")
check("第二块显示器（左置、坐标是负的）也认得出",
      winapi._covers(rect(-1920, 0, 0, 1080), rect(-1920, 0, 0, 1080)),
      "只用相对坐标比较，负坐标不该出问题")

app = QApplication([])

print("== 2. 真实窗口判定 ==")
full = QWidget(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
full.setStyleSheet("background:#2b2b2b;")
scr = app.primaryScreen().geometry()
full.setGeometry(scr)
full.show()
full.raise_()
full.activateWindow()
pump(app, 0.6)
check("无边框全屏窗口被认成全屏", winapi.fullscreen_active(ignore_own=False),
      "active=%s" % winapi.fullscreen_active(ignore_own=False))
check("自家窗口默认被排除（ignore_own=True）",
      not winapi.fullscreen_active())
full.close()
pump(app, 0.3)

normal = QWidget()
normal.setWindowTitle("EdgeDock 普通窗口")
normal.resize(600, 400)
normal.show()
normal.raise_()
normal.activateWindow()
pump(app, 0.6)
check("带标题栏的普通窗口不算全屏", not winapi.fullscreen_active(ignore_own=False))
normal.close()
pump(app, 0.2)

print("== 3. 抽屉让路 ==")
from edgedock import config as cfg_mod                 # noqa: E402
from edgedock.drawer import DrawerWindow               # noqa: E402
from edgedock.icons import IconStore                   # noqa: E402

cfg = cfg_mod.Config()
drawer = DrawerWindow(cfg, IconStore(cfg_mod.CACHE_DIR))
pump(app, 0.3)
check("平时是可见的（收起状态）", drawer.isVisible())

drawer.set_suspended(True)
pump(app, 0.2)
check("让路后窗口隐藏", not drawer.isVisible())
drawer.expand()
pump(app, 0.2)
check("让路后贴边唤出无效（expand 被拒）", drawer.target < 0.01,
      "target=%.2f" % drawer.target)
drawer.toggle()
pump(app, 0.2)
check("让路后快捷键也唤不出来", drawer.target < 0.01,
      "target=%.2f" % drawer.target)
check("让路后轮询已停", not drawer._poll.isActive())

drawer.set_suspended(False)
pump(app, 0.3)
check("退出全屏后窗口回来", drawer.isVisible())
check("轮询也恢复了", drawer._poll.isActive())
drawer.expand()
pump(app, 0.5)
check("退出全屏后能正常唤出", drawer.target > 0.5, "target=%.2f" % drawer.target)

# 钉住（固定展开）状态也要能原样回来
drawer.pinned = True
drawer.set_suspended(True)
pump(app, 0.2)
drawer.set_suspended(False)
pump(app, 0.5)
check("钉住状态退出游戏后仍是展开的", drawer.target > 0.5,
      "target=%.2f" % drawer.target)
drawer.pinned = False
drawer.collapse()
pump(app, 0.4)

print("== 4. EdgeDock 联动 ==")
from edgedock.app import EdgeDock                      # noqa: E402
from PySide6.QtWidgets import QApplication as _QA      # noqa: E402

dock = EdgeDock(app)
pump(app, 0.4)
orig = winapi.fullscreen_active
try:
    winapi.fullscreen_active = lambda *a, **k: True
    dock._poll_fullscreen()
    pump(app, 0.2)
    check("检测到全屏 -> 边栏让路", dock.drawer.suspended
          and not dock.drawer.isVisible())
    winapi.fullscreen_active = lambda *a, **k: False
    dock._poll_fullscreen()
    pump(app, 0.2)
    check("全屏结束 -> 边栏回来", not dock.drawer.suspended
          and dock.drawer.isVisible())

    # 关掉开关就该完全不管全屏的事
    dock.cfg["hide_in_game"] = False
    winapi.fullscreen_active = lambda *a, **k: True
    dock._poll_fullscreen()
    pump(app, 0.2)
    check("开关关掉后不再让路", not dock.drawer.suspended)
    dock.cfg["hide_in_game"] = True
finally:
    winapi.fullscreen_active = orig
    dock._game_timer.stop()
    dock._hotkey_timer.stop()
    dock.tray.hide()
    getattr(dock.drawer, "set_suspended", lambda v: None)(False)
    dock.drawer.close()
    dock.drawer.deleteLater()
    pump(app, 0.2)

drawer.close()
pump(app, 0.2)

print("\n%s：共 %d 项，失败 %d 项" % (
    "全部通过 ✅" if FAIL == 0 else "有失败 ❌", PASS + FAIL, FAIL))
sys.exit(1 if FAIL else 0)
