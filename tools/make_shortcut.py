# -*- coding: utf-8 -*-
"""在桌面创建 EdgeDock 快捷方式（纯 ctypes 写 .lnk）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgedock import winapi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def desktop_dir() -> str:
    dirs = winapi.desktop_dirs()
    for d in dirs:
        # 优先用户桌面（包含当前用户名的那一个）
        if os.path.basename(os.path.dirname(d)) or True:
            pass
    # desktop_dirs 返回 [用户桌面, 公共桌面]
    return dirs[0] if dirs else os.path.join(os.path.expanduser("~"), "Desktop")


def main() -> None:
    for d in winapi.desktop_dirs():
        print("桌面目录:", d)
    target_dir = desktop_dir()
    lnk = os.path.join(target_dir, "EdgeDock 边缘抽屉.lnk")
    ok = winapi.create_lnk(
        lnk,
        os.path.join(ROOT, "启动 EdgeDock.vbs"),
        workdir=ROOT,
        icon=os.path.join(ROOT, "assets", "edgedock.ico"),
        desc="EdgeDock · 吸附桌面边缘的应用抽屉",
    )
    print(("已创建: " if ok else "创建失败: ") + lnk)
    if ok:
        print("回读验证:", winapi.resolve_lnk(lnk)["target"])


if __name__ == "__main__":
    main()
