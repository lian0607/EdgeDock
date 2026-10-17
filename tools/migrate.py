# -*- coding: utf-8 -*-
"""换目录后的迁移：重建桌面快捷方式 + 修正开机自启路径。"""
import os
import sys
import winreg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgedock import winapi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "EdgeDock"


def main() -> None:
    print("程序目录:", ROOT)

    # ---- 1. 桌面快捷方式 ----
    dirs = winapi.desktop_dirs()
    lnk = os.path.join(dirs[0], "EdgeDock 边缘抽屉.lnk")
    ok = winapi.create_lnk(
        lnk,
        os.path.join(ROOT, "启动 EdgeDock.vbs"),
        workdir=ROOT,
        icon=os.path.join(ROOT, "assets", "edgedock.ico"),
        desc="EdgeDock · 吸附桌面边缘的应用抽屉",
    )
    print(("桌面快捷方式已更新: " if ok else "桌面快捷方式创建失败: ") + lnk)
    if ok:
        print("  回读目标 =", winapi.resolve_lnk(lnk)["target"])

    # ---- 2. 开机自启 ----
    pyw = os.path.join(ROOT, ".venv", "Scripts", "pythonw.exe")
    main_py = os.path.join(ROOT, "main.pyw")
    cmd = '"%s" "%s"' % (pyw, main_py)
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            try:
                old, _ = winreg.QueryValueEx(k, RUN_NAME)
            except FileNotFoundError:
                old = "(无)"
            if old != cmd:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, cmd)
                print("开机自启已修正:\n  旧 = %s\n  新 = %s" % (old, cmd))
            else:
                print("开机自启无需修改")
    except Exception as exc:
        print("开机自启处理失败:", exc)


if __name__ == "__main__":
    main()
