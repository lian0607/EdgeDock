# -*- coding: utf-8 -*-
"""核对两项新功能：主题「跟随系统」 + 设置窗口的最小化联动。

跑的是真程序（EdgeDock 主控 + 抽屉 + 设置窗口），不是替身，
所以结果就是实际行为；配置写到临时文件，不碰使用者自己的设置。

用法：.venv\\Scripts\\python.exe tools\\check_theme_minimize.py
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
TMP = tempfile.mkdtemp(prefix="edgedock_theme_")
os.environ["EDGEDOCK_CONFIG"] = os.path.join(TMP, "config.json")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from edgedock import config as cfg_mod
from edgedock import theme as theme_mod
from edgedock import winapi
from edgedock.app import EdgeDock

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

fails: list[str] = []
total = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global total
    total += 1
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("   " + extra) if extra else ""))
    if not cond:
        fails.append(name)


def pump(sec: float = 0.6) -> None:
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)


def topmost(widget) -> bool:
    ex = winapi._get_long(winapi.wintypes.HWND(int(widget.winId())), GWL_EXSTYLE)
    return bool(ex & WS_EX_TOPMOST)


def seed_config() -> None:
    """把使用者的配置抄一份到临时文件，只改我们需要摆弄的项。"""
    data = dict(cfg_mod.Config().data)
    data["theme"] = "dark"
    data["pin"] = False            # 固定展开会挡住自动收起，松手的效果就看不出来
    data["hide_delay"] = 300
    data["trigger_px"] = 1
    with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def main() -> int:
    seed_config()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    winapi.ensure_com()

    dock = EdgeDock(app)
    pump(0.5)

    # ---- 1. 主题解析 ----
    print("\n[1] 主题「跟随系统」")
    sys_now = theme_mod.system_theme()
    check("system_theme() 有结果", sys_now in ("dark", "light"), "实际=%s" % sys_now)
    check("resolve('system') == 现问系统", theme_mod.resolve("system") == sys_now)
    check("resolve('light') 不被系统带跑", theme_mod.resolve("light") == "light")
    check("resolve('dark') 不被系统带跑", theme_mod.resolve("dark") == "dark")
    check("resolve('bogus') 兜底 dark", theme_mod.resolve("bogus") == "dark")
    check("get('system') 就是系统那套",
          theme_mod.get("system")["name"] == sys_now)

    dock.cfg["theme"] = theme_mod.SYSTEM
    dock.apply_settings()
    pump(0.3)
    check("抽屉配色 = 跟随系统的结果",
          dock.t["name"] == sys_now and dock.drawer.t["name"] == sys_now,
          "抽屉=%s" % dock.drawer.t["name"])

    # ---- 2. 系统广播 ----
    print("\n[2] 系统配色变更广播的处理")
    calls = []
    real = dock.apply_settings
    dock.apply_settings = lambda: (calls.append(1), real())[1]
    dock._on_system_theme()
    check("配色没真变时不重画", not calls, "重画 %d 次" % len(calls))
    dock.cfg["theme"] = "light"
    dock._on_system_theme()
    check("不是「跟随系统」时也不动", not calls, "重画 %d 次" % len(calls))
    dock.apply_settings = real
    # 上面为了验证守卫把主题临时改成了 light，这里放回 system，
    # 免得后面新建的设置窗口带着错的主题按钮状态
    dock.cfg["theme"] = theme_mod.SYSTEM
    dock.apply_settings()
    pump(0.3)

    # ---- 3. 设置窗口 && 最小化 ----
    print("\n[3] 设置窗口最小化联动")
    dock.open_settings()
    dlg = dock.settings_dlg
    pump(0.4)
    check("窗口已显示", bool(dlg and dlg.isVisible()))
    check("带最小化按钮",
          bool(dlg.windowFlags() & Qt.WindowMinimizeButtonHint))
    check("打开设置 → 抽屉被按住", dock.drawer.hold_open is True)
    check("打开设置 → 抽屉让出置顶", topmost(dock.drawer) is False)

    dlg.showMinimized()
    pump(0.5)
    check("最小化 → 状态与信号一致", dlg.minimized is True and dlg.isMinimized())
    check("最小化 → 抽屉松开", dock.drawer.hold_open is False)
    check("最小化 → 抽屉恢复置顶", topmost(dock.drawer) is True)

    dlg.showNormal()
    pump(0.5)
    check("还原 → 状态已复位", dlg.minimized is False)
    check("还原 → 抽屉又按住", dock.drawer.hold_open is True)
    check("还原 → 再次让出置顶", topmost(dock.drawer) is False)

    # 从托盘菜单唤回：最小化状态下再 open_settings() 应当能拉回来
    dlg.showMinimized()
    pump(0.4)
    dock.open_settings()
    pump(0.4)
    check("托盘再唤 → 窗口已还原", dlg.isMinimized() is False and dlg.isVisible())
    check("托盘再唤 → 抽屉重新按住", dock.drawer.hold_open is True)

    # ---- 4. 面板上真的点得到「跟随系统」 ----
    print("\n[4] 设置面板里的主题按钮")
    theme_labels = {"跟随系统", "深色", "浅色"}
    by_text = {b.text(): b for b in dlg.findChildren(QPushButton)
               if b.objectName() == "Seg" and b.text() in theme_labels}
    check("三个主题选项都在", theme_labels <= set(by_text),
          "实际=%s" % sorted(by_text))
    # 别处的分段按钮（吸附到 / 沿边位置）也共用 #Seg，按文字挑出主题这一组
    checked = {t for t, b in by_text.items() if b.isChecked()}
    check("主题组选中「跟随系统」", checked == {"跟随系统"},
          "选中=%s" % sorted(checked))

    by_text["深色"].click()
    pump(0.5)
    check("点「深色」→ 配置生效", dock.cfg["theme"] == "dark")
    check("点「深色」→ 抽屉换肤", dock.drawer.t["name"] == "dark")
    check("点「深色」→ 设置窗口也换肤", dlg.t["name"] == "dark")

    by_text["跟随系统"].click()
    pump(0.5)
    check("点回「跟随系统」→ 配置生效", dock.cfg["theme"] == "system")
    check("点回「跟随系统」→ 抽屉按系统配色",
          dock.drawer.t["name"] == sys_now, "抽屉=%s" % dock.drawer.t["name"])

    # ---- 5. 关闭设置 ----
    print("\n[5] 关闭设置窗口")
    # 最小化状态下直接关：Qt 会先发 finished、再补一条「已不最小化」，
    # 那条迟到的信号要是照单全收，抽屉就被按住了放不开
    dlg.showMinimized()
    pump(0.4)
    dlg.close()
    pump(0.5)
    check("最小化下关掉 → 引用已清", dock.settings_dlg is None)
    check("最小化下关掉 → 抽屉没被按住",
          dock.drawer.hold_open is False and topmost(dock.drawer) is True)

    dock.open_settings()
    dlg = dock.settings_dlg
    pump(0.4)
    check("还能重新打开", bool(dlg and dlg.isVisible() and not dlg.isMinimized()))
    dlg.accept()
    pump(0.5)
    check("完成后引用已清", dock.settings_dlg is None)
    check("完成后抽屉归位（松开 + 置顶）",
          dock.drawer.hold_open is False and topmost(dock.drawer) is True)

    dock.quit()
    pump(0.3)
    print("\n%s：共 %d 项，失败 %d 项"
          % ("全部通过 ✅" if not fails else "有失败项 ❌", total, len(fails)))
    if fails:
        for n in fails:
            print("   - %s" % n)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
