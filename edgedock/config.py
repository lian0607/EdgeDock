# -*- coding: utf-8 -*-
"""配置读写（绿色版：config.json 就放在程序目录）。"""
from __future__ import annotations

import json
import os

from . import apps
from . import winapi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 默认读写程序目录下的 config.json；设置 EDGEDOCK_CONFIG 可以指到别处，
# 自检脚本靠它跑一份临时配置，不碰使用者自己的设置。
CONFIG_PATH = os.environ.get("EDGEDOCK_CONFIG") or os.path.join(ROOT, "config.json")
CACHE_DIR = os.path.join(ROOT, "cache", "icons")

# 首次运行时自动挑选的应用关键词（按此顺序优先收录）
SEED_ORDER = [
    "IntelliJ IDEA", "PyCharm", "DataGrip", "Visual Studio Code",
    "VMware Workstation", "Ubuntu", "DevEco Studio", "Adobe Photoshop",
    "Cursor", "OBS Studio", "GitHub Desktop", "HBuilder X", "Trae CN",
    "WPS Office", "Docker Desktop", "Postman",
]

DEFAULTS = {
    "edge": "top",             # top / bottom / left / right
    "peek": 4,                 # 收起时露出的「触手条」厚度(px)，0 = 完全隐藏
    "icon_size": 40,           # 图标尺寸(px)
    "padding": 13,             # 面板内边距
    "gap": 4,                  # 图标间距
    "hover_scale": 1.16,       # 悬停放大倍率
    "theme": "dark",           # dark / light / system（跟随系统）
    "panel_opacity": 100,      # 面板不透明度 60~100
    "hide_delay": 700,         # 鼠标移开后自动收起延时(ms)
    "dwell": 110,              # 触发区停留判定(ms)
    "trigger_px": 2,           # 触发区厚度(px)
    "keep_open_px": 26,        # 鼠标离面板多少 px 内仍算「停留」
    "slot": "center",          # 沿边位置：center / start / end
    "offset": 0,               # 沿边偏移(px)
    "pin": False,              # 固定展开（不自动收起）
    "hide_after_launch": True, # 启动应用后自动收起
    "hotkey": "Ctrl+Alt+D",
    "autostart": False,
    "show_labels": True,       # 悬停时浮出名称
    "items": [],               # [{"name","path","appid","args","target","workdir","runas"}]
                               # appid = 「所有应用」里的标识，path = 文件（.lnk/.exe/.url）
                               # 两者至少有一个，appid 优先
    "hide_sys": True,          # 选择器里默认隐藏 Windows 自带的系统工具
    "seeded": False,
}


def _norm_item(raw) -> dict | None:
    if isinstance(raw, str):
        raw = {"path": raw}
    if not isinstance(raw, dict):
        return None
    path = (raw.get("path") or "").strip()
    appid = (raw.get("appid") or "").strip()
    # 一个条目要么指向文件，要么指向「所有应用」里的某项 —— 总得有一个
    if not path and not appid:
        return None
    return {
        "path": path,
        # 「所有应用」里的标识（UWP 是包标识，传统程序可能是 exe 路径）
        "appid": appid,
        "name": (raw.get("name") or "").strip(),
        "args": (raw.get("args") or "").strip(),
        # 快捷方式只是个指针。把它的真实目标一并记下来，桌面上那个 .lnk
        # 被删掉/挪走之后，还能直接按 target 把程序拉起来。
        "target": (raw.get("target") or "").strip(),
        "workdir": (raw.get("workdir") or "").strip(),
        # 勾了「以管理员身份运行」的快捷方式得走它自己，直接起 exe 会丢提权
        "runas": bool(raw.get("runas")),
    }


