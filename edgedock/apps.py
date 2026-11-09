# -*- coding: utf-8 -*-
"""应用目录：把「这台机器上装了哪些程序」整理成一份可选列表。

名单来源就是**控制面板 → 程序和功能**（注册表里 Uninstall 三处），跟用户
在控制面板看到的那一份对齐，不再混入「所有应用」里的系统小程序和网址。

控制面板里还有运行库、驱动、服务这类「装上了但不能打开」的东西。它们照抄
进来只会让人点了没反应，所以每条都要先找出主程序，找不出来的直接不列：

  1. 「开始」菜单里的同名快捷方式 —— 最保真，带启动参数、工作目录、提权标记
  2. DisplayIcon 指向的 .exe
  3. InstallLocation 目录下的主程序
  4. UninstallString 反推出的安装目录

这一套下来，本机 88 条控制面板条目里能落地成「点了必开」的约 50 多条。
"""
from __future__ import annotations

import os
import re
import winreg

from . import winapi

# 控制面板的三处来源：64 位程序、32 位程序、当前用户装的（不需要管理员权限）
_UNINSTALL_ROOTS = (
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)

# exe 名字里带这些词的，多半是安装器 / 卸载器 / 更新器 / 后台服务，不是主程序。
# 拿它当入口，点下去要么弹卸载框，要么什么都不发生。
_BAD_EXE_WORDS = (
    "unins", "uninstall", "setup", "install", "update", "updater", "upgrade",
    "repair", "remove", "helper", "crash", "report", "service", "server",
    "daemon", "watchdog", "vc_redist", "dotnet", "devcon", "卸载", "安装",
)

# 这些 exe 是命令行工具，双击只会闪一个黑框
_CLI_EXES = {
    "git.exe", "mysql.exe", "mysqld.exe", "node.exe", "npm.exe",
    "python.exe", "pythonw.exe", "rustup.exe", "cargo.exe", "cmd.exe",
    "mysqladmin.exe", "mysqldump.exe",
}

# 安装包缓存里的 exe 全是安装器；系统目录和公共组件目录也不属于任何应用
_BAD_PATHS = (
    "\\package cache\\", "\\windows\\", "\\program files\\common files\\",
    "\\nvcontainer\\", "\\edgewebview\\", "\\windowsapps\\",
    "\\installer2\\", "\\installercore\\",
)

# 控制面板里这些名字的东西装上了但没法「打开」，列出来只会让人点了没反应：
# 运行库、驱动、服务、SDK、安装器。宁可少列，也别列一个点不动的。
_BAD_NAME_WORDS = (
    "runtime", "redistributable", "redistribu", "framework", "webview",
    "service", "driver", "sdk", "installer", "support", "router",
    "container", "server", "运行库", "驱动", "服务", "组件", "输入法",
)

# 这些目录本身不是某个程序的安装目录，往里乱找会翻出一堆系统 exe
_WIDE_DIRS = (
    "\\windows", "\\windows\\system32", "\\windows\\syswow64",
    "\\program files", "\\program files (x86)", "\\programdata",
)

# 名字里这些词对「找 exe」没有区分度，反而会误导匹配
_NAME_NOISE = {
    "microsoft", "windows", "corporation", "company", "inc", "ltd", "llc",
    "the", "for", "and", "with", "edition", "version", "professional",
    "community", "ultimate", "enterprise", "server", "client",
}

# 版本号之类的显示名后缀，比对时先去掉
_VERSION_TAIL = re.compile(r"\s+v?\d+(\.\d+)+\S*\s*$", re.I)


def walk(root: str, exts: tuple) -> list[str]:
    """递归列出目录下指定后缀的文件（「开始」菜单很小，随便走）。"""
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.lower().endswith(exts):
                out.append(os.path.join(base, f))
    return out


# ----------------------------------------------------------------------
#  控制面板名单
# ----------------------------------------------------------------------
def _reg_str(key, name: str) -> str:
    try:
        value, _kind = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return value.strip() if isinstance(value, str) else ""


