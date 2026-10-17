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
    """模态循环里跑：在多个 x 位置物理点击，看勾选到底翻不翻。"""
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
    mid_y = tl.y() + vr.height() // 2
    REC["row"] = dlg.pool[row.data(Qt.UserRole)]["name"]
    REC["rect_w"] = vr.width()
    before = row.checkState() == Qt.Checked
    REC["before"] = before
    # 逐个偏移量点：14=行首空隙、35=复选框实际画的位置（用户截图实测）、
    # 行宽/2=图标名字区。每个都点两脚，回原位后再试下一个。
    for dx_name, dx in (("x14", 14), ("x35", 35), ("x_mid", vr.width() // 2)):
        physical_click(tl.x() + dx, mid_y)
        first = row.checkState() == Qt.Checked
        REC[dx_name] = "翻" if first != before else "没反应"
        physical_click(tl.x() + dx, mid_y)          # 点回去，恢复原状态
        REC[dx_name + "_back"] = "回" if (row.checkState() == Qt.Checked) == before else "没回"
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
ok = (REC.get("active") is True
      and REC.get("x14") == "翻" and REC.get("x35") == "翻"
      and REC.get("x_mid") == "翻"
      and REC.get("x14_back") == "回" and REC.get("x35_back") == "回"
      and REC.get("x_mid_back") == "回")
print("\n结论: %s" % ("整行点击都能翻勾选 ✅" if ok else "还有位置点不动 ❌"))

dock.settings_dlg and dock.settings_dlg.close()
getattr(dock, "cleanup", lambda: None)()
os.remove(os.environ["EDGEDOCK_CONFIG"])