class Config:
    def __init__(self, path: str = CONFIG_PATH):
        self.path = path
        self.data = dict(DEFAULTS)
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in DEFAULTS or k == "items":
                            self.data[k] = v
            except Exception:
                pass
        self.data["items"] = [i for i in
                              (_norm_item(x) for x in self.data.get("items", []))
                              if i]

    def save(self) -> None:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value

    # ------------------------------------------------------------------
    @property
    def items(self) -> list[dict]:
        return self.data.setdefault("items", [])

    def set_items(self, items: list[dict]) -> None:
        out = [i for i in (_norm_item(x) for x in items) if i]
        for it in out:
            self._remember_link(it)
        self.data["items"] = out

    # ---- 单个条目 ----
    @staticmethod
    def key(it: dict) -> str:
        """条目的稳定标识：应用标识优先，其次路径。

        抽屉、右键菜单、设置界面之间只传这一个字符串 —— 上层不用关心
        这一项底下到底是「所有应用」的标识还是磁盘上的文件。
        """
        return (it.get("appid") or it.get("path") or "").strip()

    def _find(self, key: str) -> int:
        """按标识找下标，找不到返回 -1（比较不区分大小写）。"""
        k = os.path.normcase(key or "")
        if not k:
            return -1
        return next((i for i, it in enumerate(self.items)
                     if os.path.normcase(self.key(it)) == k), -1)

    def _reorder(self, key: str, index: int) -> bool:
        """把某一项搬到第 index 位；真的挪动了才返回 True。"""
        items = self.items
        idx = self._find(key)
        if idx < 0:
            return False
        new = max(0, min(len(items) - 1, index))
        if new == idx:
            return False
        items.insert(new, items.pop(idx))
        return True

    def _append(self, it: dict) -> bool:
        """查重 → 记目标 → 入列，两个 add 的公共尾巴。"""
        if self._find(self.key(it)) >= 0:
            return False
        self._remember_link(it)
        self.items.append(it)
        return True

    def add_item(self, path: str, name: str = "") -> bool:
        """把一个磁盘上的文件（.lnk / .exe / .url）加进抽屉。"""
        path = os.path.abspath(path)
        # 拖进来的快捷方式/程序用文件名（去扩展名）当显示名，
        # 否则设置界面里这一行会是空白的。
        stem = os.path.splitext(os.path.basename(path))[0]
        return self._append({"path": path, "appid": "", "name": name or stem,
                             "args": "", "target": "", "workdir": "",
                             "runas": False})

    def add_app(self, app: dict) -> bool:
        """把「所有应用」里的一个应用加进抽屉。

        app 来自 ``apps.scan_apps()``，形如
        ``{"name","path","appid","source"}``；path / appid 有一个就行。
        """
        name = (app.get("name") or "").strip()
        path = (app.get("path") or "").strip()
        appid = (app.get("appid") or "").strip()
        if not name or not (path or appid):
            return False
        return self._append({"path": path, "appid": appid, "name": name,
                             "args": "", "target": "", "workdir": "",
                             "runas": False})

    def remove_item(self, key: str) -> None:
        idx = self._find(key)
        if idx >= 0:
            del self.items[idx]

    def move_item(self, key: str, delta: int) -> None:
        idx = self._find(key)
        if idx >= 0:
            self._reorder(key, idx + delta)

    def move_item_to(self, key: str, index: int) -> bool:
        """把某一项直接搬到第 index 位（抽屉内拖动排序用）。"""
        return self._reorder(key, int(index))

    def find(self, key: str) -> dict | None:
        idx = self._find(key)
        return self.items[idx] if idx >= 0 else None

    # ---- 能不能打开 / 打不开就修 ----
    @staticmethod
    def launchable(it: dict) -> bool:
        """能不能把这一项拉起来。

        「所有应用」里的条目（有 appid）由系统注册，随手就能启动；
        文件条目则看路径还在不在。
        """
        if (it.get("appid") or "").strip():
            return True
        return any(it.get(k) and os.path.exists(it[k]) for k in ("path", "target"))

    @staticmethod
    def durable(it: dict) -> bool:
        """这一项是不是「靠得住」的入口 —— 启动目标确定，不依赖资源管理器。

        有 appid 的最靠得住：由系统注册，跟桌面、快捷方式都没关系，
        重装系统之前它一直有效。.lnk 解析不出目标就不算靠得住 ——
        能不能开全看资源管理器，而且快捷方式一被删就彻底抓瞎。
        """
        if (it.get("appid") or "").strip():
            return True
        path = it.get("path") or ""
        target = it.get("target") or ""
        if target and os.path.exists(target):
            return True
        if not path or not os.path.exists(path):
            return False
        return not path.lower().endswith(".lnk")

    def _remember_link(self, it: dict) -> bool:
        """解析 .lnk，把真实目标、启动参数、工作目录记进条目。返回是否有改动。"""
        if it.get("appid"):
            return False        # 「所有应用」的条目没有 .lnk 可解析
        path = it.get("path") or ""
        if not path.lower().endswith(".lnk") or not os.path.exists(path):
            return False
        changed = False
        # runas 读文件头就有，几乎不要钱，所以每回都对齐一次
        # （老配置里没这个字段，得靠这一步补上）
        runas = winapi.lnk_runas(path)
        if it.get("runas") != runas:
            it["runas"] = runas
            changed = True
        # 已经记过而且那个目标还在，就不用再解析一遍 COM 了。
        # 目标不见时（程序升级换了目录）自然会走到下面重新解析。
        if it.get("target") and os.path.exists(it["target"]):
            return changed
        link = winapi.resolve_lnk(path)
        if not link["target"]:
            return changed
        for key, val in (("target", link["target"]), ("args", link["args"]),
                         ("workdir", link["workdir"])):
            if it.get(key) != val:
                it[key] = val
                changed = True
        return changed

    def relocate(self, it: dict) -> bool:
        """尽力把这一项变成「靠得住」的入口，有改动返回 True。

        先重解析原快捷方式；还是拿不到确定的目标，就按名字另找一个能替代的快捷方式。
        原路径还能用的话**留着不动**（图标、右键「打开文件所在位置」都还对），
        只把找回来的真实目标补进 target 当兜底；原路径没了才改 path。
        """
        if it.get("appid"):
            return False        # 系统注册的应用，不存在「找不到入口」这回事
        path = it.get("path") or ""
        if not path:
            return False
        if os.path.exists(path):
            self._remember_link(it)
            if self.durable(it):
                return False                    # 本来就靠得住，不必动
        for name in (os.path.splitext(os.path.basename(path))[0],
                     it.get("name", "")):
            hit = find_shortcut(name)
            if not hit:
                continue
            if os.path.exists(path):
                # 借替身把真实目标挖出来，但不动原路径
                sub = {"path": hit["path"], "name": hit["name"], "args": "",
                       "target": "", "workdir": "", "runas": False}
                self._remember_link(sub)
                if sub["target"]:
                    it["target"] = sub["target"]
                    it["workdir"] = it["workdir"] or sub["workdir"]
                    it["args"] = it["args"] or sub["args"]
                    return True
            it["path"] = hit["path"]
            it["target"] = it["args"] = it["workdir"] = ""
            it["runas"] = False
            if not it.get("name"):
                it["name"] = hit["name"]
            self._remember_link(it)
            return True
        return False

    def repair(self) -> int:
        """把所有条目过一遍，能修的就地修好，返回改动过的条数。

        启动时跑一次：快捷方式被删、被改名、被挪走都是常事，
        没必要等到点不开才发现 —— 那时候用户只会觉得「点了没反应」。
        """
        keys = ("path", "appid", "name", "args", "target", "workdir", "runas")
        changed = 0
        for it in self.items:
            if it.get("appid"):
                continue        # 系统注册的条目没什么可修
            before = tuple(it.get(k) for k in keys)
            # 快捷方式还在就顺手刷新一遍目标：程序升级换了安装目录也能跟上
            if it.get("path") and os.path.exists(it["path"]):
                self._remember_link(it)
            if not self.durable(it):
                self.relocate(it)
            if before != tuple(it.get(k) for k in keys):
                changed += 1
        return changed


