# -*- coding: utf-8 -*-
"""选择器（AppPicker）自检：勾选状态、防误清空、池外条目保留、系统工具过滤。

全部在**离屏**模式下跑（QT_QPA_PLATFORM=offscreen），不弹窗口、不碰真实鼠标，
配置写在临时文件里，不会动你自己的 config.json。

用法：.venv\\Scripts\\python.exe tools\\check_picker.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须在 import edgedock.config 之前定好配置路径（CONFIG_PATH 是模块级求值的）
_tmp = tempfile.mkdtemp(prefix="edgedock_picker_")
os.environ["EDGEDOCK_CONFIG"] = os.path.join(_tmp, "config.json")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt                      # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox   # noqa: E402

from edgedock import apps as apps_mod              # noqa: E402
from edgedock import config as cfg_mod             # noqa: E402
from edgedock.icons import IconStore               # noqa: E402
from edgedock.settings import AppPicker            # noqa: E402

app = QApplication([])
PASS = FAIL = 0

# 用一个**真实存在**于候选池里的应用当测试样本（假应用id不在池里，测不了勾选）
POOL = apps_mod.scan_apps()
SAMPLE = next(a for a in POOL if not apps_mod.is_system_tool(a) and a["appid"])


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s   %s" % (name, detail))


def fresh_config(items: list) -> cfg_mod.Config:
    with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
        json.dump({"items": items, "hide_sys": True, "seeded": True}, fh,
                  ensure_ascii=False)
    return cfg_mod.Config()


def picker(cfg) -> AppPicker:
    return AppPicker(cfg, IconStore(os.path.join(_tmp, "cache")))


def row_of(dlg: AppPicker, name: str):
    for i in range(dlg.list.count()):
        if dlg.pool[dlg.list.item(i).data(Qt.UserRole)]["name"] == name:
            return dlg.list.item(i)
    return None


GREEN = {"path": r"C:\portable\green.exe", "appid": "", "name": "GreenTool"}

print("== 1. 系统工具识别 ==")
check("按名字认出 Control Panel",
      apps_mod.is_system_tool({"name": "Control Panel", "path": "", "appid": "x"}))
check("普通应用不被误伤",
      not apps_mod.is_system_tool({"name": "某绿色软件", "path": r"C:\sm\app.exe",
                                   "appid": ""}))
check("按开始菜单分组认出系统工具",
      apps_mod.is_system_tool({"name": "whatever", "path":
          r"C:\Start Menu\Programs\Administrative Tools\x.lnk", "appid": ""}))

print("== 2. 初始勾选状态（键匹配 + 名字兜底） ==")
cfg = fresh_config([
    {"path": SAMPLE.get("path", ""), "appid": SAMPLE["appid"],
     "name": SAMPLE["name"]},
    dict(GREEN),     # 池外条目：路径是编的，scan_apps 里不会有
])
dlg = picker(cfg)
check("池内条目按键勾上", row_of(dlg, SAMPLE["name"]).checkState() == Qt.Checked)
check("池外条目不在列表里", row_of(dlg, "GreenTool") is None)

print("== 3. 全不选 + 确定 -> 拦截（回答「否」） ==")
# 两条都是池内条目：全不选之后确定，列表会清空，必须被拦截问一句
SAMPLE2 = next(a for a in POOL if a is not SAMPLE
               and not apps_mod.is_system_tool(a) and a["appid"])
cfg = fresh_config([
    {"path": SAMPLE.get("path", ""), "appid": SAMPLE["appid"],
     "name": SAMPLE["name"]},
    {"path": SAMPLE2.get("path", ""), "appid": SAMPLE2["appid"],
     "name": SAMPLE2["name"]},
])
dlg = picker(cfg)
dlg._set_all(Qt.Unchecked)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
dlg._accept()
cfg2 = cfg_mod.Config()
check("回答「否」-> 条目原样保留", len(cfg2.items) == 2,
      str([(i['name'], i['appid'], i['path']) for i in cfg2.items]))

print("== 4. 同上但回答「是」 -> 真的清空 ==")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
dlg._accept()
cfg3 = cfg_mod.Config()
check("确认真清空", len(cfg3.items) == 0, str(cfg3.items))

print("== 5. 池外条目在重选时不被丢掉 ==")
cfg4 = fresh_config([dict(GREEN)])
dlg2 = picker(cfg4)
row_of(dlg2, SAMPLE["name"]).setCheckState(Qt.Checked)
dlg2._accept()
cfg5 = cfg_mod.Config()
names = [it["name"] for it in cfg5.items]
check("池外条目保留", "GreenTool" in names, str(names))
check("新勾的条目加进来", SAMPLE["name"] in names, str(names))

print("== 4b. 全不选 + 确定 也不动池外条目 ==")
cfg4b = fresh_config([dict(GREEN)])
dlg2b = picker(cfg4b)
dlg2b._set_all(Qt.Unchecked)
dlg2b._accept()
cfg4b_after = cfg_mod.Config()
check("池外条目即使在全不选下也保留",
      [it["name"] for it in cfg4b_after.items] == ["GreenTool"],
      str(cfg4b_after.items))

print("== 6. 隐藏系统工具开关 ==")
dlg3 = picker(cfg5)
hidden = [i for i in range(dlg3.list.count()) if dlg3.list.item(i).isHidden()]
check("默认开启 -> 有条目被隐藏", len(hidden) > 0, "hidden=%d" % len(hidden))
dlg3.chk_sys.setChecked(False)
check("关掉后全部可见",
      all(not dlg3.list.item(i).isHidden() for i in range(dlg3.list.count())))
check("开关状态写进配置", cfg_mod.Config()["hide_sys"] is False)
dlg3.chk_sys.setChecked(True)
check("再开回去也落盘", cfg_mod.Config()["hide_sys"] is True)

print("== 7. 整行点击切换勾选（模拟真实鼠标） ==")
# 复选框原生命中判定在 QSS 列表里会失灵，CheckList 改成整行接管：
# 点行中间（图标/名字区）也必须一脚翻状态 —— 用户不会只点那个小格子
from PySide6.QtTest import QTest                  # noqa: E402

dlg4 = picker(cfg5)
dlg4.show()
row = next(i for i in range(dlg4.list.count())
           if not dlg4.list.item(i).isHidden())
item = dlg4.list.item(row)
before = item.checkState()
rect = dlg4.list.visualItemRect(item)
QTest.mouseClick(dlg4.list.viewport(), Qt.LeftButton, Qt.NoModifier,
                 rect.center())                    # 点行的正中间
check("点行中间一脚切换", item.checkState() != before,
      "before=%s after=%s" % (before, item.checkState()))
QTest.mouseClick(dlg4.list.viewport(), Qt.LeftButton, Qt.NoModifier,
                 rect.center())
check("再点一脚切回来", item.checkState() == before)
dlg4.close()

print("\n%s：共 %d 项，失败 %d 项" % (
    "全部通过 ✅" if FAIL == 0 else "有失败 ❌", PASS + FAIL, FAIL))
sys.exit(1 if FAIL else 0)
