# -*- coding: utf-8 -*-
"""把 EdgeDock 打成免 Python 的独立 exe，并压成可发布的 zip。

产物：
    dist\\EdgeDock.exe                     单文件，双击即用
    release\\EdgeDock-v<版本>-win64.zip     exe + 使用说明（发布用）
    release\\EdgeDock-v<版本>-source.zip    源码（不含 .venv / 缓存 / 构建产物）

用法：.venv\\Scripts\\python.exe tools\\build_release.py [版本号]
（默认版本号取自代码里的 VERSION）
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
RELEASE = os.path.join(ROOT, "release")
# 走 `python -m PyInstaller`，不用 .venv\Scripts\pyinstaller.exe：
# 那个 exe 是个控制台脚本包装，虚拟环境换过机器/被搬动之后它会静默退出（exit 1 且没有任何输出）。
PYI_ARGS = [sys.executable, "-m", "PyInstaller"]

# 源码包里不该出现的东西：虚拟环境、缓存、构建产物、本机配置
SRC_SKIP_DIRS = {".venv", "__pycache__", "cache", "_shots", "build", "dist",
                 "release", ".git", ".idea", ".vscode"}
SRC_SKIP_NAMES = {"EdgeDock.spec", ".DS_Store", "Thumbs.db", "desktop.ini"}
SRC_SKIP_PATTERNS = ("config.json", "config.json.bak-*", "*.pyc", "*.log",
                     "_*.png", "_probe_*")

README_TXT = """EdgeDock · 边缘抽屉  v{ver}
========================================

一条吸附在屏幕边缘的应用启动器。平时只剩一道几像素的光痕，
鼠标碰到屏幕边缘才滑出来；展开时只显示图标，移开就自动收回。
它认的是系统里装了什么，不是桌面上摆了什么 —— 桌面可以彻底空着。

怎么用
------
1. 双击 EdgeDock.exe（绿色版，不需要安装，也不需要 Python）
2. 系统托盘会出现 EdgeDock 图标；鼠标移到屏幕边缘（默认顶部）唤出抽屉
3. 右键托盘图标 →「设置…」→ 控制面板… 挑你想要的应用
   （列的就是控制面板「程序和功能」里那一份，只显示双击能启动的）
4. 想开机自启：托盘右键 → 勾上「开机自动启动」

文件说明
--------
config.json   全部设置和应用列表（就生成在 exe 旁边；删掉即恢复默认）
cache\\icons   图标缓存，可随意删除，会重新生成

小贴士
------
* 单击图标即启动，走的是直连进程的方式，不再绕资源管理器（更快、不会「点了没反应」）
* 全屏游戏 / 全屏视频时边栏会自动让开，退出全屏立刻回来
* 托盘右键 → 设置 → 添加桌面图标，可以在桌面放一个快捷方式
* 程序是单实例的：重复双击只会提示已在运行

项目主页：https://github.com/lian0607/EdgeDock
"""


def _skip(name: str) -> bool:
    if name in SRC_SKIP_DIRS or name in SRC_SKIP_NAMES:
        return True
    return any(fnmatch.fnmatch(name, p) for p in SRC_SKIP_PATTERNS)


def build_source(ver: str) -> tuple[str, int]:
    """把源码目录打包（顶层是 EdgeDock-<ver>/，解压即可用）。"""
    top = "EdgeDock-%s" % ver
    path = os.path.join(RELEASE, "EdgeDock-v%s-source.zip" % ver)
    count = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(top + "/", "")
        for entry in sorted(os.listdir(ROOT)):
            if _skip(entry):
                continue
            full = os.path.join(ROOT, entry)
            if os.path.isfile(full):
                z.write(full, "%s/%s" % (top, entry))
                count += 1
                continue
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = sorted(d for d in dirnames if not _skip(d))
                rel = os.path.relpath(dirpath, ROOT).replace("\\", "/")
                z.writestr("%s/%s/" % (top, rel), "")
                for f in sorted(filenames):
                    if _skip(f):
                        continue
                    z.write(os.path.join(dirpath, f), "%s/%s/%s" % (top, rel, f))
                    count += 1
    return path, count


def main(argv: list[str]) -> int:
    ver = argv[0] if argv else "1.1.0"
    probe = subprocess.run(PYI_ARGS + ["--version"], capture_output=True, text=True)
    if probe.returncode != 0:
        print("找不到 PyInstaller：先跑 "
              ".venv\\Scripts\\python.exe -m pip install pyinstaller")
        if probe.stderr.strip():
            print(probe.stderr.strip()[-400:])
        return 1

    cmd = PYI_ARGS + ["--noconfirm", "--clean", "--windowed", "--onefile",
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

    src_path, n = build_source(ver)
    print("源码包：%s（%d 个文件，%.1f MB）" % (
        src_path, n, os.path.getsize(src_path) / 1024 / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
