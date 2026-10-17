@echo off
cd /d "%~dp0"
echo EdgeDock 调试模式（关闭本窗口即退出程序）
echo.
".venv\Scripts\python.exe" main.pyw
echo.
echo 程序已退出。
pause
