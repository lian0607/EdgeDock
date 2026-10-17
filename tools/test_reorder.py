# -*- coding: utf-8 -*-
"""抽屉内拖动排序的端到端测试（进程内发真实的 Qt 鼠标事件）。

校验：
  1. 按下不动 -> 是一次点击（触发启动）而不是拖动
  2. 按住拖到第 4 个槽位松手 -> 该项落到第 4 位，buttons 与 cfg.items 顺序一致
  3. 拖动后又拖回原位松手 -> 顺序不变
  4. 往左拖同样生效
  5. 拖动过程中会画出「占位凹槽」，被拖的图标抬起
产物：_shots\\R_dragging.png（拖动中的面板）

用法：.venv\\Scripts\\python.exe tools\\test_reorder.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

from edgedock import config as cfg_mod
from edgedock import winapi
from edgedock.drawer import DrawerWindow
from edgedock.icons import IconStore

TMP = tempfile.mkdtemp(prefix="edgedock_reorder_")
SHOTS = os.path.join(ROOT, "_shots")
ok = True


def check(label, cond, extra=""):
    global ok
    if not cond:
        ok = False
    print("  [%s] %s %s" % ("PASS" if cond else "FAIL", label, extra))


def names(win):
    return [os.path.splitext(os.path.basename(b.item["path"]))[0]
            for b in win.buttons]


def cfg_names(win):
    return [os.path.splitext(os.path.basename(i["path"]))[0]
            for i in win.cfg.items]


def send(btn, etype, global_pos, button=Qt.LeftButton,
         buttons=Qt.LeftButton, local=None):
    gp = QPointF(global_pos)
    lp = QPointF(local) if local is not None else \
        QPointF(btn.mapFromGlobal(global_pos))
    ev = QMouseEvent(etype, lp, gp, button, buttons, Qt.NoModifier)
    QApplication.sendEvent(btn, ev)
    QApplication.processEvents()


def drag_to(win, btn, target_along, steps=6, shot_at=None):
    """把 btn 沿边拖到面板坐标 target_along 处（横竖两种吸附都支持）。"""
    panel_origin = win.panel.mapToGlobal(QPoint(0, 0))
    b = win.geo.btn
    cross = win.geo.pad + (win.geo.thick - 2 * win.geo.pad - b) // 2

    start_g = panel_origin + win.slot_rect(win.buttons.index(btn)).center()
    if win.geo.horizontal:
        end_g = panel_origin + QPoint(int(target_along), cross + b // 2)
    else:
        end_g = panel_origin + QPoint(cross + b // 2, int(target_along))

    # 按下
    send(btn, QEvent.MouseButtonPress, start_g,
         local=QPointF(b / 2.0, b / 2.0))

    for i in range(1, steps + 1):
        t = i / float(steps)
        gx = int(round(start_g.x() + (end_g.x() - start_g.x()) * t))
        gy = int(round(start_g.y() + (end_g.y() - start_g.y()) * t))
        send(btn, QEvent.MouseMove, QPoint(gx, gy))
        if shot_at is not None and i == shot_at:
            os.makedirs(SHOTS, exist_ok=True)
            pm = win.panel.grab()
            pm.save(os.path.join(SHOTS, "R_dragging.png"), "PNG")
            print("     （拖动中截图已保存 _shots\\R_dragging.png，"
                  "drop_index=%s）" % win.drop_index)
    return end_g


def release(btn, gpos):
    send(btn, QEvent.MouseButtonRelease, gpos, buttons=Qt.NoButton)


def make_window(items, tag, **over):
    """按给定配置起一个 DrawerWindow 并等图标就绪。"""
    cfg_path = os.path.join(TMP, "config_%s.json" % tag)
    base = dict(cfg_mod.DEFAULTS)
    base.update({"items": [dict(i) for i in items], "theme": "light",
                 "pin": True, "icon_size": 40, "padding": 13, "gap": 4,
                 "seeded": True})
    base.update(over)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False)
    cfg = cfg_mod.Config(cfg_path)
    store = IconStore(cfg_mod.CACHE_DIR)
    w = DrawerWindow(cfg, store)
    w.reveal = 1.0
    w.target = 1.0
    w._on_reveal(1.0)
    for _ in range(200):
        QApplication.processEvents()
        if all(store.png_of(i["path"]) for i in items):
            break
        time.sleep(0.02)
    QApplication.processEvents()
    return w


def main() -> int:
    app = QApplication([])

    # ---- 造 6 个假快捷方式 -------------------------------------------------
    desk = os.path.join(TMP, "desk")
    os.makedirs(desk, exist_ok=True)
    items = []
    for i, nm in enumerate("ABCDEF"):
        p = os.path.join(desk, "应用%s.lnk" % nm)
        winapi.create_lnk(p, os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                          "notepad.exe"), "", "", "t")
        items.append({"path": p, "name": "应用%s" % nm, "args": ""})

    cfg_path = os.path.join(TMP, "config_top.json")
    win = make_window(items, "top", edge="top")

    ORDER = ["应用" + c for c in "ABCDEF"]      # 显示名来自 .lnk 文件名
    print("初始顺序: %s" % names(win))
    check("初始顺序 A..F", names(win) == ORDER, names(win))
    check("buttons 与 cfg.items 一致", names(win) == cfg_names(win))
    check("槽位数与图标数一致", win.geo.panel_len(6) == win.geo.content_len(6))

    # ---- 1. 按下不动 -> 点击 ---------------------------------------------
    print("\n== 1. 按下不动松手 = 点击 ==")
    fired = []
    win.buttons[0].activated.connect(lambda p: fired.append(p))
    g = win.panel.mapToGlobal(win.slot_rect(0).center())
    send(win.buttons[0], QEvent.MouseButtonPress, g,
         local=QPointF(win.geo.btn / 2.0, win.geo.btn / 2.0))
    release(win.buttons[0], g)
    QApplication.processEvents()
    check("触发了启动", len(fired) == 1, "fired=%d" % len(fired))
    check("顺序没变", names(win) == ORDER, names(win))
    check("没残留拖动状态", win.drag_index is None)

    # ---- 2. 拖到第 4 个槽位 ----------------------------------------------
    print("\n== 2. 把「应用A」拖到第 4 位 ==")
    step = win.geo.btn + win.geo.gap
    base_along = win._content_base(6)
    target_local_x = base_along + 4 * step + win.geo.btn // 2
    btn = win.buttons[0]
    rel = drag_to(win, btn, target_local_x, steps=8, shot_at=5)
    check("拖动中被标记为 dragging", btn.dragging is True)
    check("drop_index 已更新", win.drop_index == 4, "-> %s" % win.drop_index)
    release(btn, rel)
    QApplication.processEvents()
    want = ["应用" + c for c in "BCDEAF"]
    check("落地顺序 = BCDEAF", names(win) == want, names(win))
    check("与 cfg.items 一致", names(win) == cfg_names(win), cfg_names(win))
    check("状态已复位", win.drag_index is None and win.drop_index is None)
    check("dragging 已复位", btn.dragging is False)

    # 松手后应该有一段滑回动画，最终停在自己的槽位上
    time.sleep(0.25)
    QApplication.processEvents()
    check("滑回后落在正确槽位", btn.pos() == win.slot_rect(4).topLeft(),
          "pos=%s slot=%s" % (btn.pos(), win.slot_rect(4).topLeft()))

    # 磁盘上也要是同样顺序
    with open(cfg_path, "r", encoding="utf-8") as fh:
        disk = json.load(fh)
    disk_names = [os.path.splitext(os.path.basename(i["path"]))[0]
                  for i in disk["items"]]
    check("已落盘", disk_names == want, disk_names)

    # ---- 3. 拖回原位 -> 不变 ---------------------------------------------
    print("\n== 3. 拖走再拖回原位 ==")
    before = names(win)
    btn = win.buttons[4]                       # 现在 A 在第 4 位
    home = base_along + 4 * step + win.geo.btn // 2
    rel = drag_to(win, btn, base_along + 5 * step + win.geo.btn // 2, steps=4)
    rel = drag_to(win, btn, home, steps=4)
    release(btn, rel)
    QApplication.processEvents()
    check("顺序不变", names(win) == before, names(win))

    # ---- 4. 往左拖 --------------------------------------------------------
    print("\n== 4. 把最后一个拖到最前 ==")
    btn = win.buttons[5]
    rel = drag_to(win, btn, base_along + 0 * step + win.geo.btn // 2, steps=8)
    check("drop_index = 0", win.drop_index == 0, "-> %s" % win.drop_index)
    release(btn, rel)
    QApplication.processEvents()
    check("F 到了最前", names(win)[0] == "应用F", names(win))
    check("button 顺序与配置一致", names(win) == cfg_names(win), names(win))

    # ---- 5. 光标停在槽位正中时，凹槽正好在悬浮图标底下 --------------------
    print("\n== 5. 凹槽与悬浮图标对齐 ==")
    b = win.geo.btn
    origin = win.panel.mapToGlobal(QPoint(0, 0))
    btn = win.buttons[0]
    send(btn, QEvent.MouseButtonPress,
         origin + win.slot_rect(0).center(), local=QPointF(b / 2.0, b / 2.0))
    for k in (1, 3, 5):
        g = origin + win.slot_rect(k).center()
        send(btn, QEvent.MouseMove, g)
        check("光标在槽位%d正中 -> drop_index=%d" % (k, k),
              win.drop_index == k, "-> %s" % win.drop_index)
        # 逻辑屏幕宽 1706.67px（2560/1.5），mapToGlobal 往返会有 ±1px 误差，
        # 真实鼠标事件不会有这个问题，这里给 1px 容差即可
        want = win.slot_rect(k).topLeft()
        got = btn.pos()
        check("  图标压住凹槽 (槽位%d)" % k,
              abs(got.x() - want.x()) <= 1 and abs(got.y() - want.y()) <= 1,
              "btn=%s slot=%s" % (got, want))
    release(btn, g)
    QApplication.processEvents()
    time.sleep(0.3)                      # 等滑回动画结束
    QApplication.processEvents()

    # ---- 6. 横向坐标不能串味 ---------------------------------------------
    print("\n== 6. 拖动仅影响沿边方向 ==")
    ys = set()
    for b in win.buttons:
        ys.add(b.y())
    check("所有图标纵向位置一致", len(ys) == 1, "y=%s" % ys)
    xs = [b.x() for b in win.buttons]
    check("横向等距排列",
          all(xs[i + 1] - xs[i] == step for i in range(len(xs) - 1)), xs)
    check("首尾留白对称",
          xs[0] - 0 + (win.geo.panel_len(6) - (xs[-1] + win.geo.btn))
          == 2 * win.geo.pad,
          "左=%d 右=%d" % (xs[0],
                           win.geo.panel_len(6) - (xs[-1] + win.geo.btn)))

    # ---- 7. 吸附在左侧时，纵向拖动排序也要能用 -----------------------------
    print("\n== 7. 左侧吸附（纵向）排序 ==")
    winv = make_window(items, "left", edge="left")
    check("初始顺序", names(winv) == ORDER, names(winv))
    stepv = winv.geo.btn + winv.geo.gap
    basev = winv._content_base(6)
    btnv = winv.buttons[0]
    relv = drag_to(winv, btnv,
                   basev + 4 * stepv + winv.geo.btn // 2, steps=8)
    check("纵向 drop_index = 4", winv.drop_index == 4, "-> %s" % winv.drop_index)
    release(btnv, relv)
    QApplication.processEvents()
    check("纵向落地顺序 = BCDEAF",
          names(winv) == ["应用" + c for c in "BCDEAF"], names(winv))
    check("纵向只动 y",
          len({b.x() for b in winv.buttons}) == 1,
          "x=%s" % {b.x() for b in winv.buttons})
    winv.close()

    # ---- 8. 回归：从桌面拖文件进来仍然能新增 -------------------------------
    print("\n== 8. 回归：桌面拖入新增 ==")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(items[2]["path"])])   # 已存在 -> 应去重
    add_ev = QDropEvent(QPointF(40, 30), Qt.CopyAction, md,
                        Qt.LeftButton, Qt.NoModifier)
    before_n = len(win.cfg.items)
    win.dropEvent(add_ev)
    check("重复项被去重", len(win.cfg.items) == before_n,
          "-> %d" % len(win.cfg.items))

    new_dir = os.path.join(TMP, "一个新文件夹")
    os.makedirs(new_dir, exist_ok=True)
    md2 = QMimeData()
    md2.setUrls([QUrl.fromLocalFile(new_dir)])
    win.dropEvent(QDropEvent(QPointF(40, 30), Qt.CopyAction, md2,
                             Qt.LeftButton, Qt.NoModifier))
    QApplication.processEvents()
    check("新项目被加入", len(win.cfg.items) == before_n + 1,
          "-> %d" % len(win.cfg.items))
    check("rebuild 后顺序与配置一致", names(win) == cfg_names(win), names(win))
    check("拖动状态没被污染", win.drag_index is None and win.drop_index is None)

    # ---- 9. 图标放不下（出现滚动）时，拖到边缘要自动滚动 -------------------
    print("\n== 9. 内容溢出时的自动滚动 ==")
    wins = make_window(items, "small", edge="top")
    wins.rebuild()
    wins.geo.max_len = 200                     # 人为制造溢出（6 个要 334px）
    wins._layout_panel()                       # 注意要在 rebuild 之后再改
    wins.reveal = 1.0
    wins.target = 1.0
    wins._on_reveal(1.0)
    QApplication.processEvents()
    check("内容确实溢出了", wins._content_len > wins.geo.panel_len(6),
          "content=%d panel=%d" % (wins._content_len, wins.geo.panel_len(6)))

    btn = wins.buttons[0]
    edge_along = wins.geo.panel_len(6) - 6     # 贴住面板右端
    rel = drag_to(wins, btn, edge_along, steps=6)
    for _ in range(14):                        # 停在边缘，让它持续滚动
        send(btn, QEvent.MouseMove, rel)
    check("拖到边缘触发了自动滚动", wins._scroll < 0, "-> %s" % wins._scroll)
    check("drop_index 走到了末尾", wins.drop_index == 5,
          "-> %s" % wins.drop_index)
    release(btn, rel)
    QApplication.processEvents()
    check("最后落到了队尾", names(wins)[-1] == "应用A", names(wins))
    check("滚动期间顺序与配置仍一致",
          names(wins) == cfg_names(wins), names(wins))
    wins.close()

    win.close()
    app.quit()
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n结果: %s" % ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
