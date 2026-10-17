# -*- coding: utf-8 -*-
"""把设置窗口真实渲染出来，方便调布局的时候对着看。

产物在 _shots\\ 下：
    S_settings_system.png  主题选「跟随系统」时的设置窗口
    S_settings_light.png   浅色主题的设置窗口
    S_settings_dark.png    深色主题的设置窗口
    S_picker.png           「从桌面挑选应用」窗口
    S_both.png             浅色 / 深色并排的对比图

用法：.venv\\Scripts\\python.exe tools\\preview_settings.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from edgedock import config as cfg_mod
from edgedock.icons import IconStore
from edgedock.settings import SettingsDialog, ShortcutPicker

SHOTS = os.path.join(ROOT, "_shots")
TMP = tempfile.mkdtemp(prefix="edgedock_settings_")


def pump(seconds: float = 1.2) -> None:
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)


def make_cfg(theme: str):
    live = cfg_mod.Config()
    path = os.path.join(TMP, "cfg_%s.json" % theme)
    data = dict(live.data)
    data["theme"] = theme
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return cfg_mod.Config(path)


def shoot(widget, name: str) -> QImage:
    widget.show()
    widget.raise_()
    pump(1.4)
    img = widget.grab().toImage().convertToFormat(QImage.Format_ARGB32)
    os.makedirs(SHOTS, exist_ok=True)
    img.save(os.path.join(SHOTS, name), "PNG")
    print("  -> %s  (%dx%d)" % (name, img.width(), img.height()))
    widget.close()
    widget.deleteLater()
    QApplication.processEvents()
    return img


def main() -> int:
    app = QApplication([])
    store = IconStore(cfg_mod.CACHE_DIR)

    outs = []
    # system 也渲一张：它落在哪个配色取决于当前系统，需要眼见为实
    for theme in ("system", "light", "dark"):
        cfg = make_cfg(theme)
        dlg = SettingsDialog(cfg, store)
        outs.append((theme, dlg.width(), dlg.height(), dlg.t["name"]))
        shoot(dlg, "S_settings_%s.png" % theme)

    cfg = make_cfg("light")
    shoot(ShortcutPicker(cfg), "S_picker.png")

    # 把两个主题横向拼一张，方便一眼对比
    a = QImage(os.path.join(SHOTS, "S_settings_light.png"))
    b = QImage(os.path.join(SHOTS, "S_settings_dark.png"))
    gap = 24
    canvas = QImage(a.width() + b.width() + gap * 3,
                    max(a.height(), b.height()) + gap * 2, QImage.Format_ARGB32)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.drawImage(gap, gap, a)
    p.drawImage(gap * 2 + a.width(), gap, b)
    p.end()
    canvas.save(os.path.join(SHOTS, "S_both.png"), "PNG")

    for theme, w, h, resolved in outs:
        tag = "" if theme == resolved else "  （落在 %s）" % resolved
        print("%-6s 设置窗口 %dx%d%s" % (theme, w, h, tag))
    print("已写入 _shots\\")

    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
