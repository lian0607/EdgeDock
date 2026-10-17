# -*- coding: utf-8 -*-
"""选择器勾选状态的**视觉**回归（必须在真实渲染平台上跑）。

背景：之前所有断言都只查 ``item.checkState()``，状态翻没翻都知道，
但屏幕上勾没勾**长得一模一样** —— 用户看到的就是「点了没反应」。
离屏渲染走的是另一套 style，会画出对勾，反而测不出这个问题，所以这个
脚本故意不设 QT_QPA_PLATFORM，直接开真窗口、抓像素。

用法：.venv\\Scripts\\python.exe tools\\check_picker_visual.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_tmp = tempfile.mkdtemp(prefix="edgedock_vis_")
os.environ["EDGEDOCK_CONFIG"] = os.path.join(_tmp, "config.json")
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import Qt                    # noqa: E402
from PySide6.QtWidgets import QApplication      # noqa: E402

from edgedock import config as cfg_mod          # noqa: E402
from edgedock import theme as theme_mod         # noqa: E402
from edgedock.icons import IconStore            # noqa: E402
from edgedock.settings import AppPicker         # noqa: E402

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (name, detail))


def pump(app, n: int = 20) -> None:
    for _ in range(n):
        app.processEvents()
        time.sleep(0.02)


def grab_states(theme: str, app) -> tuple[list[list[tuple]], list[list[tuple]]]:
    """返回 (未勾选行像素, 已勾选行像素)，各自是二维颜色表。"""
    with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
        json.dump({"items": [], "hide_sys": False, "seeded": True,
                   "theme": theme}, fh, ensure_ascii=False)
    dlg = AppPicker(cfg_mod.Config(), IconStore(os.path.join(_tmp, "cache", theme)))
    dlg.move(40, 40)
    dlg.show()
    dlg.raise_()
    pump(app, 40)
    lst = dlg.list
    row = lst.item(0)
    rect = lst.visualItemRect(row)
    out = []
    for state in (Qt.Unchecked, Qt.Checked):
        row.setCheckState(state)
        pump(app)
        img = lst.viewport().grab(rect).toImage()
        # 只取行首那 30 个逻辑 px（指示器所在区域），逐点取色
        w = min(img.width(), int(30 * dlg.devicePixelRatioF()))
        px = [[img.pixelColor(x, y).getRgb()[:3]
               for x in range(w)] for y in range(img.height())]
        out.append(px)
    dlg.close()
    pump(app, 10)
    return out[0], out[1]


def color_diff(a, b) -> int:
    n = 0
    for ya, yb in zip(a, b):
        for ca, cb in zip(ya, yb):
            if abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2]) > 24:
                n += 1
    return n


def accent_hits(px, accent) -> int:
    import re
    hexa = accent.name() if hasattr(accent, "name") else str(accent)
    m = re.match(r"#(..)(..)(..)", hexa)
    if not m:
        return 0
    ar, ag, ab = (int(m.group(i), 16) for i in (1, 2, 3))
    n = 0
    for row in px:
        for c in row:
            if (abs(c[0] - ar) + abs(c[1] - ag) + abs(c[2] - ab)) < 60:
                n += 1
    return n


app = QApplication([])

for theme in ("light", "dark"):
    t = theme_mod.get(theme)
    print("== 主题 %s ==" % theme)
    off, on = grab_states(theme, app)
    d = color_diff(off, on)
    # 旧代码（没有指示器样式）实测差异只有 ~57 个像素，都是反锯齿噪点；
    # 现在勾上是一整块主题色，差异在 300 以上。阈值取 150 两头都稳。
    check("勾选前后画面明显不同（不能是同一个空框）", d > 150,
          "差异像素 %d（旧代码约 57）" % d)
    check("勾上后出现主题色块", accent_hits(on, t["accent"]) > 40,
          "主题色像素 %d（accent=%s）" % (accent_hits(on, t["accent"]), t["accent"]))
    check("未勾选时没有主题色块", accent_hits(off, t["accent"]) < 10,
          "主题色像素 %d" % accent_hits(off, t["accent"]))

print("\n%s：共 %d 项，失败 %d 项" % (
    "全部通过 ✅" if FAIL == 0 else "有失败 ❌", PASS + FAIL, FAIL))
sys.exit(1 if FAIL else 0)
