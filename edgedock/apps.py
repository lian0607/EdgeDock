# -*- coding: utf-8 -*-
"""系统应用目录：把「这台机器上装了哪些应用」整理成一份可选列表。

来源有三处，按可靠性排优先级，同名的只留前面那个：

  1. ``shell:AppsFolder`` —— Windows 的「所有应用」。UWP / 商店应用和绝大多数
     传统程序都在里头，这是最全的一份，也是唯一能覆盖商店应用的地方。
  2. 「开始」菜单 —— 补 AppsFolder 里没有的（绿色软件的快捷方式、网址等）。
  3. 桌面 —— 用户自己摆上去的，仍然认。

所以抽屉不再依赖桌面：桌面清爽与否，跟抽屉里放什么完全无关。
"""
from __future__ import annotations

import os

from . import winapi

# 这些不该出现在「启动器」里：卸载程序、帮助文档、许可协议之类。
# 关键词挑得保守一些，宁可多留几个也不要误杀正常应用。
_SKIP_WORDS = (
    "卸载", "uninstall", "帮助", "help", "readme", "说明", "文档",
    "许可", "license", "主页", "官网",
    # 这些在「所有应用」里也会出现，但不是能「打开」的应用
    "updates", "references", "documentation", "manual",
)


def _skip(name: str) -> bool:
    low = name.strip().lower()
    if not low:
        return True
    return any(w in low for w in _SKIP_WORDS)


def walk(root: str, exts: tuple) -> list[str]:
    """递归列出目录下指定后缀的文件（桌面和「开始」菜单都很小，随便走）。"""
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.lower().endswith(exts):
                out.append(os.path.join(base, f))
    return out


def scan_apps() -> list[dict]:
    """列出这台机器上能启动的应用，按名字排序。

    每一项长这样::

        {"name": "计算器", "path": "", "appid": "Microsoft.WindowsCalculator_...!App",
         "source": "apps"}

      * ``appid`` 有值 -> 用 ``shell:AppsFolder\\<appid>`` 寻址（商店应用、应用列表里的条目）
      * ``path`` 有值  -> 文件系统里的 .lnk / .exe / .url，直接打开
      * ``source``     -> apps / startmenu / desktop，设置界面里用来提示来源
    """
    out: list[dict] = []
    seen: set[str] = set()

    def add(name: str, path: str = "", appid: str = "",
            source: str = "apps") -> None:
        key = name.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        out.append({"name": name, "path": path, "appid": appid,
                    "source": source})

    # 1.「所有应用」
    for a in winapi.list_apps():
        name, ident = a["name"], a["appid"]
        if _skip(name):
            continue
        # 传统程序的标识往往直接就是 exe 路径。这种按普通文件处理更好：
        # 能显示「打开文件所在位置」，取图标也走文件那条更快的路。
        if os.path.isabs(ident) and os.path.exists(ident):
            add(name, path=ident)
        else:
            add(name, appid=ident)

    # 2.「开始」菜单
    for d in winapi.start_menu_dirs():
        for path in walk(d, (".lnk", ".url")):
            stem = os.path.splitext(os.path.basename(path))[0]
            if not _skip(stem):
                add(stem, path=path, source="startmenu")

    # 3. 桌面
    for d in winapi.desktop_dirs():
        for path in walk(d, (".lnk", ".url")):
            stem = os.path.splitext(os.path.basename(path))[0]
            if not _skip(stem):
                add(stem, path=path, source="desktop")

    out.sort(key=lambda a: a["name"].lower())
    return out


def spec_of(it: dict) -> str:
    """取图标 / 启动时用的寻址串：应用标识优先，其次文件路径。

    带 ``shell:`` 前缀的是 shell 命名空间路径，不是文件，图标得走
    IShellItemImageFactory；不带的就是普通文件，走文件图标。
    """
    appid = (it.get("appid") or "").strip()
    if appid:
        return winapi.app_spec(appid)
    return (it.get("path") or "").strip()


SOURCE_LABEL = {
    "apps": "应用列表",
    "startmenu": "开始菜单",
    "desktop": "桌面",
}