def _installed_rows() -> list[dict]:
    """读控制面板「程序和功能」那一份名单。

    过滤规则跟控制面板自己一致：没有显示名的、标了 SystemComponent 的、
    是别的程序的子项 / 补丁的，都不在列表里出现。
    """
    rows: list[dict] = []
    for hive, path in _UNINSTALL_ROOTS:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            count = winreg.QueryInfoKey(root)[0]
            for i in range(count):
                try:
                    name = winreg.EnumKey(root, i)
                    with winreg.OpenKey(root, name) as k:
                        display = _reg_str(k, "DisplayName")
                        if not display:
                            continue
                        if _reg_str(k, "SystemComponent") == "1":
                            continue
                        if _reg_str(k, "ParentKeyName"):
                            continue
                        if _reg_str(k, "ReleaseType") in (
                                "Update", "Hotfix", "Security Update",
                                "ServicePack"):
                            continue
                        rows.append({
                            "name": display,
                            "icon": _reg_str(k, "DisplayIcon"),
                            "loc": _reg_str(k, "InstallLocation"),
                            "unins": _reg_str(k, "UninstallString"),
                        })
                except OSError:
                    continue
        finally:
            root.Close()
    return rows


def _usable_exe(path: str) -> bool:
    """这个 exe 能不能当「打开某个程序」的入口。"""
    if not path or not os.path.isfile(path):
        return False
    low = os.path.normcase(path.lower())
    if not low.endswith(".exe"):
        return False
    if any(b in low for b in _BAD_PATHS):
        return False
    base = os.path.basename(low)
    if base in _CLI_EXES:
        return False
    stem = os.path.splitext(base)[0]
    return not any(w in stem for w in _BAD_EXE_WORDS)


def _bad_name(name: str) -> bool:
    low = (name or "").casefold()
    return any(w in low for w in _BAD_NAME_WORDS)


def _exe_from_icon(raw: str) -> str:
    """DisplayIcon 里取 exe：``"C:\\a\\b.exe",0`` 这种带图标序号的要剥掉。"""
    path = (raw or "").strip().strip('"')
    if not path:
        return ""
    head, sep, tail = path.rpartition(",")
    if sep and tail.strip().isdigit():
        path = head.strip().strip('"')
    path = os.path.expandvars(path)
    return path if _usable_exe(path) else ""


def _safe_folder(folder: str) -> str:
    """确认这是某个程序的安装目录，而不是盘符根 / Program Files 这种大杂院。"""
    if not folder:
        return ""
    folder = os.path.expandvars(folder.strip().strip('"'))
    if not os.path.isdir(folder):
        return ""
    low = os.path.normcase(os.path.abspath(folder))
    if any(low.endswith(d) for d in _WIDE_DIRS):
        return ""
    if any(b.rstrip("\\") in low for b in _BAD_PATHS):
        return ""
    return folder


def _dir_of_command(cmd: str) -> str:
    """从 UninstallString 反推安装目录。

    ``"C:\\App\\unins000.exe" /SILENT`` -> ``C:\\App``；
    ``MsiExec.exe /X{GUID}`` 这种推不出来，返回空（推出来也是 System32）。
    """
    cmd = (cmd or "").strip()
    if not cmd:
        return ""
    if cmd.startswith('"'):
        path = cmd[1:].split('"', 1)[0]
    else:
        path = cmd.split(" ", 1)[0]
    path = os.path.expandvars(path)
    base = os.path.basename(path).lower()
    if base in ("msiexec.exe", "rundll32.exe", "cmd.exe", "powershell.exe"):
        return ""
    if not os.path.isfile(path):
        return ""
    folder = os.path.dirname(path)
    return "" if os.path.normcase(folder).endswith("\\system32") else folder


def _name_tokens(name: str) -> list[str]:
    """把显示名拆成能跟 exe 文件名对上的小词。

    显示名里基本都是版本号、位数、公司名这些噪声，真正有区分度的是
    ``Photoshop`` / ``datagrip`` 这种词。
    """
    low = _VERSION_TAIL.sub("", name or "").casefold()
    low = re.sub(r"\(.*?\)", " ", low)
    out = []
    for word in re.findall(r"[a-z0-9]+", low):
        if len(word) < 3 or word.isdigit() or word in _NAME_NOISE:
            continue
        out.append(word)
    return out


