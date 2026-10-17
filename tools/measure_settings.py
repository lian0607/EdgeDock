# -*- coding: utf-8 -*-
"""临时：量一下设置窗口里各控件的真实几何，调布局用。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (QApplication, QComboBox, QFrame, QLabel,
                               QListWidget, QPushButton, QScrollArea, QSlider)

from edgedock import config as cfg_mod
from edgedock.icons import IconStore
from edgedock.settings import SettingsDialog

TMP = tempfile.mkdtemp(prefix="edgedock_measure_")


def pump(seconds=1.0):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.02)


def main():
    app = QApplication([])
    live = cfg_mod.Config()
    path = os.path.join(TMP, "cfg.json")
    data = dict(live.data)
    data["theme"] = "light"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    cfg = cfg_mod.Config(path)
    store = IconStore(cfg_mod.CACHE_DIR)

    dlg = SettingsDialog(cfg, store)
    dlg.show()
    pump(1.2)

    print("对话框 %dx%d" % (dlg.width(), dlg.height()))
    area = dlg.findChild(QScrollArea)
    bar = area.verticalScrollBar()
    print("滚动区 viewport 高 %d ; 内容高 %d ; 需要滚动: %s"
          % (area.viewport().height(), area.widget().sizeHint().height(),
             bar.maximum() > 0))
    print("滚动条最大值 %d (0 = 不滚动)" % bar.maximum())

    print("\n-- 滑杆 --")
    for s in dlg.findChildren(QSlider):
        p = s.mapTo(dlg, QPoint(0, 0))
        print("  x=%-4d y=%-4d w=%-4d h=%-4d val=%s"
              % (p.x(), p.y(), s.width(), s.height(), s.value()))

    print("\n-- 数值读数 / 名称标签（同一 x 说明对齐了）--")
    seen = set()
    for lab in dlg.findChildren(QLabel):
        p = lab.mapTo(dlg, lab.rect().topLeft())
        if p.y() in seen:
            continue
        seen.add(p.y())
        t = lab.text()
        if t and t not in ("边缘抽屉",):
            print("  y=%-4d x=%-4d w=%-4d  %s" % (p.y(), p.x(), lab.width(), t))

    print("\n-- 组合框 / 列表 / 卡片 --")
    for w in dlg.findChildren(QComboBox):
        p = w.mapTo(dlg, w.rect().topLeft())
        print("  combo  x=%-4d y=%-4d w=%d" % (p.x(), p.y(), w.width()))
    for w in dlg.findChildren(QListWidget):
        p = w.mapTo(dlg, w.rect().topLeft())
        print("  list   x=%-4d y=%-4d w=%-4d h=%d"
              % (p.x(), p.y(), w.width(), w.height()))
    names = {id(w): n for n, w in (("吸", None),)}
    for card in dlg.findChildren(QFrame):
        if card.objectName() not in ("Card", "FootLine"):
            continue
        p = card.mapTo(dlg, card.rect().topLeft())
        print("  %-9s x=%-4d y=%-4d w=%-4d h=%d"
              % (card.objectName(), p.x(), p.y(), card.width(), card.height()))
    for b in dlg.findChildren(QPushButton):
        p = b.mapTo(dlg, b.rect().topLeft())
        print("  btn %-12s x=%-4d y=%-4d w=%-4d" % (b.text(), p.x(), p.y(),
                                                    b.width()))

    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
