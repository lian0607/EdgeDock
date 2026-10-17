# -*- coding: utf-8 -*-
"""真实完整环境下的选择器点击探针（托盘 + 抽屉 + 设置 + 模态 exec）。

和 check_theme_minimize 一样在进程内起完整 EdgeDock，然后走真实的
「设置 → 从系统选择」流程（AppPicker.exec() 模态），在模态循环里用
物理鼠标事件点击复选框，看状态到底翻不翻。

配置抄到临时文件，不碰真实 config.json。
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["EDGEDOCK_CONFIG"] = os.path.join(ROOT, "_probe_real_config.json")

import ctypes                                    # noqa: E402
from PySide6.QtCore import Qt, QTimer            # noqa: E402
from PySide6.QtWidgets import QApplication       # noqa: E402

from edgedock import winapi                      # noqa: E402
from edgedock.app import EdgeDock                # noqa: E402
from edgedock import config as cfg_mod           # noqa: E402
from edgedock.settings import AppPicker          # noqa: E402

# ---- 配置：抄真实配置（保留 items），关掉 pin 方便操作 ----
data = dict(cfg_mod.Config().data)
data["pin"] = False
with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False)

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
winapi.ensure_com()
dock = EdgeDock(app)


def pump(sec: float = 0.6) -> None:
    end = time.time() + sec
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)


u32 = ctypes.windll.user32
REC: dict = {}


def physical_click(lx: int, ly: int) -> None:
    dpr = QApplication.primaryScreen().devicePixelRatio()
    u32.SetCursorPos(int(lx * dpr), int(ly * dpr))
    time.sleep(0.12)
    u32.mouse_event(2, 0, 0, 0, 0)
    u32.mouse_event(4, 0, 0, 0, 0)
    pump(0.4)


def find_picker() -> AppPicker:
    for w in QApplication.topLevelWidgets():
        if isinstance(w, AppPicker) and w.isVisible():
            return w
    return None


def drive() -> None:
    """模态循环里跑：物理点击复选框，然后关掉选择器。"""
    dlg = find_picker()
    if dlg is None:
        REC["error"] = "找不到可见的 AppPicker"
        return
    dlg.raise_()
    dlg.activateWindow()
    pump(0.3)
    REC["active"] = dlg.isActiveWindow()
    lst = dlg.list
    # 找第一行**可见**的条目
    row = None
    for i in range(lst.count()):
        if not lst.item(i).isHidden():
            row = lst.item(i)
            break
    vr = lst.visualItemRect(row)
    tl = lst.mapToGlobal(vr.topLeft())
    name = dlg.pool[row.data(Qt.UserRole)]["name"]
    REC["row"] = name
    REC["before"] = row.checkState() == Qt.Checked
    # 点复选框（探针 1 实测命中区在 x≈12~20）
    physical_click(tl.x() + 14, tl.y() + vr.height() // 2)
    REC["after"] = row.checkState() == Qt.Checked
    REC["current_row"] = lst.currentRow()
    # 再点一次点回去
    physical_click(tl.x() + 14, tl.y() + vr.height() // 2)
    REC["after2"] = row.checkState() == Qt.Checked
    dlg.close()


print("== 起完整应用，打开设置 → 从系统选择 ==")
dock.open_settings()
pump(0.5)
dlg_settings = dock.settings_dlg
print("设置窗口可见:", bool(dlg_settings and dlg_settings.isVisible()))

QTimer.singleShot(2000, drive)
# _pick_apps 里 exec() 会阻塞，drive 在模态循环里被定时器唤起
dlg_settings._pick_apps()
pump(0.3)

print("\n== 结果 ==")
for k, v in REC.items():
    print("  %-12s %s" % (k, v))
ok = (REC.get("active") is True and REC.get("before") is not None
      and REC.get("after") != REC.get("before")
      and REC.get("after2") == REC.get("before"))
print("\n结论: %s" % ("复选框点击正常 ✅" if ok else "复选框点击有问题 ❌"))

dock.settings_dlg and dock.settings_dlg.close()
getattr(dock, "cleanup", lambda: None)()
os.remove(os.environ["EDGEDOCK_CONFIG"])