def _exe_files(folder: str, depth: int) -> list[str]:
    """列出目录里的 exe，最多下探 ``depth`` 层。

    ``dirs[:16]`` 是防呆：有些安装目录里挂着 SDK、示例工程，全走一遍要好几秒。
    """
    out: list[str] = []
    root = os.path.normpath(folder)
    if not os.path.isdir(root):
        return out
    for base, dirs, files in os.walk(root):
        rel = os.path.relpath(base, root)
        level = 0 if rel == "." else rel.count(os.sep) + 1
        if level >= depth:
            dirs[:] = []
        else:
            dirs[:] = [d for d in dirs if not d.startswith((".", "$"))][:16]
        for f in files:
            if f.lower().endswith(".exe"):
                out.append(os.path.join(base, f))
        if len(out) > 300:
            break
    return out


def _pick_exe(folder: str, name: str) -> str:
    """在安装目录里挑最像「主程序」的那个 exe。

    打分三件事：名字里含显示名的关键词、在安装目录根下、层级浅。
    """
    folder = _safe_folder(folder)
    if not folder:
        return ""
    tokens = _name_tokens(name)
    best, best_score = "", -99
    for depth in (2, 3):
        for path in _exe_files(folder, depth):
            if not _usable_exe(path):
                continue
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            rel = os.path.relpath(os.path.dirname(path), folder)
            level = 0 if rel == "." else rel.count(os.sep) + 1
            score = 6 - level * 2
            for t in tokens:
                if t == stem:
                    score += 8
                elif t in stem:
                    score += 4
            if score > best_score:
                best, best_score = path, score
        if best:
            break
    return best


def _start_index() -> dict[str, list[str]]:
    """「开始」菜单的快捷方式索引：名字 -> 路径。建一次查几十次。"""
    index: dict[str, list[str]] = {}
    for d in winapi.start_menu_dirs():
        for path in walk(d, (".lnk",)):
            stem = os.path.splitext(os.path.basename(path))[0].strip().casefold()
            if stem:
                index.setdefault(stem, []).append(path)
    return index


def _entry_of(row: dict, index: dict[str, list[str]]) -> dict | None:
    """把一条控制面板记录落成一个「点了能开」的抽屉条目。"""
    name = row["name"]
    key = name.strip().casefold()

    # 1) 开始菜单的同名快捷方式：参数、工作目录、提权标记都在，最保真
    for link in index.get(key, ()):
        if not os.path.exists(link):
            continue
        info = winapi.resolve_lnk(link)
        target = info.get("target") or ""
        if target and _usable_exe(target):
            return {"name": name, "path": link, "appid": "",
                    "source": "installed", "target": target,
                    "args": info.get("args", ""),
                    "workdir": info.get("workdir", ""),
                    "runas": bool(info.get("runas"))}
        if not target:
            # 解析不出来的快捷方式照样能用（走 shell 激活），别丢
            return {"name": name, "path": link, "appid": "",
                    "source": "installed"}

    # 2) DisplayIcon 直接指着主程序
    exe = _exe_from_icon(row["icon"])

    # 3) 安装目录里找；4) 卸载程序反推安装目录再找
    if not exe:
        for folder in (_safe_folder(row["loc"]),
                       _safe_folder(_dir_of_command(row["unins"]))):
            if folder:
                exe = _pick_exe(folder, name)
                if exe:
                    break
    if not exe:
        return None                 # 运行库 / 驱动 / 服务：列出来也点不开
    return {"name": name, "path": exe, "appid": "", "source": "installed",
            "target": exe, "workdir": os.path.dirname(exe)}


def scan_installed() -> list[dict]:
    """控制面板「程序和功能」里那些能启动的程序，按名字排序。"""
    index = _start_index()
    out: list[dict] = []
    seen: set[str] = set()
    for row in _installed_rows():
        key = row["name"].strip().casefold()
        if not key or key in seen:
            continue
        entry = _entry_of(row, index)
        if entry:
            seen.add(key)
            out.append(entry)
    out.sort(key=lambda a: a["name"].casefold())
    return out


# ----------------------------------------------------------------------
#  按名字回落到控制面板入口
# ----------------------------------------------------------------------
_INSTALLED: list[dict] | None = None


def installed_pool(refresh: bool = False) -> list[dict]:
    """缓存一份控制面板名单。扫一次约 150ms，点图标时不该每次都付这个钱。"""
    global _INSTALLED
    if refresh or _INSTALLED is None:
        _INSTALLED = scan_installed()
    return _INSTALLED


