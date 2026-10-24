# -*- coding: utf-8 -*-
"""把 EdgeDock 打成免 Python 的独立 exe，并压成可发布的 zip。

产物：
    dist\\EdgeDock.exe                     单文件，双击即用
    release\\EdgeDock-v<版本>-win64.zip     exe + 使用说明（发布用）

用法：.venv\\Scripts\\python.exe tools\\build_release.py [版本号]
（默认版本号取自代码里的 VERSION）
"""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
RELEASE = os.path.join(ROOT, "release")
PYI = os.path.join(ROOT, ".venv", "Scripts", "pyinstaller.exe")

README_TXT = """EdgeDock · 边缘抽屉  v{ver}
========================================

一条吸附在屏幕边缘的应用启动器。平时只剩一道几像素的光痕，
鼠标碰到屏幕边缘才滑出来；展开时只显示图标，移开就自动收回。
它认的是系统里装了什么，不是桌面上摆了什么 —— 桌面可以彻底空着。

怎么用
------
1. 双击 EdgeDock.exe（绿色版，不需要安装，也不需要 Python）
2. 系统托盘会出现 EdgeDock 图标；鼠标移到屏幕边缘（默认顶部）唤出抽屉
3. 右键托盘图标 →「设置…」→ 从系统选择… 挑你想要的应用
4. 想开机自启：托盘右键 → 勾上「开机自动启动」

文件说明
--------
config.json   全部设置和应用列表（就生成在 exe 旁边；删掉即恢复默认）
cache\\icons   图标缓存，可随意删除，会重新生成

小贴士
------
* 全屏游戏 / 全屏视频时边栏会自动让开，退出全屏立刻回来
* 托盘右键 → 设置 → 添加桌面图标，可以在桌面放一个快捷方式
* 程序是单实例的：重复双击只会提示已在运行

项目主页：https://github.com/lian0607/EdgeDock
"""


def main(argv: list[str]) -> int:
    ver = argv[0] if argv else "1.0.0"
    if not os.path.exists(PYI):
        print("找不到 PyInstaller：先跑 "
              ".venv\\Scripts\\python.exe -m pip install pyinstaller")
        return 1

    cmd = [PYI, "--noconfirm", "--clean", "--windowed", "--onefile",
           "--name", "EdgeDock",
           "--icon", os.path.join(ROOT, "assets", "edgedock.ico"),
           # 窗口图标是代码画的（QPainter），assets 里没有运行时要读的文件，
           # 所以不用 --add-data —— 那枚 ico 只作为 exe 自己的图标嵌进去。
           # 这些用不上，排掉能小一圈
           "--exclude-module", "tkinter",
           "--exclude-module", "PIL",
           "--exclude-module", "unittest",
           os.path.join(ROOT, "main.pyw")]
    print("== 开始打包 ==")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print("打包失败，退出码", r.returncode)
        return r.returncode

    exe = os.path.join(DIST, "EdgeDock.exe")
    if not os.path.exists(exe):
        print("打完没找到 dist\\EdgeDock.exe")
        return 1
    size_mb = os.path.getsize(exe) / 1024 / 1024
    print("exe 好了：%.1f MB" % size_mb)

    os.makedirs(RELEASE, exist_ok=True)
    zip_path = os.path.join(RELEASE, "EdgeDock-v%s-win64.zip" % ver)
    note = os.path.join(ROOT, "_release_使用说明.txt")
    with open(note, "w", encoding="utf-8-sig") as fh:   # 记事本友好
        fh.write(README_TXT.format(ver=ver))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, "EdgeDock.exe")
        z.write(note, "使用说明.txt")
    os.remove(note)
    print("发布包：%s（%.1f MB）" % (
        zip_path, os.path.getsize(zip_path) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
