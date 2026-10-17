# -*- coding: utf-8 -*-
"""生成 EdgeDock 的 .ico 图标（纯手写 ICO 容器 + Qt 绘制，无需额外依赖）。

用法： python tools/make_icon.py
输出： assets/edgedock.ico
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)

SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    u = size / 64.0
    accent = QColor("#FF7A2D")

    body = QRectF(6 * u, 16 * u, 52 * u, 34 * u)
    path = QPainterPath()
    path.addRoundedRect(body, 9 * u, 9 * u)
    g = QLinearGradient(body.topLeft(), body.bottomLeft())
    g.setColorAt(0.0, QColor(58, 61, 71))
    g.setColorAt(1.0, QColor(22, 23, 28))
    p.fillPath(path, g)
    p.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, 1.3 * u)))
    p.drawPath(path)

    p.setPen(QPen(accent, 3.6 * u, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(13 * u, 33 * u), QPointF(51 * u, 33 * u))

    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 215))
    p.drawRoundedRect(QRectF(25 * u, 41 * u, 14 * u, 3.4 * u), 1.7 * u, 1.7 * u)
    p.end()
    return pm.toImage()


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main() -> None:
    QGuiApplication([])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "assets")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "edgedock.ico")

    entries = []
    for s in SIZES:
        entries.append((s, png_bytes(draw(s))))

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = len(header) + 16 * len(entries)
    dir_bytes, data_bytes = b"", b""
    for size, data in entries:
        dim = 0 if size >= 256 else size
        dir_bytes += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                                 len(data), offset)
        data_bytes += data
        offset += len(data)

    with open(out, "wb") as fh:
        fh.write(header + dir_bytes + data_bytes)

    # 顺便导出一张 PNG 预览
    draw(256).save(os.path.join(out_dir, "edgedock_preview.png"), "PNG")
    print("已生成:", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()
