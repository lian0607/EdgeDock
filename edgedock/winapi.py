# -*- coding: utf-8 -*-
"""Win32 / Windows Shell 底层能力封装。

全部通过 ctypes 直接调用系统 API，不依赖 pywin32：
  * 窗口扩展样式（鼠标穿透 / 工具窗口 / 不抢占焦点）
  * 全局热键
  * Shell 图标提取（系统超大图标列表 256x256）
  * .lnk 快捷方式解析（IShellLinkW）
  * 打开文件 / 启动程序（explorer 为主，ShellExecuteW 备用）
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import winreg
from ctypes import POINTER, byref, c_int, c_long, c_ssize_t, c_ubyte, c_uint, c_void_p
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --------------------------------------------------------------------------
# 窗口扩展样式
# --------------------------------------------------------------------------
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020   # 鼠标穿透
WS_EX_TOOLWINDOW = 0x00000080    # 不出现在 Alt+Tab
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000    # 点击不抢占焦点

if hasattr(user32, "GetWindowLongPtrW"):
    _get_long = user32.GetWindowLongPtrW
    _set_long = user32.SetWindowLongPtrW
    _get_long.restype = c_ssize_t
    _get_long.argtypes = [wintypes.HWND, c_int]
    _set_long.restype = c_ssize_t
    _set_long.argtypes = [wintypes.HWND, c_int, c_ssize_t]
else:  # pragma: no cover - 32 位兜底
    _get_long = user32.GetWindowLongW
    _set_long = user32.SetWindowLongW
    _get_long.restype = c_long
    _get_long.argtypes = [wintypes.HWND, c_int]
    _set_long.restype = c_long
    _set_long.argtypes = [wintypes.HWND, c_int, c_long]


def _toggle_ex_style(hwnd: int, bits: int, enable: bool) -> None:
    """改窗口扩展样式。纯属锦上添花，失败了也不影响主流程，所以内部吞掉异常。"""
    try:
        ex = _get_long(wintypes.HWND(hwnd), GWL_EXSTYLE)
        new = (ex | bits) if enable else (ex & ~bits)
        if new != ex:
            _set_long(wintypes.HWND(hwnd), GWL_EXSTYLE, new)
    except Exception:
        pass


def set_click_through(hwnd: int, enable: bool) -> None:
    """开启后鼠标事件会穿透到下层窗口（抽屉收起时使用）。"""
    _toggle_ex_style(hwnd, WS_EX_TRANSPARENT, enable)


def as_tool_window(hwnd: int) -> None:
    """工具窗口 + 不抢焦点，避免出现在任务栏/Alt+Tab 里。"""
    _toggle_ex_style(hwnd, WS_EX_APPWINDOW, False)
    _toggle_ex_style(hwnd, WS_EX_TOOLWINDOW, True)
    _toggle_ex_style(hwnd, WS_EX_NOACTIVATE, True)


HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010

user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, c_int, c_int,
                                c_int, c_int, c_uint]
user32.SetWindowPos.restype = wintypes.BOOL


def set_topmost(hwnd: int, on: bool) -> None:
    """不重建窗口地切换置顶（打开设置窗口时让出置顶，避免挡住它）。"""
    try:
        user32.SetWindowPos(wintypes.HWND(hwnd),
                            wintypes.HWND(HWND_TOPMOST if on else HWND_NOTOPMOST),
                            0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 全局热键
# --------------------------------------------------------------------------
# 这里只做「解析」，不做注册。热键靠 app.py 轮询 GetAsyncKeyState 实现
# （见 EdgeDock._poll_hotkey）：RegisterHotKey 会独占组合键，注册了就轮到
# 用户在其他软件里按不动了。
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN = 0x1, 0x2, 0x4, 0x8
MOD_MAP = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
           "shift": MOD_SHIFT, "win": MOD_WIN, "super": MOD_WIN}

VK_CTRL, VK_ALT, VK_SHIFT, VK_WIN = 0x11, 0x12, 0x10, 0x5B
# (修饰键位, 虚拟键码) —— 轮询时逐个查这些键有没有按下
MOD_KEYS = ((MOD_CONTROL, VK_CTRL), (MOD_ALT, VK_ALT),
            (MOD_SHIFT, VK_SHIFT), (MOD_WIN, VK_WIN))


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+D' -> (modifiers, vk)。无法解析返回 None。"""
    if not text:
        return None
    mods, vk = 0, None
    for part in text.replace(" ", "").split("+"):
        low = part.lower()
        if low in MOD_MAP:
            mods |= MOD_MAP[low]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
            vk = 0x6F + int(low[1:])
        else:
            return None
    if vk is None or mods == 0:
        return None
    return mods, vk


