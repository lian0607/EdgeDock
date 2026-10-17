@echo off
cd /d "%~dp0"
echo 正在创建独立运行环境（.venv）...
"D:\Program Files\Python\Python313\python.exe" -m venv .venv
if errorlevel 1 (
    echo.
    echo 未找到 D:\Program Files\Python\Python313\python.exe
    echo 请把本文件里的 python.exe 路径改成实际路径后重试。
    pause
    exit /b 1
)
echo 正在安装依赖 PySide6 ...
".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple PySide6-Essentials
if errorlevel 1 (
    echo.
    echo 安装失败，请检查网络后重试。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" tools\make_icon.py
echo.
echo 完成，双击「启动 EdgeDock.vbs」即可运行。
pause
