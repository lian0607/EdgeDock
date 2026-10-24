# -*- coding: utf-8 -*-
"""自检：快捷方式没了，图标也得点得开。

关键场景是「桌面上的 .lnk 被删掉/挪走，但程序还装着」。以前点一下什么都不发生
（异常被吞了），现在要求能照着记住的目标把程序拉起来，实在不行就按名字重新定位。

**不会真的启动任何程序** —— 把 winapi.explorer_open 和 winapi.shell_execute
都换成记录器，这样能看清「走的哪条通道、带了什么参数、工作目录对不对」，
又不会在你桌面上弹窗。

用法：.venv\\Scripts\\python.exe tools\\check_launch.py
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import shutil
import struct
import sys
import tempfile

from ctypes import POINTER, byref, c_long, c_void_p, wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 必须在 import edgedock.config 之前设好：CONFIG_PATH 是模块导入时定死的
TMP = tempfile.mkdtemp(prefix="edgedock_launch_")
os.environ["EDGEDOCK_CONFIG"] = os.path.join(TMP, "config.json")

from PySide6.QtWidgets import QApplication                      # noqa: E402

from edgedock import app as app_mod                          # noqa: E402
from edgedock import apps as apps_mod                        # noqa: E402
from edgedock import config as cfg_mod                       # noqa: E402
from edgedock import winapi                                  # noqa: E402

fails: list[str] = []
total = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global total
    total += 1
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name,
                          ("   " + extra) if extra else ""))
    if not cond:
        fails.append(name)


class Recorder:
    """顶替 winapi.explorer_open / winapi.shell_execute，记下走了哪条通道。

    explorer 是主力通道（实测只有它真能把程序拉起来），shell 通道只在
    「条目里额外填了启动参数」时才用得上 —— explorer 递不了参数。
    fail 里的路径模拟「这条通道起不来」，用来验证回退顺序。
    """

    def __init__(self):
        self.calls = []          # [(通道, 路径, 参数, 工作目录)]
        self.fail: set[str] = set()
        self.fail_channel = "*"  # 这些路径只在哪个通道上失败；"*" 表示两条都失败

    def _log(self, channel, path, args="", workdir=""):
        self.calls.append((channel, path, args, workdir))
        if (os.path.normcase(path) in self.fail
                and self.fail_channel in ("*", channel)):
            return False
        return True

    def explorer(self, path):
        return self._log("explorer", path)

    def shell(self, path, args="", workdir=""):
        return self._log("shell", path, args, workdir)

    @property
    def last(self):
        return self.calls[-1] if self.calls else None

    @property
    def tried(self):
        return [os.path.normcase(c[1]) for c in self.calls]

    def only(self, channel: str) -> bool:
        """是不是只走了某一条通道。"""
        return bool(self.calls) and all(c[0] == channel for c in self.calls)

    def clear(self):
        self.calls.clear()


# ----------------------------------------------------------------------
def new_cfg(items: list[dict]):
    path = os.path.join(TMP, "cfg_%d.json" % len(glob.glob(os.path.join(TMP, "cfg_*.json"))))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"items": items, "seeded": True}, fh, ensure_ascii=False)
    return cfg_mod.Config(path)


def sample_start_menu_lnk() -> str | None:
    """随便找一个真实存在的「开始」菜单快捷方式，用来验证按名字重新定位。"""
    for d in winapi.start_menu_dirs():
        hits = sorted(glob.glob(os.path.join(d, "**", "*.lnk"), recursive=True))
        if hits:
            return hits[0]
    return None


# shell:AppsFolder 这个虚拟目录的 GUID，字节序跟 .lnk 里存的一致
APPSFOLDER_GUID = bytes.fromhex("9bd434424502f34db78038939434" + "56e1")


def write_lnk(lnk_path: str, pidl: bytes) -> None:
    """手搓一个只有 TargetIDList 的 .lnk（没有 LinkInfo / RelativePath）。

    专门用来复刻「指向 shell:AppsFolder 虚拟目录」那种快捷方式 ——
    IShellLink::GetPath 对它只返回 S_FALSE，任何方式都拿不到路径。
    （指向真实文件的同类链接用 make_idlist_lnk 造，那个交给 Shell 自己写。）
    """
    header = bytearray(76)
    struct.pack_into("<I", header, 0, 76)
    header[4:20] = bytes.fromhex("0114020000000000c000000000000046")
    struct.pack_into("<I", header, 20, 0x80000001)   # HasLinkTargetIDList | IsUnicode
    struct.pack_into("<I", header, 24, 0x20)         # FILE_ATTRIBUTE_ARCHIVE
    with open(lnk_path, "wb") as fh:
        fh.write(header)
        fh.write(struct.pack("<H", len(pidl)))
        fh.write(pidl)


def appsfolder_pidl() -> bytes:
    """指向 shell:AppsFolder 虚拟目录的绝对 PIDL（就是问题里那种快捷方式的目标）。"""
    return b"\x14\x00\x1f\x80" + APPSFOLDER_GUID + b"\x00\x00"


def make_idlist_lnk(lnk_path: str, target: str) -> bool:
    """造一个「只存 IDList、指向真实文件」的快捷方式。

    用 Shell 自己的 SHParseDisplayName + IShellLink::SetIDList + Save 来造，
    免得手写 PIDL 字节写错。故意不调 SetPath，所以不会有 LinkInfo。
    """
    sh = ctypes.windll.shell32
    sh.SHParseDisplayName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p),
                                     ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
    sh.SHParseDisplayName.restype = ctypes.c_long
    pidl = ctypes.c_void_p()
    attrs = ctypes.c_ulong(0)
    if sh.SHParseDisplayName(target, None, ctypes.byref(pidl), 0,
                             ctypes.byref(attrs)) != 0 or not pidl:
        return False
    # 这个 PIDL 故意不释放：SetIDList 到底会不会接管所有权说法不一，
    # 测试脚本跑完就退，宁可漏一点也不冒重复释放的险。
    winapi.ensure_com()
    psl = c_void_p()
    winapi.ole32.CoCreateInstance(byref(winapi.CLSID_ShellLink), None,
                                  winapi.CLSCTX_INPROC_SERVER,
                                  byref(winapi.IID_IShellLinkW), byref(psl))
    if not psl:
        return False
    try:
        set_idlist = winapi._com_call(psl.value, 5, c_long, c_void_p)
        if set_idlist(psl.value, pidl) != 0:
            return False
        ppf = c_void_p()
        winapi._com_call(psl.value, 0, c_long, POINTER(winapi.GUID),
                         POINTER(c_void_p))(psl.value,
                                            byref(winapi.IID_IPersistFile),
                                            byref(ppf))
        if not ppf:
            return False
        save = winapi._com_call(ppf.value, 6, c_long, wintypes.LPCWSTR,
                                wintypes.BOOL)
        return save(ppf.value, lnk_path, True) == 0
    finally:
        winapi._release(psl)


def main() -> int:
    rec = Recorder()
    real_shell_execute = winapi.shell_execute
    real_explorer_open = winapi.explorer_open
    winapi.shell_execute = rec.shell
    winapi.explorer_open = rec.explorer

    exe = sys.executable                      # 拿 Python 自己当「被启动的程序」

    # ---- 1. 加进抽屉时就把目标记下来 ----
    print("\n[1] 添加时记住 .lnk 的真实目标")
    lnk = os.path.join(TMP, "演示应用.lnk")
    made = winapi.create_lnk(lnk, exe, workdir=TMP, desc="EdgeDock 自检")
    check("测试用快捷方式已建出来", made and os.path.exists(lnk))
    cfg = new_cfg([])
    check("add_item 成功", cfg.add_item(lnk) is True)
    it = cfg.items[0]
    check("target 已记下", os.path.normcase(it["target"]) == os.path.normcase(exe),
          it["target"])
    check("workdir 已记下", os.path.normcase(it["workdir"]) == os.path.normcase(TMP),
          it["workdir"])
    check("launchable() 为真", cfg.launchable(it) is True)
    check("重复添加会被挡掉", cfg.add_item(lnk) is False)

    # ---- 2. 快捷方式还在：交给 explorer 打开它 ----
    print("\n[2] 快捷方式在 → explorer 打开它（这条通道才真起得来）")
    rec.clear()
    check("launch_item 成功", app_mod.launch_item(it) is True)
    check("走的是 explorer 通道", rec.only("explorer"), repr(rec.calls))
    check("打开的是快捷方式本身（参数/提权/应用标识都挂在它身上）",
          rec.last and os.path.normcase(rec.last[1]) == os.path.normcase(lnk),
          repr(rec.last))
    check("只试了一次", len(rec.calls) == 1, repr(rec.calls))

    # 为什么不用 ShellExecute：实测它对着 .exe / .lnk 都返回成功码，进程却一个
    # 都不起来 —— 谎报成功，用户看到的就是「点了没反应」。
    # 勾了「以管理员身份运行」的快捷方式尤其得走 explorer 打开 .lnk，提权标记才生效。
    print("     —— 勾了「以管理员身份运行」的快捷方式 ——")
    runas_lnk = os.path.join(TMP, "管理员应用.lnk")
    winapi.create_lnk(runas_lnk, exe, workdir=TMP)
    raw = bytearray(open(runas_lnk, "rb").read())
    raw[20:24] = (int.from_bytes(raw[20:24], "little") | 0x00002000).to_bytes(4, "little")
    open(runas_lnk, "wb").write(bytes(raw))
    check("RunAs 位已写入", bool(winapi._lnk_flags(runas_lnk) & 0x2000))
    check("解析出 runas=True", winapi.resolve_lnk(runas_lnk)["runas"] is True)
    cfg_r = new_cfg([runas_lnk])
    r_it = cfg_r.items[0]
    check("刚读进来时 runas 还没记（老配置就这样）", r_it["runas"] is False)
    cfg_r.repair()                       # 和真程序启动时一样过一遍
    check("启动体检后就记下了 runas", r_it["runas"] is True)
    rec.clear()
    check("这种条目确实能启动", app_mod.launch_item(r_it) is True)
    check("走的是快捷方式本身（保住提权）",
          rec.tried == [os.path.normcase(runas_lnk)], repr(rec.calls))
    check("而且是 explorer 通道，UAC 提权标记才认",
          rec.only("explorer"), repr(rec.calls))

    # ---- 3. 快捷方式被删、目标还在：按目标启动 ----
    print("\n[3] 快捷方式被删 → 按记住的目标启动（核心场景）")
    os.remove(lnk)                            # 模拟「桌面上的快捷方式没了」
    it["args"] = "--probe 1"                  # 参数得原样带过去
    check("路径已不存在", not os.path.exists(it["path"]))
    check("launchable() 仍然为真（目标还在）", cfg.launchable(it) is True)
    rec.clear()
    check("launch_item 照样成功", app_mod.launch_item(it) is True)
    check("启动的是记下的目标", rec.last and
          os.path.normcase(rec.last[1]) == os.path.normcase(exe), repr(rec.last))
    check("参数带过去了", rec.last[2] == "--probe 1", repr(rec.last))
    check("工作目录带过去了",
          os.path.normcase(rec.last[3]) == os.path.normcase(TMP), repr(rec.last))
    check("填了参数才用 shell 通道（explorer 递不了参数）",
          rec.only("shell"), repr(rec.calls))

    # 没填参数就走 explorer —— 实测 shell 通道对着这类程序是谎报成功的
    it["args"] = ""
    rec.clear()
    check("没参数时改用 explorer 起目标", app_mod.launch_item(it) is True and
          rec.only("explorer") and
          os.path.normcase(rec.last[1]) == os.path.normcase(exe), repr(rec.calls))

    # shell 通道失败（比如谎报成功之外的真失败）要能退回 explorer
    it["args"] = "--probe 2"
    rec.clear()
    rec.fail.add(os.path.normcase(exe))
    rec.fail_channel = "shell"           # 只让 shell 通道失败
    check("shell 通道起不来时退回 explorer", app_mod.launch_item(it) is True)
    check("两条通道都试过", len(rec.calls) == 2, repr(rec.calls))
    check("最后一次是 explorer", rec.last[0] == "explorer", repr(rec.last))
    rec.fail.clear()
    rec.fail_channel = "*"
    it["args"] = ""

    # ---- 4. 快捷方式和目标都没了：按名字重新定位 ----
    print("\n[4] 都不在了 → 按名字重新定位")
    sample = sample_start_menu_lnk()
    check("本机有「开始」菜单快捷方式可供重定位", bool(sample), sample or "")
    if sample:
        name = os.path.splitext(os.path.basename(sample))[0]
        find = cfg_mod.find_shortcut(name)
        check("find_shortcut 按名字找得到", bool(find), str(find))
        check("找到的是真实存在的文件", bool(find and os.path.exists(find["path"])))
        # 伪造一个「桌面快捷方式被删、也没有记录目标」的孤儿条目
        orphan = {"path": os.path.join(TMP, "没了", name + ".lnk"),
                  "name": name, "args": "", "target": "", "workdir": ""}
        check("孤儿条目一开始打不开", cfg.launchable(orphan) is False)
        with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
            json.dump({"items": [orphan], "seeded": True}, fh, ensure_ascii=False)
        cfg2 = cfg_mod.Config()
        o = cfg2.items[0]
        check("relocate 成功", cfg2.relocate(o) is True)
        check("路径重指到找到的那个", os.path.exists(o["path"]), o["path"])
        check("重定位后能打开", cfg2.launchable(o) is True)
        rec.clear()
        check("重定位后真的启动得起来", app_mod.launch_item(o) is True)
        check("走 explorer 打开找到的那个快捷方式",
              rec.only("explorer") and
              os.path.normcase(rec.last[1]) == os.path.normcase(o["path"]),
              repr(rec.calls))
    check("find_shortcut 对空名字返回 None",
          cfg_mod.find_shortcut("   ") is None)

    # ---- 5. repair()：老配置的一次性迁移 ----
    print("\n[5] repair() 修老配置")
    lnk2 = os.path.join(TMP, "老配置应用.lnk")
    winapi.create_lnk(lnk2, exe, workdir=TMP)
    old = {"path": lnk2, "name": "老配置应用", "args": ""}   # 没有 target 字段
    with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
        json.dump({"items": [old], "seeded": True}, fh, ensure_ascii=False)
    cfg3 = cfg_mod.Config()
    check("读进来时 target 字段被补成空串", cfg3.items[0]["target"] == "")
    n = cfg3.repair()
    check("repair 报告改了 1 条", n == 1, "实际 %d" % n)
    check("target 已补上",
          os.path.normcase(cfg3.items[0]["target"]) == os.path.normcase(exe))
    check("再跑一次 repair 不再改动（幂等）", cfg3.repair() == 0)
    cfg3.save()
    check("落盘的 JSON 里有 target",
          "target" in json.load(open(cfg3.path, encoding="utf-8"))["items"][0])

    # ---- 6. launchable 的真值表 ----
    print("\n[6] launchable() 真值表")
    gone_lnk = os.path.join(TMP, "x.lnk")
    cases = [
        ({"path": exe, "target": ""}, True, "裸 exe 还在"),
        ({"path": lnk2, "target": exe}, True, "快捷方式 + 目标都在"),
        ({"path": lnk2, "target": ""}, True, "快捷方式在、目标字段还是空的"),
        ({"path": gone_lnk, "target": exe}, True, "只剩记下的目标"),
        ({"path": gone_lnk, "target": ""}, False, "快捷方式没了也没目标"),
        ({"path": gone_lnk, "target": os.path.join(TMP, "y.exe")}, False, "目标也不在了"),
        ({"path": "", "target": ""}, False, "空条目"),
    ]
    for it_, want, why in cases:
        check("launchable: %s" % why, cfg_mod.Config.launchable(it_) is want)

    # ---- 7. 打不开时不再静默 ----
    print("\n[7] 彻底打不开时的表现")
    rec.clear()
    check("launch_item 返回 False", app_mod.launch_item(
        {"path": os.path.join(TMP, "无.lnk"),
         "target": os.path.join(TMP, "无.exe")}) is False)
    check("没有乱发起动调用", rec.calls == [], repr(rec.calls))
    check("shell_execute 对不存在的路径返回 False（真实调用）",
          real_shell_execute(os.path.join(TMP, "根本不存在.exe")) is False)

    # ---- 8. 设置列表的状态文案 ----
    print("\n[8] 设置列表里的状态提示")
    QApplication.instance() or QApplication([])
    from edgedock.icons import IconStore                         # noqa: E402
    from edgedock.settings import SettingsDialog                 # noqa: E402
    winapi.create_lnk(lnk, exe, workdir=TMP)                     # 把快捷方式再造回来
    with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
        json.dump({"items": [
            {"path": lnk, "name": "正常项", "args": "", "target": "", "workdir": ""},
            {"path": os.path.join(TMP, "no.lnk"), "name": "只剩目标项", "args": "",
             "target": exe, "workdir": ""},
            {"path": os.path.join(TMP, "no2.lnk"), "name": "彻底没有项", "args": "",
             "target": "", "workdir": ""},
        ], "seeded": True}, fh, ensure_ascii=False)
    dlg = SettingsDialog(cfg_mod.Config(), IconStore(os.path.join(TMP, "icons")))
    texts = [dlg.list.item(i).text() for i in range(dlg.list.count())]
    check("正常项不加后缀", texts[0] == "正常项", texts[0])
    check("只剩目标的提示「快捷方式已删除，按目标启动」",
          "快捷方式已删除，按目标启动" in texts[1], texts[1])
    check("彻底没有的提示「找不到，请重新添加」",
          "找不到，请重新添加" in texts[2], texts[2])
    dlg.close()
    dlg.deleteLater()
    QApplication.processEvents()

    # ---- 9. durable()：启动目标确不确定 ----
    print("\n[9] durable() 真值表（目标是否确定）")
    for it_, want, why in [
        ({"path": exe, "target": ""}, True, "裸 exe，路径本身就是入口"),
        ({"path": lnk2, "target": exe}, True, "能解析出目标的快捷方式"),
        ({"path": lnk2, "target": ""}, False, ".lnk 但目标解析不出来"),
        ({"path": gone_lnk, "target": exe}, True, "快捷方式没了、只剩目标"),
        ({"path": gone_lnk, "target": ""}, False, "什么都没有"),
    ]:
        check("durable: %s" % why, cfg_mod.Config.durable(it_) is want)

    # ---- 10. 复刻「点不开」的现场 ----
    print("\n[10] 复刻：从应用列表拖出来的快捷方式（只存 IDList）")
    apps_lnk = os.path.join(TMP, "只有IDList.lnk")
    write_lnk(apps_lnk, appsfolder_pidl())
    check("这种快捷方式建出来了", os.path.exists(apps_lnk))
    got = winapi.resolve_lnk(apps_lnk)["target"]
    check("GetPath 与 IDList 都拿不到路径（和现场一致）", got == "", repr(got))
    fake = {"path": apps_lnk, "name": "只有IDList", "args": "",
            "target": "", "workdir": ""}
    check("launchable 仍为真（文件在，资源管理器多半能开）",
          cfg_mod.Config.launchable(fake) is True)
    check("durable 为假（目标不确定，快捷方式一删就抓瞎）",
          cfg_mod.Config.durable(fake) is False)
    # 没有目标可用时只能退回快捷方式，让 explorer 去试（对 UWP / AppsFolder 应用就靠这个）
    rec.clear()
    check("没有目标时仍然会去试快捷方式（尽力而为）",
          app_mod.launch_item(fake) is True and
          rec.tried == [os.path.normcase(apps_lnk)], repr(rec.calls))
    check("走的正是 explorer 通道 —— 这种链接只有它认",
          rec.only("explorer"), repr(rec.calls))

    print("     —— 指向真文件、同样没有 LinkInfo 的链接 ——")
    real_lnk = os.path.join(TMP, "真文件IDList.lnk")
    check("用 Shell 自己的 SetIDList 造出来了",
          make_idlist_lnk(real_lnk, exe) and os.path.exists(real_lnk))
    got2 = winapi.resolve_lnk(real_lnk)["target"]
    check("照样能还原出目标",
          os.path.normcase(got2) == os.path.normcase(exe), repr(got2))
    check("这种条目 durable 为真", cfg_mod.Config.durable(
        {"path": real_lnk, "name": "", "args": "", "target": got2,
         "workdir": ""}) is True)

    # ---- 11. repair 真能修好现场那种条目 ----
    print("\n[11] repair 修好现场：补出目标，原路径留着")
    if sample:
        sname = os.path.splitext(os.path.basename(sample))[0]
        broken = os.path.join(TMP, sname + ".lnk")
        write_lnk(broken, appsfolder_pidl())     # 目标未知，且起了个能查到的名字
        with open(os.environ["EDGEDOCK_CONFIG"], "w", encoding="utf-8") as fh:
            json.dump({"items": [{"path": broken, "name": sname, "args": ""}],
                       "seeded": True}, fh, ensure_ascii=False)
        cfg4 = cfg_mod.Config()
        it4 = cfg4.items[0]
        check("修之前 durable 为假", cfg4.durable(it4) is False)
        check("repair 报告改了 1 条", cfg4.repair() == 1)
        check("目标被补上了", os.path.exists(it4["target"]), it4["target"])
        check("原路径保留着（图标、右键「打开所在位置」都还对）",
              it4["path"] == broken, it4["path"])
        check("修完 durable 为真", cfg4.durable(it4) is True)
        check("再跑一次 repair 不再改动（幂等）", cfg4.repair() == 0)

        # 快捷方式还在时，explorer 打开它就行
        rec.clear()
        check("修完真的能启动", app_mod.launch_item(it4) is True)
        check("快捷方式还在 → explorer 打开它",
              rec.only("explorer") and
              os.path.normcase(rec.last[1]) == os.path.normcase(broken),
              repr(rec.calls))

        # 关键一步：这个快捷方式被删掉，补出来的目标就是唯一的救命稻草
        os.remove(broken)
        check("快捷方式已删", not os.path.exists(broken))
        rec.clear()
        check("靠补出来的目标照样打得开", app_mod.launch_item(it4) is True)
        check("起的是补出来的目标",
              rec.only("explorer") and
              os.path.normcase(rec.last[1]) == os.path.normcase(it4["target"]),
              repr(rec.calls))

    # ---- 12. 应用目录：不依赖桌面的那种条目 ----
    print("\n[12] 系统应用目录（appid 条目 —— 桌面上根本没有它）")
    pool = apps_mod.scan_apps()
    check("扫得到应用", len(pool) > 0, "%d 个" % len(pool))
    check("每一项都有名字", all(a["name"] for a in pool))
    check("每一项都能寻址（有 path 或 appid）",
          all(a.get("path") or a.get("appid") for a in pool))
    check("卸载程序被过滤掉了",
          not [a for a in pool if "卸载" in a["name"]
               or a["name"].lower().startswith("uninstall")])
    names = [a["name"].lower() for a in pool]
    check("同名只留一个", len(names) == len(set(names)))
    check("按名字排好序", names == sorted(names))

    store_app = next((a for a in pool if a.get("appid")), None)
    check("候选里有只有 appid 的应用（商店应用）", bool(store_app), str(store_app))
    if store_app:
        cfg5 = new_cfg([])
        check("add_app 成功", cfg5.add_app(store_app) is True)
        a_it = cfg5.items[0]
        check("条目记住了 appid", a_it["appid"] == store_app["appid"], a_it["appid"])
        check("path 是空的（不依赖任何文件）", a_it["path"] == "", repr(a_it["path"]))
        check("key 用的是 appid", cfg5.key(a_it) == store_app["appid"])
        check("launchable 为真", cfg5.launchable(a_it) is True)
        check("durable 为真（系统注册，与桌面无关）", cfg5.durable(a_it) is True)
        check("spec_of 拼得出 shell 路径",
              apps_mod.spec_of(a_it) == winapi.app_spec(store_app["appid"]),
              apps_mod.spec_of(a_it))
        check("重复添加会被挡掉", cfg5.add_app(store_app) is False)

        rec.clear()
        check("launch_item 走得通", app_mod.launch_item(a_it) is True)
        check("走 explorer 打开 shell:AppsFolder\\<标识>",
              rec.only("explorer")
              and rec.last[1] == winapi.app_spec(store_app["appid"]),
              repr(rec.calls))

        # appid 条目没有文件可修，体检不该去动它
        snapshot = dict(a_it)
        check("repair 跳过 appid 条目", cfg5.repair() == 0)
        check("条目一个字段都没被改", snapshot == a_it, repr(a_it))
        check("relocate 不动它", cfg5.relocate(a_it) is False)
        check("失败提示能拿到名字", bool(a_it["name"]), a_it["name"])

    winapi.shell_execute = real_shell_execute
    winapi.explorer_open = real_explorer_open
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n%s：共 %d 项，失败 %d 项"
          % ("全部通过 ✅" if not fails else "有失败项 ❌", total, len(fails)))
    for n in fails:
        print("   - %s" % n)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
