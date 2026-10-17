# -*- coding: utf-8 -*-
"""EdgeDock 启动入口（.pyw 双击运行无控制台窗口）。"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from edgedock.app import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
