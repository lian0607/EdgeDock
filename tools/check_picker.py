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
# 控制面板来源的条目走 path（不再有 appid），筛「池里第一个非系统工具」即可
SAMPLE = next(a for a in POOL if not apps_mod.is_system_tool(a))


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
    {"path": SAMPLE.get("path", ""), "appid": SAMPLE.get("appid", ""),
     "name": SAMPLE["name"]},
    dict(GREEN),     # 池外条目：路径是编的，scan_apps 里不会有
])
dlg = picker(cfg)
check("池内条目按键勾上", row_of(dlg, SAMPLE["name"]).checkState() == Qt.Checked)
check("池外条目不在列表里", row_of(dlg, "GreenTool") is None)

print("== 3. 全不选 + 确定 -> 拦截（回答「否」） ==")
# 两条都是池内条目：全不选之后确定，列表会清空，必须被拦截问一句
SAMPLE2 = next(a for a in POOL if a is not SAMPLE
               and not apps_mod.is_system_tool(a))
cfg = fresh_config([
    {"path": SAMPLE.get("path", ""), "appid": SAMPLE.get("appid", ""),
     "name": SAMPLE["name"]},
    {"path": SAMPLE2.get("path", ""), "appid": SAMPLE2.get("appid", ""),
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

print("== 8. 已加入的程序：路径对得上就算「已勾选」 ==")
# 名单里给的是「开始」菜单那个 .lnk，抽屉里存的往往是 exe 本体。
# 只比 path 会让加过的程序显示成没加过，再勾一次就多出一条重复项。
LNK_APP = next((a for a in POOL
                if (a.get("path") or "").lower().endswith(".lnk")
                and a.get("target")), None)
if LNK_APP:
    cfg8 = fresh_config([{"path": LNK_APP["target"], "name": "老名字 1.0"}])
    dlg8 = picker(cfg8)
    item8 = row_of(dlg8, LNK_APP["name"])
    check("按真实目标认出已加入", item8 is not None
          and item8.checkState() == Qt.Checked,
          "" if item8 is None else str(item8.checkState()))
else:
    print("  SKIP  这台机器上没有「.lnk 入口」的样本")

print("== 9. 确定时抽屉顺序原样不动 ==")
# 之前把「池外条目」整体提到最前、池内条目挪到后面，用户排好的顺序每次确定都被打乱
TWO = [a for a in POOL if not apps_mod.is_system_tool(a)][:3]
if len(TWO) >= 2:
    later = TWO[2] if len(TWO) > 2 else None
    before_items = [{"path": TWO[0]["path"], "name": TWO[0]["name"]},
                    dict(GREEN),
                    {"path": TWO[1]["path"], "name": TWO[1]["name"]}]
    if later:
        before_items.insert(1, {"path": later["path"], "name": later["name"]})
    cfg9 = fresh_config(before_items)
    dlg9 = picker(cfg9)
    dlg9._accept()                      # 什么都不改，直接确定
    after9 = [it["name"] for it in cfg_mod.Config().items]
    check("顺序与确定前完全一致",
          after9 == [i["name"] for i in before_items],
          "%s -> %s" % ([i["name"] for i in before_items], after9))

print("== 10. 取消勾选 = 移出抽屉，其余位置不动 ==")
cfg10 = fresh_config([
    {"path": TWO[0]["path"], "name": TWO[0]["name"]},
    dict(GREEN),
    {"path": TWO[1]["path"], "name": TWO[1]["name"]},
])
dlg10 = picker(cfg10)
row_of(dlg10, TWO[0]["name"]).setCheckState(Qt.Unchecked)
dlg10._accept()
after10 = [it["name"] for it in cfg_mod.Config().items]
check("取消勾选的那条被移出", TWO[0]["name"] not in after10, str(after10))
check("其余条目顺序不变",
      after10 == [GREEN["name"], TWO[1]["name"]], str(after10))

print("== 11. 老配置（只有应用标识）照样能取消勾选 ==")
# 那批条目的键是应用标识、根本不是文件路径，路径索引永远对不上。只靠名字才
# 认得出 —— 之前这种条目在「取消勾选 / 全不选」之后还赖在抽屉里，用户看到
# 的就是「勾选改了但没生效」。
LEGACY = next((a["name"] for a in POOL
               if sum(1 for b in POOL
                      if apps_mod.same_name(a["name"], b["name"])) == 1),
              SAMPLE["name"])
cfg11 = fresh_config([{"appid": "legacy-id", "name": LEGACY}])
dlg11 = picker(cfg11)
item11 = row_of(dlg11, LEGACY)
check("老条目显示成已勾选",
      item11 is not None and item11.checkState() == Qt.Checked)
dlg11._set_all(Qt.Unchecked)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
dlg11._accept()
left11 = [it["name"] for it in cfg_mod.Config().items]
check("取消勾选后真的移出抽屉", left11 == [], str(left11))

print("\n%s：共 %d 项，失败 %d 项" % (
    "全部通过 ✅" if FAIL == 0 else "有失败 ❌", PASS + FAIL, FAIL))
sys.exit(1 if FAIL else 0)