# --------------------------------------------------------------------------
# Shell 图标
# --------------------------------------------------------------------------
SHGFI_ICON = 0x00000100
SHGFI_LARGEICON = 0x00000000
SHGFI_SMALLICON = 0x00000001
SHGFI_SYSICONINDEX = 0x00004000
SHGFI_USEFILEATTRIBUTES = 0x00000010
FILE_ATTRIBUTE_NORMAL = 0x00000080

SHIL_LARGE, SHIL_SMALL, SHIL_EXTRALARGE, SHIL_SYSSMALL, SHIL_JUMBO = 0, 1, 2, 3, 4
ILD_TRANSPARENT = 0x00000001

MAX_PATH = 260
LINKFLAG_RUNAS = 0x00002000     # 快捷方式勾了「以管理员身份运行」


def _lnk_flags(path: str) -> int:
    """直接读 .lnk 头里的 LinkFlags（第 20~24 字节）。

    用 COM 解析之前先看看标志位，成本几乎为零，还能避开 COM 的坑。
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
        if len(head) < 24 or head[:4] != b"\x4c\x00\x00\x00":
            return 0
        return int.from_bytes(head[20:24], "little")
    except Exception:
        return 0


def lnk_runas(path: str) -> bool:
    """快捷方式有没有勾「以管理员身份运行」。"""
    return bool(_lnk_flags(path) & LINKFLAG_RUNAS)


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * MAX_PATH),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", c_ubyte * 8)]

    def __init__(self, d1=0, d2=0, d3=0, d4=(0,) * 8):
        super().__init__(d1, d2, d3, (c_ubyte * 8)(*d4))


IID_IImageList = GUID(0x46EB5926, 0x582E, 0x4017,
                      (0x9F, 0xDF, 0xE8, 0x99, 0x8D, 0xAA, 0x09, 0x50))

shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                   POINTER(SHFILEINFOW), c_uint, c_uint]
shell32.SHGetFileInfoW.restype = ctypes.c_void_p
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyIcon.restype = wintypes.BOOL

_ie_imagelist = None


def _load_imagelist_fn():
    """SHGetImageList 在个别系统上仅以序号 727 导出。"""
    global _ie_imagelist
    if _ie_imagelist is not None:
        return _ie_imagelist
    fn = getattr(shell32, "SHGetImageList", None)
    if fn is None:
        try:
            fn = shell32[727]
        except Exception:
            fn = None
    if fn is not None:
        fn.argtypes = [c_int, POINTER(GUID), POINTER(c_void_p)]
        fn.restype = c_long
    _ie_imagelist = fn
    return fn


def _com_call(this: int, index: int, restype, *argtypes):
    """从 COM 接口指针上取虚表第 index 个方法。"""
    vtbl = ctypes.cast(c_void_p(this), POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(restype, *(c_void_p,) + argtypes)
    return proto(vtbl[index])


HRESULT = c_long


def _release(ptr: c_void_p) -> None:
    """Release 一个 COM 接口指针（IUnknown 虚表第 2 项）。"""
    try:
        _com_call(ptr.value, 2, HRESULT)(ptr.value)
    except Exception:
        pass


def shell_icon_index(path: str) -> int:
    """取得文件在系统图标列表中的索引。"""
    sfi = SHFILEINFOW()
    flags = SHGFI_SYSICONINDEX
    if not os.path.exists(path):
        flags |= SHGFI_USEFILEATTRIBUTES
    shell32.SHGetFileInfoW(path, FILE_ATTRIBUTE_NORMAL, byref(sfi),
                           ctypes.sizeof(sfi), flags)
    return sfi.iIcon


def extract_hicon(path: str) -> int:
    """提取 HICON；失败返回 0。优先超大图标(256)，逐级降级。"""
    index = shell_icon_index(path)
    fn = _load_imagelist_fn()
    if fn is not None:
        for shil in (SHIL_JUMBO, SHIL_EXTRALARGE, SHIL_LARGE):
            piml = c_void_p()
            try:
                if fn(shil, byref(IID_IImageList), byref(piml)) != 0 or not piml:
                    continue
                get_icon = _com_call(piml.value, 10, c_long, c_int, c_uint,
                                     POINTER(c_void_p))
                hicon = c_void_p()
                ok = (get_icon(piml.value, index, ILD_TRANSPARENT,
                               byref(hicon)) == 0 and hicon.value)
                _release(piml)
                if ok:
                    return hicon.value
            except Exception:
                continue
    # 兜底：传统 SHGetFileInfo 大图标
    sfi = SHFILEINFOW()
    shell32.SHGetFileInfoW(path, FILE_ATTRIBUTE_NORMAL, byref(sfi),
                           ctypes.sizeof(sfi), SHGFI_ICON | SHGFI_LARGEICON)
    return int(sfi.hIcon or 0)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", c_long), ("biHeight", c_long),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", c_long), ("biYPelsPerMeter", c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


gdi32.CreateDIBSection.argtypes = [wintypes.HDC, POINTER(BITMAPINFO), c_uint,
                                   POINTER(c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.DrawIconEx.argtypes = [wintypes.HDC, c_int, c_int, wintypes.HICON,
                              c_int, c_int, c_uint, wintypes.HBRUSH, c_uint]
user32.DrawIconEx.restype = wintypes.BOOL

DI_NORMAL = 0x0003
DIB_RGB_COLORS = 0


def hicon_to_bgra(hicon: int, size: int) -> bytes | None:
    """把 HICON 渲染成 size×size 的 32 位 BGRA 位图数据（premultiplied 无关的直存）。"""
    if not hicon:
        return None
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size          # 负数 => 自上而下
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0         # BI_RGB
    bits = c_void_p()
    hbmp = gdi32.CreateDIBSection(mem_dc, byref(bmi), DIB_RGB_COLORS,
                                  byref(bits), None, 0)
    data = None
    if hbmp and bits:
        old = gdi32.SelectObject(mem_dc, hbmp)
        ctypes.memset(bits, 0, size * size * 4)
        user32.DrawIconEx(mem_dc, 0, 0, wintypes.HICON(hicon), size, size,
                          0, None, DI_NORMAL)
        data = ctypes.string_at(bits, size * size * 4)
        gdi32.SelectObject(mem_dc, old)
        gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(None, screen_dc)
    return data


# --------------------------------------------------------------------------
# .lnk 解析（IShellLinkW + IPersistFile）
# --------------------------------------------------------------------------
CLSID_ShellLink = GUID(0x00021401, 0x0000, 0x0000, (0xC0, 0, 0, 0, 0, 0, 0, 0x46))
IID_IShellLinkW = GUID(0x000214F9, 0x0000, 0x0000, (0xC0, 0, 0, 0, 0, 0, 0, 0x46))
IID_IPersistFile = GUID(0x0000010B, 0x0000, 0x0000, (0xC0, 0, 0, 0, 0, 0, 0, 0x46))

CLSCTX_INPROC_SERVER = 1
STGM_READ = 0
SLGP_RAWPATH = 0x00000004

ole32.CoCreateInstance.argtypes = [POINTER(GUID), c_void_p, wintypes.DWORD,
                                   POINTER(GUID), POINTER(c_void_p)]
ole32.CoCreateInstance.restype = c_long
ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
ole32.CoInitializeEx.restype = c_long

_com_local = threading.local()


def ensure_com() -> None:
    """每个线程初始化一次 COM（工作线程里提取图标时需要）。"""
    if getattr(_com_local, "ready", False):
        return
    try:
        ole32.CoInitializeEx(None, 2)   # COINIT_APARTMENTTHREADED
    except Exception:
        pass
    _com_local.ready = True


def resolve_lnk(path: str) -> dict:
    """解析 .lnk，返回 {target, args, workdir, icon, icon_index, description}。

    注意有些 .lnk 真的解析不出路径：LinkFlags 里只有 HasLinkTargetIDList、
    没有 HasLinkInfo / HasRelativePath 的那种（从「开始」菜单的应用列表拖出来的
    会指向 shell:AppsFolder 虚拟目录）。这种 GetPath 会返回 S_FALSE，
    改用 IDList 去还原；还不行就只能返回空，由上层按名字另找入口。
    """
    out = {"target": "", "args": "", "workdir": "", "icon": "", "icon_index": 0,
           "description": "", "runas": False}
    if not path.lower().endswith(".lnk") or not os.path.exists(path):
        return out
    out["runas"] = lnk_runas(path)
    ensure_com()
    psl = c_void_p()
    try:
        if ole32.CoCreateInstance(byref(CLSID_ShellLink), None, CLSCTX_INPROC_SERVER,
                                  byref(IID_IShellLinkW), byref(psl)) != 0 or not psl:
            return out
        ppf = c_void_p()
        qi = _com_call(psl.value, 0, c_long, POINTER(GUID), POINTER(c_void_p))
        if qi(psl.value, byref(IID_IPersistFile), byref(ppf)) != 0 or not ppf:
            return out
        load = _com_call(ppf.value, 5, c_long, wintypes.LPCWSTR, wintypes.DWORD)
        if load(ppf.value, path, STGM_READ) != 0:
            return out
        # 目标路径要挨个试：RAWPATH 拿到的往往是没展开的原文（%windir%\... 这种），
        # 直接 os.path.exists 会误判成不存在；IDList 那条则能救回没有 LinkInfo 的链接。
        cand = []
        get_path = _com_call(psl.value, 3, c_long, wintypes.LPWSTR, c_int,
                             c_void_p, wintypes.DWORD)
        for flags in (SLGP_RAWPATH, 0):
            buf = ctypes.create_unicode_buffer(MAX_PATH)
            if get_path(psl.value, buf, MAX_PATH, None, flags) == 0 and buf.value:
                cand.append(buf.value)
        cand.append(_target_from_idlist(psl.value))
        cand = [c for c in (_expand(x) for x in cand) if c]
        out["target"] = next((c for c in cand if os.path.exists(c)), "")
        for key, idx in (("args", 10), ("workdir", 8), ("description", 6)):
            buf2 = ctypes.create_unicode_buffer(1024 if key == "args" else MAX_PATH)
            fn = _com_call(psl.value, idx, c_long, wintypes.LPWSTR, c_int)
            if fn(psl.value, buf2, len(buf2)) == 0:
                out[key] = buf2.value
        out["workdir"] = _expand(out["workdir"])
        ibuf = ctypes.create_unicode_buffer(MAX_PATH)
        iidx = c_int(0)
        get_icon = _com_call(psl.value, 16, c_long, wintypes.LPWSTR, c_int,
                             POINTER(c_int))
        if get_icon(psl.value, ibuf, MAX_PATH, byref(iidx)) == 0:
            out["icon"] = ibuf.value
            out["icon_index"] = iidx.value
    except Exception:
        pass
    finally:
        if psl:
            _release(psl)
    return out


shell32.SHGetPathFromIDListW.argtypes = [c_void_p, wintypes.LPWSTR]
shell32.SHGetPathFromIDListW.restype = wintypes.BOOL


def _expand(path: str) -> str:
    """展开 %windir% 这类环境变量。

    快捷方式里存的多半是没展开的原文，不展开就 os.path.exists 不出来，
    我们会误以为「目标没了」。
    """
    if not path:
        return ""
    try:
        return os.path.expandvars(path)
    except Exception:
        return path


def _target_from_idlist(psl: int) -> str:
    """GetPath 拿不到目标时，退一步拿 IDList 去问 Shell 要路径。

    解析不出来（比如指向 shell:AppsFolder 那种虚拟目录）就返回空串。
    """
    pidl = c_void_p()
    try:
        # IShellLinkW 虚表：0-2 是 IUnknown，GetPath=3，GetIDList=4
        get_idlist = _com_call(psl, 4, c_long, POINTER(c_void_p))
        if get_idlist(psl, byref(pidl)) != 0 or not pidl:
            return ""
        buf = ctypes.create_unicode_buffer(MAX_PATH * 2)
        if shell32.SHGetPathFromIDListW(pidl, buf):
            return buf.value
    except Exception:
        pass
    finally:
        if pidl:
            try:
                ole32.CoTaskMemFree(pidl)
            except Exception:
                pass
    return ""


# --------------------------------------------------------------------------
# 快捷方式创建
# --------------------------------------------------------------------------
def create_lnk(lnk_path: str, target: str, workdir: str = "",
               icon: str = "", desc: str = "") -> bool:
    """创建一个 .lnk 快捷方式（不依赖 WScript.Shell）。"""
    ensure_com()
    psl = c_void_p()
    try:
        if ole32.CoCreateInstance(byref(CLSID_ShellLink), None, CLSCTX_INPROC_SERVER,
                                  byref(IID_IShellLinkW), byref(psl)) != 0 or not psl:
            return False
        _com_call(psl.value, 20, c_long, wintypes.LPCWSTR)(psl.value, target)
        if workdir:
            _com_call(psl.value, 9, c_long, wintypes.LPCWSTR)(psl.value, workdir)
        if desc:
            _com_call(psl.value, 7, c_long, wintypes.LPCWSTR)(psl.value, desc)
        if icon:
            _com_call(psl.value, 17, c_long, wintypes.LPCWSTR, c_int)(
                psl.value, icon, 0)
        ppf = c_void_p()
        qi = _com_call(psl.value, 0, c_long, POINTER(GUID), POINTER(c_void_p))
        if qi(psl.value, byref(IID_IPersistFile), byref(ppf)) != 0 or not ppf:
            return False
        save = _com_call(ppf.value, 6, c_long, wintypes.LPCWSTR, wintypes.BOOL)
        return save(ppf.value, lnk_path, True) == 0
    except Exception:
        return False
    finally:
        if psl:
            _release(psl)


# --------------------------------------------------------------------------
# 启动程序 & 常用目录
# --------------------------------------------------------------------------
SW_SHOWNORMAL = 1

shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, c_int]
shell32.ShellExecuteW.restype = wintypes.HANDLE


def shell_execute(path: str, args: str = "", workdir: str = "") -> bool:
    """用 ShellExecuteW 打开文件。能带启动参数和工作目录，就它这一个长处。

    **对「启动程序」这件事别用这个函数** —— 实测（Windows 11 / 本机）：
    ShellExecute 打开 .exe 或 .lnk 都返回成功码（>32），进程却一个都没起来，
    连裸 exe 路径也照此办理。它只适合打开文档、网址这类「让默认程序处理」的东西。
    启动程序请用 explorer_open()。

    **对「目标解析不出来」的快捷方式（指向 shell:AppsFolder 那种）同样不可信**：
    返回成功码，实际什么都没发生。返回值 ≤32 才是可靠的失败信号。
    """
    try:
        ret = shell32.ShellExecuteW(None, "open", path, args or None,
                                    workdir or None, SW_SHOWNORMAL)
        return int(ret) > 32            # ≤32 都是错误码
    except Exception:
        return False


# explorer.exe 是常驻的 shell 宿主，把路径交给它，等于在资源管理器里双击。
# 它派活之后就自己退了，所以 Popen 立刻返回、拿不到目标的退出码 —— 但目标
# 确实是在 shell 自己的会话里起来的，这一点很要紧：
#   * 走的是 shell 的激活链路，shell:AppsFolder 那类应用才认（ShellExecuteW 不认）；
#   * 起来的进程挂在 explorer 名下，不受调用方的作业对象/沙箱牵连；
#   * .lnk 自己的启动参数、工作目录、提权标记、应用标识全都照旧生效。
def explorer_open(path: str) -> bool:
    """交给资源管理器打开路径（.lnk / .exe / 文件夹都行）。"""
    if not path or not os.path.exists(path):
        return False
    try:
        subprocess.Popen(["explorer", os.path.normpath(path)],
                         close_fds=True)
        return True
    except Exception:
        return False


SHELL_FOLDERS = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                 r"\User Shell Folders")


def _shell_dirs(pairs) -> list[str]:
    """从注册表读一组 Shell 文件夹（考虑重定向），只保留真实存在的。"""
    dirs = []
    for hive, name in pairs:
        try:
            with winreg.OpenKey(hive, SHELL_FOLDERS) as k:
                val = os.path.expandvars(winreg.QueryValueEx(k, name)[0])
            if os.path.isdir(val):
                dirs.append(val)
        except Exception:
            continue
    return dirs


def desktop_dirs() -> list[str]:
    """返回用户桌面 + 公共桌面（考虑重定向）。"""
    dirs = _shell_dirs(((winreg.HKEY_CURRENT_USER, "Desktop"),
                        (winreg.HKEY_LOCAL_MACHINE, "Common Desktop")))
    # 兜底：Shell 文件夹 API
    if not dirs:
        try:
            buf = ctypes.create_unicode_buffer(MAX_PATH)
            shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
            if buf.value:
                dirs.append(buf.value)
        except Exception:
            pass
    return dirs


def start_menu_dirs() -> list[str]:
    """返回用户 + 公共「开始」菜单的程序目录。

    桌面快捷方式被删掉之后，应用多半还在这儿躺着 —— 重新定位时主要靠它。
    """
    return _shell_dirs(((winreg.HKEY_CURRENT_USER, "Programs"),
                        (winreg.HKEY_LOCAL_MACHINE, "Common Programs")))


def user_program_dirs() -> list[str]:
    """用户级安装目录（%LOCALAPPDATA%\\Programs 下的一级子目录）。

    有些程序不往「开始」菜单里放快捷方式，只能到这儿按名字碰运气。
    """
    root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")
    try:
        return [os.path.join(root, d) for d in os.listdir(root)
                if os.path.isdir(os.path.join(root, d))]
    except Exception:
        return []


kernel32.CreateMutexW.argtypes = [c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
ERROR_ALREADY_EXISTS = 183

_single_mutex = None


def acquire_single_instance(name: str = "EdgeDock_SingleInstance_Mutex") -> bool:
    """拿不到互斥体说明已经有一份在跑了。"""
    global _single_mutex
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True                 # 连互斥体都建不出来，那就放行
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return False
    _single_mutex = handle
    return True
