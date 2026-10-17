# -*- coding: utf-8 -*-
"""以正确编码重写启动脚本：.vbs 用 UTF-16LE+BOM，.bat 用 GBK(936)。"""
import os

ROOT = r"D:\EdgeDrawer"

VBS = '''Option Explicit
' EdgeDock 静默启动器（双击即可，不弹黑窗口）
Dim fso, sh, root, pyw, main
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pyw  = root & "\\.venv\\Scripts\\pythonw.exe"
main = root & "\\main.pyw"

If Not fso.FileExists(pyw) Then
    MsgBox "找不到运行环境：" & vbCrLf & pyw & vbCrLf & vbCrLf & _
           "请先运行同目录下的「安装运行环境.bat」", 16, "EdgeDock"
    WScript.Quit 1
End If

sh.CurrentDirectory = root
sh.Run """" & pyw & """ """ & main & """", 0, False
'''

INSTALL = '''@echo off
cd /d "%~dp0"
echo 正在创建独立运行环境（.venv）...
"D:\\Program Files\\Python\\Python313\\python.exe" -m venv .venv
if errorlevel 1 (
    echo.
    echo 未找到 D:\\Program Files\\Python\\Python313\\python.exe
    echo 请把本文件里的 python.exe 路径改成实际路径后重试。
    pause
    exit /b 1
)
echo 正在安装依赖 PySide6 ...
".venv\\Scripts\\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple PySide6-Essentials
if errorlevel 1 (
    echo.
    echo 安装失败，请检查网络后重试。
    pause
    exit /b 1
)
".venv\\Scripts\\python.exe" tools\\make_icon.py
echo.
echo 完成，双击「启动 EdgeDock.vbs」即可运行。
pause
'''

DEBUG = '''@echo off
cd /d "%~dp0"
echo EdgeDock 调试模式（关闭本窗口即退出程序）
echo.
".venv\\Scripts\\python.exe" main.pyw
echo.
echo 程序已退出。
pause
'''


def main() -> None:
    # VBScript 由 wscript 按 ANSI 读取，中文必须用 UTF-16LE + BOM
    with open(os.path.join(ROOT, "启动 EdgeDock.vbs"), "wb") as fh:
        fh.write(b"\xff\xfe" + VBS.replace("\n", "\r\n").encode("utf-16-le"))
    # cmd.exe 在中文 Windows 上按 GBK(936) 读批处理文件
    for name, text in (("安装运行环境.bat", INSTALL), ("调试运行.bat", DEBUG)):
        with open(os.path.join(ROOT, name), "wb") as fh:
            fh.write(text.replace("\n", "\r\n").encode("gbk"))
    for n in ("启动 EdgeDock.vbs", "安装运行环境.bat", "调试运行.bat"):
        p = os.path.join(ROOT, n)
        with open(p, "rb") as fh:
            head = fh.read(4)
        print("  %-24s %6d bytes  head=%s" % (n, os.path.getsize(p), head.hex()))


if __name__ == "__main__":
    main()
