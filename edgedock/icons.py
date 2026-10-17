# -*- coding: utf-8 -*-
"""图标提取与缓存。

* 主图标从 Windows Shell 的「超大图标列表」取 256x256，保证高分屏下依旧锐利
* 解析结果落盘缓存在 cache/icons 下，键值 = 路径 + 修改时间
* 提取放在后台线程，避免首次启动卡住界面
"""
from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import QFileInfo, QObject, QThread, Qt, Signal
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import QFileIconProvider

from . import winapi

MASTER = 256


def _key(path: str) -> str:
    try:
        st = os.stat(path)
        stamp = "%d|%d" % (int(st.st_mtime), st.st_size)
    except Exception:
        stamp = "0|0"
    raw = "%s|%s|v2" % (os.path.normcase(os.path.abspath(path)), stamp)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def _extract_png(path: str, png_path: str) -> bool:
    """把一个文件的图标写成 PNG，成功返回 True。"""
    winapi.ensure_com()
    hicon = 0
    try:
        hicon = winapi.extract_hicon(path)
        if hicon:
            data = winapi.hicon_to_bgra(hicon, MASTER)
            if data:
                img = QImage(data, MASTER, MASTER, QImage.Format_ARGB32).copy()
                if not img.isNull() and img.save(png_path, "PNG"):
                    return True
    except Exception:
        pass
    finally:
        if hicon:
            try:
                winapi.user32.DestroyIcon(winapi.wintypes.HICON(hicon))
            except Exception:
                pass
    # 兜底：Qt 自带的图标提供器
    try:
        icon = QFileIconProvider().icon(QFileInfo(path))
        pm = icon.pixmap(MASTER, MASTER)
        if not pm.isNull() and pm.width() > 1:
            if pm.save(png_path, "PNG"):
                return True
    except Exception:
        pass
    return False


class _Worker(QThread):
    done = Signal(str, str)      # path, png_path（空串表示失败）

    def __init__(self, cache_dir: str, paths: list[str], parent=None):
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.paths = list(paths)

    def run(self) -> None:
        for path in self.paths:
            png = os.path.join(self.cache_dir, _key(path) + ".png")
            ok = os.path.exists(png) or _extract_png(path, png)
            self.done.emit(path, png if ok else "")


class IconStore(QObject):
    """对外只暴露「给我某个路径的图标位图」。"""

    ready = Signal(str)          # 某个图标就绪（path）

    def __init__(self, cache_dir: str, parent=None):
        super().__init__(parent)
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._png: dict[str, str] = {}
        self._pm: dict[tuple, QPixmap] = {}
        self._fallback: dict[tuple, QPixmap] = {}
        self._worker: _Worker | None = None
        self._pending: set[str] = set()

    # ------------------------------------------------------------------
    def png_of(self, path: str) -> str | None:
        """仅查缓存，不触发生成。"""
        hit = self._png.get(path)
        if hit and os.path.exists(hit):
            return hit
        if path and os.path.exists(path):
            png = os.path.join(self.cache_dir, _key(path) + ".png")
            if os.path.exists(png):
                self._png[path] = png
                return png
        return None

    def warm(self, paths: list[str]) -> None:
        """后台把还没有缓存的图标提取出来。"""
        need = [p for p in dict.fromkeys(paths)
                if p and os.path.exists(p) and not self.png_of(p)]
        if not need:
            return
        if self._worker and self._worker.isRunning():
            self._pending.update(need)
            return
        self._worker = _Worker(self.cache_dir, need, self)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_done(self, path: str, png: str) -> None:
        if png:
            self._png[path] = png
            self._pm = {k: v for k, v in self._pm.items() if k[0] != path}
            self.ready.emit(path)

    def _on_finished(self) -> None:
        if self._pending:
            extra = list(self._pending)
            self._pending.clear()
            self.warm(extra)

    def stop(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.wait(2500)

    # ------------------------------------------------------------------
    def pixmap(self, path: str, size: int, dpr: float = 1.0) -> QPixmap:
        """返回 size 逻辑像素、适配 DPR 的图标。"""
        physical = max(8, int(round(size * dpr)))
        ck = (path, physical)
        cached = self._pm.get(ck)
        if cached is not None:
            return cached

        pm = QPixmap()
        png = self.png_of(path)
        if png:
            src = QPixmap(png)
            if not src.isNull():
                pm = src.scaled(physical, physical, Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
        if pm.isNull():
            pm = self._placeholder(path, physical)
        if dpr != 1.0:
            pm.setDevicePixelRatio(dpr)
        self._pm[ck] = pm
        return pm

    def _placeholder(self, path: str, physical: int) -> QPixmap:
        ck = (path, physical)
        hit = self._fallback.get(ck)
        if hit is not None:
            return hit
        pm = QPixmap(physical, physical)
        pm.fill(Qt.transparent)
        pt = QPainter(pm)
        pt.setRenderHint(QPainter.Antialiasing, True)
        r = physical * 0.22
        path_ = QPainterPath()
        path_.addRoundedRect(1, 1, physical - 2, physical - 2, r, r)
        grad = QLinearGradient(0, 0, physical, physical)
        grad.setColorAt(0.0, QColor(255, 255, 255, 38))
        grad.setColorAt(1.0, QColor(255, 255, 255, 16))
        pt.fillPath(path_, grad)
        pt.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, physical / 64.0)))
        pt.drawPath(path_)
        letter = ""
        base = os.path.splitext(os.path.basename(path))[0]
        for ch in base:
            if ch.isalnum():
                letter = ch.upper()
                break
        if letter:
            f = pt.font()
            f.setPixelSize(int(physical * 0.46))
            f.setBold(True)
            pt.setFont(f)
            pt.setPen(QColor(255, 255, 255, 170))
            pt.drawText(pm.rect(), Qt.AlignCenter, letter)
        pt.end()
        self._fallback[ck] = pm
        return pm