def _same_app(a: str, b: str) -> bool:
    """两个显示名是不是同一个程序（"WorkBuddy" 对 "WorkBuddy 5.9.3"）。"""
    a, b = (a or "").strip().casefold(), (b or "").strip().casefold()
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    # 太短的名字做包含匹配会乱套（"QQ" 会命中 "QQ音乐"）
    if len(short) >= 4 and short in long_:
        return True
    ta, tb = set(_name_tokens(a)), set(_name_tokens(b))
    return bool(ta) and bool(tb) and (ta <= tb or tb <= ta)


def find_installed(name: str) -> dict | None:
    """按显示名在控制面板名单里找对应条目，找不到返回 None。"""
    if not name:
        return None
    best, best_score = None, -1
    for app in installed_pool():
        if not _same_app(name, app["name"]):
            continue
        score = len(app["name"])
        if app.get("target"):
            score += 100            # 能直接起的优先
        if score > best_score:
            best, best_score = app, score
    return best


# ----------------------------------------------------------------------
#  「所有应用」（控制面板不收录商店应用，留着当兜底）
# ----------------------------------------------------------------------
def scan_shell_apps() -> list[dict]:
    """「所有应用」+ 开始菜单 + 桌面，商店应用也在里头。

    只在新机器上控制面板条目为空（极罕见）时兜底用。
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

    for a in winapi.list_apps():
        name, ident = a["name"], a["appid"]
        if _skip(name):
            continue
        if os.path.isabs(ident) and os.path.exists(ident):
            add(name, path=ident)
        else:
            add(name, appid=ident)
    for d in winapi.start_menu_dirs():
        for path in walk(d, (".lnk", ".url")):
            stem = os.path.splitext(os.path.basename(path))[0]
            if not _skip(stem):
                add(stem, path=path, source="startmenu")
    for d in winapi.desktop_dirs():
        for path in walk(d, (".lnk", ".url")):
            stem = os.path.splitext(os.path.basename(path))[0]
            if not _skip(stem):
                add(stem, path=path, source="desktop")
    out.sort(key=lambda a: a["name"].lower())
    return out


def scan_apps() -> list[dict]:
    """选择器 / 首次填充用的候选池：控制面板名单，空了才退回「所有应用」。"""
    return scan_installed() or scan_shell_apps()


# ----------------------------------------------------------------------
#  公共小工具
# ----------------------------------------------------------------------
# 这些不该出现在「启动器」里：卸载程序、帮助文档、许可协议之类。
# 关键词挑得保守一些，宁可多留几个也不要误杀正常应用。
_SKIP_WORDS = (
    "卸载", "uninstall", "帮助", "help", "readme", "说明", "文档",
    "许可", "license", "主页", "官网",
    "updates", "references", "documentation", "manual",
)


def _skip(name: str) -> bool:
    low = name.strip().lower()
    if not low:
        return True
    return any(w in low for w in _SKIP_WORDS)


# Windows 自带的管理工具 / 系统小程序：能打开，但当成「应用」没有意义。
_SYS_DIRS = (
    "windows system", "windows accessories", "windows administrative tools",
    "windows ease of access", "windows games", "administrative tools",
    "system tools", "accessories",
    "windows 系统", "windows 附件", "windows 管理工具", "windows 轻松使用",
)
_SYS_WORDS = (
    "component services", "computer management", "control panel",
    "character map", "command prompt", "registry editor", "event viewer",
    "device manager", "task scheduler", "system configuration",
    "system information", "disk cleanup", "defragment", "dfrgui",
    "windows defender", "steps recorder", "math input",
    "组件服务", "计算机管理", "控制面板", "字符映射表", "命令提示符",
    "注册表编辑器", "事件查看器", "设备管理器", "任务计划程序", "系统配置",
    "系统信息", "磁盘清理", "磁盘碎片整理", "任务管理器", "步骤记录器",
)


def is_system_tool(app: dict) -> bool:
    """是不是「装上了但不该放进启动器」的那一类：系统工具、运行库、驱动、服务。

    只在选择器里当**可开关的过滤器**用 —— 不在扫描阶段剔除，用户想要照样能加。
    """
    low = app.get("name", "").strip().lower()
    if any(w in low for w in _SYS_WORDS) or _bad_name(low):
        return True
    p = (app.get("path") or "").lower()
    return any(d in p for d in _SYS_DIRS)


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
    "installed": "控制面板",
    "apps": "应用列表",
    "startmenu": "开始菜单",
    "desktop": "桌面",
}