# ----------------------------------------------------------------------
# 首次运行：从系统应用目录挑一批常用开发工具
# ----------------------------------------------------------------------
def find_shortcut(name: str) -> dict | None:
    """按名字找一个能启动这个应用的快捷方式或可执行文件。

    桌面快捷方式被删掉之后，应用多半还躺在「开始」菜单里 —— 先找那儿。
    找不到同名的再放宽到「名字开头对得上」的（优先短的，最像原主）。
    """
    key = os.path.normcase(name.strip())
    if not key:
        return None
    exact, loose = [], []
    for d in winapi.desktop_dirs() + winapi.start_menu_dirs():
        for path in apps.walk(d, (".lnk", ".url", ".exe")):
            stem = os.path.splitext(os.path.basename(path))[0]
            k = os.path.normcase(stem)
            if k == key:
                exact.append(path)
            elif k.startswith(key) or key.startswith(k):
                loose.append(path)
    # 有些程序不往「开始」菜单里放快捷方式，到用户级安装目录碰碰运气
    for d in winapi.user_program_dirs():
        for path in apps.walk(d, (".exe",)):
            stem = os.path.splitext(os.path.basename(path))[0]
            if os.path.normcase(stem) == key:
                exact.append(path)
    # 同名的里面，快捷方式优先于裸 exe，其次取名字最短的（最像原主）
    for bucket in (exact, loose):
        if bucket:
            bucket.sort(key=lambda p: (".exe" if p.lower().endswith(".exe") else "",
                                       len(os.path.basename(p)), p))
            best = bucket[0]
            return {"path": best,
                    "name": os.path.splitext(os.path.basename(best))[0]}
    return None


def seed_items() -> list[dict]:
    """按 SEED_ORDER 顺序挑出常用应用，最多 12 个。

    扫的是**系统应用目录**而不是桌面 —— 桌面上有没有快捷方式都不影响。
    这正是「应用启动器」和「桌面图标抽屉」的分水岭。
    """
    pool = apps.scan_apps()
    picked: list[dict] = []
    for key in SEED_ORDER:
        low = key.lower()
        for a in pool:
            if a not in picked and a["name"].lower().startswith(low):
                picked.append(a)
                break
    return (picked or pool[:10])[:12]
