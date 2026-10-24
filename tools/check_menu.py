# -*- coding: utf-8 -*-
"""核对右键菜单不会跟着抽屉一起消失。

修的是这个毛病：菜单挂在抽屉窗口上，是它的子窗口。鼠标从图标挪到菜单上
（已经离开面板），hide_delay 一到抽屉自动收起，菜单跟着没影 —— 手慢一点，
右键菜单就是「闪一下」。

这条测试在**旧写法上会挂**：控制组把 _popup 换回直接 menu.exec，探针会看到
hold_open=False、抽屉被收掉。两边的对照都留着，防止以后谁把按住又删了。

用法：.venv\\Scripts\\python.exe tools\\check_menu.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须在 import edgedock.config 之前设好：CONFIG_PATH 是模块导入时定死的
TMP = tempfile.mkdtemp(prefix="edgedock_menu_")
os.environ["EDGEDOCK_CONFIG"] = os.path.join(TMP, "config.json")

from PySide6.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QContextMenuEvent    # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from edgedock import config as cfg_mod          # noqa: E402
from edgedock import theme as theme_mod         # noqa: E402
from edgedock import winapi                     # noqa: E402
from edgedock.drawer import DrawerWindow        # noqa: E402
from edgedock.icons import IconStore            # noqa: E402

fails: list[str] = []
total = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global total
    total += 1
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("   " + extra) if extra else ""))
    if not cond:
        fails.append(name)


def pump(sec: float = 0.3) -> None:
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)


def flush_deletes() -> None:
    """把 deleteLater 的活干完。

    processEvents 不处理 DeferredDelete，只有事件循环回到顶层才做；
    测试里没有真事件循环，得自己送一把，否则会误判成「菜单在攒」。
    """
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def seed_config() -> None:
    data = dict(cfg_mod.Config().data)
    data["pin"] = False            # 钉住就不会收，测不出东西
    data["hide_delay"] = 300
    # 自己摆一个条目，不去读使用者真实的抽屉内容
    data["items"] = [{"name": "记事本", "path": r"C:\Windows\System32\notepad.exe"}]
    with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


class ProbeMenu(QMenu):
    """真 QMenu，只是把 exec 换掉：不进嵌套循环，好在里面做探针。"""

    def __init__(self, parent, probe):
        super().__init__(parent)
        self.setStyleSheet(theme_mod.menu_qss(parent.t))
        self._probe = probe
        self.executed = 0

    def exec(self, *args, **kwargs) -> int:      # noqa: A003
        self.executed += 1
        self._probe(self)                        # 菜单「开着」的这一刻
        return 0


def old_popup(menu: QMenu, pos) -> None:
    """旧写法：不按住、也不销毁。留着做反证，证明下面几条测得出问题。"""
    menu.exec(pos)


def main() -> int:
    seed_config()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    winapi.ensure_com()

    cfg = cfg_mod.Config()
    dock = DrawerWindow(cfg, IconStore(cfg_mod.CACHE_DIR))
    dock.show()
    dock.expand()
    pump(0.6)
    key = cfg.key(cfg.items[0])
    print("测试条目：%s（共 %d 个）" % (key, len(cfg.items)))

    seen: dict = {}

    def probe(menu: QMenu) -> None:
        """探针：此刻菜单正开着，模拟「鼠标早就离开面板很久了」。"""
        seen["hold"] = dock.hold_open
        seen["texts"] = [a.text() for a in menu.actions() if a.text()]
        dock._away = 10 ** 6                     # 远超 hide_delay
        dock._tick()
        seen["target"] = dock.target
        seen["visible"] = dock.isVisible()

    def install(proc) -> None:
        dock._menu = lambda: ProbeMenu(dock, proc)

    # ---- 1. 控制组：不按住的话，抽屉确实会收 ----
    print("\n[1] 控制组：没按住时（旧写法就是这样）")
    dock.hold_open = False
    dock._away = 10 ** 6
    dock._tick()
    check("鼠标离开太久就自动收起", dock.target < 0.5, "target=%.2f" % dock.target)
    dock.expand()
    # 这里不能 pump：鼠标本来就不在面板上，_tick 过一会儿又会把它收掉
    check("重新展开成功", dock.target > 0.5)

    # ---- 2. 菜单开着时必须按住 ----
    print("\n[2] 图标上的右键菜单（_on_menu）")
    dock.expand()
    install(probe)
    dock._on_menu(key, QPoint(10, 10))
    check("菜单开着时 hold_open 已按住", seen.get("hold") is True)
    check("抽屉没被收掉", seen.get("target", 0) > 0.5,
          "target=%.2f" % seen.get("target", -1))
    check("窗口还看得见", seen.get("visible") is True)
    check("菜单项齐全（设置… / 退出 都在）",
          "设置…" in seen.get("texts", []) and "退出 EdgeDock" in seen.get("texts", []),
          repr(seen.get("texts")))
    check("菜单关掉后松开按住", dock.hold_open is False)
    check("关掉后抽屉仍留在原地", dock.target > 0.5)

    # ---- 3. 设置窗口开着时弹菜单，松手不能把它的按住也松掉 ----
    print("\n[3] 设置窗口正开着（本来就是按住的）")
    dock.hold_open = True
    dock._on_menu(key, QPoint(10, 10))
    check("上一手的按住被还原", dock.hold_open is True)
    dock.hold_open = False

    # ---- 4. 空白处右键（contextMenuEvent）同样按住 ----
    print("\n[4] 抽屉空白处的右键菜单")
    dock.expand()
    seen.clear()
    install(probe)
    ev = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(5, 5), QPoint(5, 5))
    dock.contextMenuEvent(ev)
    check("菜单开着时同样按住", seen.get("hold") is True)
    check("抽屉没被收掉", seen.get("target", 0) > 0.5)
    check("这一份菜单也有设置…/退出", "设置…" in seen.get("texts", []))

    # ---- 5. 菜单用完要销毁，不能每右键一次攒一个 ----
    print("\n[5] 菜单对象的回收")
    flush_deletes()                    # 先把前面几节欠下的销毁做掉
    keep = dock._popup
    before = len(dock.findChildren(QMenu))

    dock._popup = old_popup            # 先看旧写法会不会攒
    for _ in range(3):
        dock._on_menu(key, QPoint(10, 10))
    flush_deletes()
    leaked = len(dock.findChildren(QMenu))
    check("旧写法每右键一次攒一个（说明这条测得出泄漏）", leaked == before + 3,
          "前 %d → 后 %d" % (before, leaked))

    flush_deletes()
    before = len(dock.findChildren(QMenu))
    dock._popup = keep                 # 换回新写法
    for _ in range(3):
        dock._on_menu(key, QPoint(10, 10))
    flush_deletes()
    after = len(dock.findChildren(QMenu))
    check("新写法用完就销毁，数量没涨", after == before, "前 %d → 后 %d" % (before, after))

    # ---- 6. 反证：把 _popup 换回旧写法，第 2 节那几条必须挂 ----
    print("\n[6] 反证：旧写法（直接 menu.exec）会被抓出来")
    dock.expand()
    seen.clear()
    dock._popup = old_popup
    dock._on_menu(key, QPoint(10, 10))
    check("旧写法下 hold_open 还是 False", seen.get("hold") is False)
    check("旧写法下抽屉被收掉（正是用户看到的「菜单闪一下」）",
          seen.get("target", 1) < 0.5, "target=%.2f" % seen.get("target", -1))

    print("\n%s：共 %d 项，失败 %d 项" % (
        "全部通过 ✅" if not fails else "有失败项 ❌", total, len(fails)))
    for f in fails:
        print("   -", f)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
