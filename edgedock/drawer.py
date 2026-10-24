# -*- coding: utf-8 -*-
"""抽屉主体：贴边面板 + 图标按钮 + 滑出/收起动画。"""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF,
                            Qt, QTimer, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from . import apps as apps_mod
from . import theme as theme_mod
from . import winapi
from .config import Config

SHADOW = 0           # 不留投影留白（窗口与面板等大，避免遮挡下层点击）


# ==========================================================================
#  几何计算
# ==========================================================================
class Geo:
    """根据配置算出面板/窗口的尺寸与位置。"""

    def __init__(self, cfg):
        self.apply(cfg)

    def apply(self, cfg) -> None:
        app = QApplication.instance()
        scr = app.primaryScreen().availableGeometry() if app else QRect(0, 0, 1920, 1080)
        self.scr = scr
        self.edge = cfg["edge"] if cfg["edge"] in ("top", "bottom", "left", "right") else "top"
        self.horizontal = self.edge in ("top", "bottom")

        self.icon = int(cfg["icon_size"])
        self.scale = float(cfg["hover_scale"])
        self.btn = int(round(self.icon * self.scale)) + 2
        self.pad = int(cfg["padding"])
        self.gap = int(cfg["gap"])
        self.thick = self.btn + 2 * self.pad          # 面板厚度
        self.peek = max(0, min(int(cfg["peek"]), self.thick))
        self.slot = cfg["slot"]
        self.offset = int(cfg["offset"])

        avail = scr.width() if self.horizontal else scr.height()
        self.max_len = max(160, int(avail * 0.86))

    # ------------------------------------------------------------------
    @property
    def step(self) -> int:
        """相邻两个图标槽位的中心距。"""
        return self.btn + self.gap

    @property
    def cross(self) -> int:
        """图标条在面板厚度方向上的起点（居中）。"""
        return self.pad + (self.thick - 2 * self.pad - self.btn) // 2

    def content_len(self, count: int) -> int:
        """内容总长：图标 + 间距 + 两端留白（两端留白与上下内边距一致）。"""
        if count <= 0:
            return 320
        return count * self.btn + (count - 1) * self.gap + 2 * self.pad

    def panel_len(self, count: int) -> int:
        if count <= 0:
            return min(320, self.max_len)
        return max(76, min(self.content_len(count), self.max_len))

    def window_rect(self, count: int) -> QRect:
        """窗口矩形：始终含面板 + 投影留白，位置固定不动。"""
        L = self.panel_len(count)
        scr = self.scr

        def along(lo: int, span: int) -> int:
            """沿边方向上的起点：靠起始 / 居中 / 靠末端，再加人工偏移。"""
            if self.slot == "start":
                return lo + self.offset
            if self.slot == "end":
                return lo + span - L - self.offset
            return lo + (span - L) // 2 + self.offset

        if self.horizontal:
            w, h = L, self.thick + SHADOW
            y = scr.top() if self.edge == "top" else scr.bottom() - h + 1
            return QRect(along(scr.left(), scr.width()), y, w, h)
        w, h = self.thick + SHADOW, L
        x = scr.left() if self.edge == "left" else scr.right() - w + 1
        return QRect(x, along(scr.top(), scr.height()), w, h)

    def panel_offset(self, reveal: float) -> QPoint:
        """面板相对窗口左上角的偏移（reveal=1 完全展开，0 完全收起）。"""
        d = int(round((self.thick - self.peek) * (1.0 - reveal)))
        if self.edge == "top":
            return QPoint(0, -d)
        if self.edge == "bottom":
            return QPoint(0, SHADOW + d)
        if self.edge == "left":
            return QPoint(-d, 0)
        return QPoint(SHADOW + d, 0)

    def panel_screen_rect(self, count: int, reveal: float = 1.0) -> QRect:
        """面板在屏幕坐标系里的矩形。"""
        wr = self.window_rect(count)
        off = self.panel_offset(reveal)
        L = self.panel_len(count)
        w, h = (L, self.thick) if self.horizontal else (self.thick, L)
        return QRect(wr.x() + off.x(), wr.y() + off.y(), w, h)

    def trigger_hit(self, pos: QPoint, trigger_px: int, count: int,
                    slack: int = 60) -> bool:
        """鼠标是否落在贴边的触发带上。"""
        r = self.panel_screen_rect(count, 0.0)
        if self.horizontal:
            # 贴边方向看 y，沿边方向的容差看 x
            near_edge = pos.y() <= self.scr.top() + trigger_px if self.edge == "top" \
                else pos.y() >= self.scr.bottom() - trigger_px
            lo, hi, along = r.left() - slack, r.right() + slack, pos.x()
        else:
            near_edge = pos.x() <= self.scr.left() + trigger_px \
                if self.edge == "left" else pos.x() >= self.scr.right() - trigger_px
            lo, hi, along = r.top() - slack, r.bottom() + slack, pos.y()
        return near_edge and lo <= along <= hi


# ==========================================================================
#  图标按钮
# ==========================================================================
class IconButton(QWidget):
    activated = Signal(str)
    hoverChanged = Signal(str, bool, QRect)   # 显示名, entered, 全局矩形
    menuRequested = Signal(str, object)
    dragStarted = Signal(object)              # self：按下并移动超过阈值，开始拖动排序
    dragMoved = Signal(object, QPoint)        # self, 全局坐标
    dragFinished = Signal(object, bool)       # self, 是否真的挪动过

    def __init__(self, item: dict, geo: Geo, store, t: dict, parent=None):
        super().__init__(parent)
        self.item = item
        self.geo = geo
        self.store = store
        self.t = t
        # 显示名提前算好：悬停浮标和右键菜单都要用，省得每处再查一遍配置
        self.name = item.get("name") or \
            os.path.splitext(os.path.basename(item.get("path", "")))[0] or "应用"
        self._hover = 0.0
        self._press = False
        # 对外只用这个标识（appid 优先，其次路径）
        self.key = Config.key(item)
        self.spec = apps_mod.spec_of(item)
        # 「所有应用」的条目由系统注册，不存在找不到的问题
        self.missing = (not item.get("appid")
                        and not os.path.exists(item.get("path") or ""))
        self.setFixedSize(geo.btn, geo.btn)
        self.setMouseTracking(True)
        # 拖动排序用
        self.dragging = False
        self.grab_offset = QPointF(0.0, 0.0)   # 按下点相对按钮左上角的偏移
        self._press_global = QPoint()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        # 松手后滑回槽位的补间
        self._glide = QVariantAnimation(self)
        self._glide.setDuration(140)
        self._glide.setEasingCurve(QEasingCurve.OutCubic)
        self._glide.valueChanged.connect(self._on_glide)

    def _on_glide(self, value) -> None:
        # QVariantAnimation 在 QPoint 起止值下回调给的就是 QPoint，别再 toPoint()
        self.move(value.toPoint() if isinstance(value, QPointF) else value)

    def glide_to(self, pos: QPoint) -> None:
        self._glide.stop()
        self._glide.setStartValue(self.pos())
        self._glide.setEndValue(QPoint(pos))
        self._glide.start()

    def stop_glide(self) -> None:
        self._glide.stop()

    def _on_anim(self, value):
        self._hover = float(value)
        self.update()

    def _animate(self, to: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(float(to))
        self._anim.start()

    # ------------------------------------------------------------------
    def _global_rect(self) -> QRect:
        return QRect(self.mapToGlobal(QPoint(0, 0)), self.size())

    def enterEvent(self, event):
        self._animate(1.0)
        self.hoverChanged.emit(self.name, True, self._global_rect())
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        self.hoverChanged.emit(self.name, False, self._global_rect())
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = True
            self._press_global = event.globalPosition().toPoint()
            self.grab_offset = event.position()      # QPointF，局部坐标
            self.update()

    def mouseMoveEvent(self, event):
        """按下后移动超过系统阈值 -> 进入「拖动排序」。"""
        if not self._press:
            super().mouseMoveEvent(event)
            return
        gp = event.globalPosition().toPoint()
        if not self.dragging:
            if (gp - self._press_global).manhattanLength() \
                    < QApplication.startDragDistance():
                return
            self.dragging = True
            self._animate(1.0)
            self.setCursor(Qt.ClosedHandCursor)      # 给个「抓住了」的反馈
            self.raise_()                            # 拖起来的那枚压在最上层
            self.dragStarted.emit(self)
        self.dragMoved.emit(self, gp)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        was_drag = self.dragging
        self._press = False
        self.dragging = False
        self.unsetCursor()
        self.update()
        if was_drag:
            self.dragFinished.emit(self, True)       # 拖动排序收尾，不触发启动
            return
        if self.rect().contains(event.position().toPoint()):
            self.activated.emit(self.key)

    def contextMenuEvent(self, event):
        if self.dragging:
            return
        self.menuRequested.emit(self.key, event.globalPos())

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = min(13.0, r.height() / 2.6)

        if self.dragging:
            # 「拿起来」的手感：先垫一层投影，再叠高亮底
            sh = QPainterPath()
            sh.addRoundedRect(r.adjusted(1.6, 3.4, -1.6, 1.2), rad, rad)
            p.fillPath(sh, QColor(0, 0, 0,
                                  62 if self.t["name"] == "light" else 118))

        # 拖动过程中始终保持高亮（不依赖悬停动画的进度）
        hi = max(self._hover, 1.0 if self.dragging else 0.0)
        if hi > 0.01:
            bg = QColor(self.t["hover"])
            bg.setAlpha(int(self.t["hover"].alpha() * hi))
            path = QPainterPath()
            path.addRoundedRect(r, rad, rad)
            p.fillPath(path, bg)
            ring = QColor(self.t["hover_ring"])
            ring.setAlpha(int(ring.alpha() * hi))
            pen = QPen(ring, 1.6 if self.dragging else 1.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        factor = 1.0 + (self.geo.scale - 1.0) * hi
        if self._press and not self.dragging:
            factor *= 0.92
        side = int(self.geo.icon * factor)
        dpr = self.devicePixelRatioF() or 1.0
        pm = self.store.pixmap(self.spec, side, dpr)
        if not pm.isNull():
            w = pm.width() / (pm.devicePixelRatio() or 1.0)
            h = pm.height() / (pm.devicePixelRatio() or 1.0)
            x = (self.width() - w) / 2.0
            y = (self.height() - h) / 2.0
            if self.missing:
                p.setOpacity(0.42)
            p.drawPixmap(int(round(x)), int(round(y)), pm)
        p.end()


# ==========================================================================
#  名称浮标
# ==========================================================================
class NameToast(QWidget):
    """图标名称浮标。

    注意：这里不能用 setWindowOpacity —— Windows 上「全局透明度」与
    Qt 的逐像素透明窗口（UpdateLayeredWindow）互斥，会导致窗口画不出来。
    改为在 paintEvent 里按 _alpha 调整绘制透明度。
    """

    def __init__(self, t: dict):
        super().__init__(None, Qt.Tool)
        self.t = t
        self._text = ""
        self._font = QFont("Microsoft YaHei UI", 9)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus |
                            Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._op = QVariantAnimation(self)
        self._op.setDuration(150)
        self._op.setEasingCurve(QEasingCurve.OutCubic)
        self._op.valueChanged.connect(self._on_op)
        self._op.finished.connect(self._on_op_done)
        self._alpha = 0.0
        self.hide()

    def _on_op(self, v):
        self._alpha = float(v)
        self.update()

    def _on_op_done(self):
        # 只有淡出结束才真正隐藏，避免淡入起始帧被误判
        if self._alpha <= 0.01:
            self.hide()

    def _fade(self, to: float) -> None:
        self._op.stop()
        self._op.setStartValue(self._alpha)
        self._op.setEndValue(float(to))
        self._op.start()

    def show_name(self, text: str, anchor: QRect, edge: str) -> None:
        self._text = text or ""
        fm = QFontMetrics(self._font)
        w = fm.horizontalAdvance(self._text) + 28
        h = fm.height() + 17
        self.resize(w, h)
        # 浮标压在图标外侧，贴着面板那条边
        gap = 12
        if edge in ("top", "bottom"):
            x = anchor.center().x() - w // 2
            y = anchor.bottom() + gap if edge == "top" else anchor.top() - h - gap
        else:
            y = anchor.center().y() - h // 2
            x = anchor.right() + gap if edge == "left" else anchor.left() - w - gap
        scr = QApplication.primaryScreen().availableGeometry()
        x = max(scr.left() + 6, min(x, scr.right() - w - 6))
        y = max(scr.top() + 6, min(y, scr.bottom() - h - 6))
        self.move(x, y)
        if not self.isVisible():
            self.show()
        self.raise_()
        hwnd = int(self.winId())
        winapi.as_tool_window(hwnd)
        winapi.set_click_through(hwnd, True)
        self._fade(1.0)

    def hide_name(self) -> None:
        self._fade(0.0)

    def paintEvent(self, event):
        if self._alpha <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setOpacity(max(0.0, min(1.0, self._alpha)))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        p.fillPath(path, self.t["toast_bg"])
        p.setPen(QPen(self.t["border"], 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setFont(self._font)
        p.setPen(QColor(self.t["text"]))
        p.drawText(self.rect(), Qt.AlignCenter, self._text)
        p.end()


# ==========================================================================
#  抽屉窗口
# ==========================================================================
class DrawerWindow(QWidget):
    launchRequested = Signal(str)
    settingsRequested = Signal()
    quitRequested = Signal()
    dropped = Signal(int, int)          # 新增数量, 重复数量

    def __init__(self, cfg, store):
        super().__init__(None)
        self.cfg = cfg
        self.store = store
        self.t = theme_mod.get(cfg["theme"])
        self.geo = Geo(cfg)

        self.reveal = 0.0
        self.target = 0.0
        self.pinned = bool(cfg["pin"])
        self.suspended = False        # 全屏游戏期间整条边栏让路（见 set_suspended）
        self.hold_open = False        # 打开设置窗口期间强制保持展开
        self.drag_over = False        # 正在被拖拽悬停（从桌面拖文件进来）
        # 抽屉内拖动排序
        self.drag_index = None        # 正在被拖动的图标在 buttons 里的下标
        self.drop_index = None        # 目标槽位下标

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
                            Qt.Tool | Qt.WindowDoesNotAcceptFocus |
                            Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_AlwaysStackOnTop, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)     # 支持从桌面 / 资源管理器直接拖入

        self.panel = _Panel(self)
        self.toast = NameToast(self.t)

        self.buttons: list[IconButton] = []
        self._scroll = 0
        self._content_len = 0

        self.store.ready.connect(self._on_icon_ready)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_reveal)

        self._dwell = 0
        self._away = 0
        self._poll = QTimer(self)
        self._poll.setInterval(40)
        self._poll.timeout.connect(self._tick)

        self.rebuild()
        self.show()
        self._apply_win_style()

    # ------------------------------------------------------------------
    def _apply_win_style(self) -> None:
        hwnd = int(self.winId())
        winapi.as_tool_window(hwnd)
        winapi.set_click_through(hwnd, True)
        self._poll.start()

    # ------------------------------------------------------------------
    #  构建内容
    # ------------------------------------------------------------------
    def rebuild(self) -> None:
        self.geo.apply(self.cfg)
        self.t = theme_mod.get(self.cfg["theme"])
        self.toast.t = self.t
        self.drag_index = None          # 重建时清掉拖动排序状态
        self.drop_index = None
        for b in self.buttons:
            b.setParent(None)
            b.deleteLater()
        self.buttons = []

        items = self.cfg.items
        for it in items:
            btn = IconButton(it, self.geo, self.store, self.t, self.panel)
            btn.activated.connect(self._on_activate)
            btn.hoverChanged.connect(self._on_hover)
            btn.menuRequested.connect(self._on_menu)
            btn.dragStarted.connect(self._on_drag_started)
            btn.dragMoved.connect(self._on_drag_moved)
            btn.dragFinished.connect(self._on_drag_finished)
            btn.show()
            self.buttons.append(btn)

        self._content_len = self.geo.content_len(len(self.buttons))
        self._scroll = 0
        self._layout_panel()
        self.store.warm([i.spec for i in self.buttons])

    def _on_icon_ready(self, spec: str) -> None:
        """图标后台提取完成 -> 让对应按钮重画。"""
        for b in self.buttons:
            if b.spec == spec:
                b.update()
        self.panel.update()

    def _layout_panel(self) -> None:
        wr = self.geo.window_rect(len(self.buttons))
        self.setFixedSize(wr.size())
        self.move(wr.topLeft())
        L = self.geo.panel_len(len(self.buttons))
        if self.geo.horizontal:
            self.panel.setFixedSize(L, self.geo.thick)
        else:
            self.panel.setFixedSize(self.geo.thick, L)
        self._place_buttons()
        self._on_reveal(self.reveal)

    def _content_base(self, n: int) -> int:
        """第一个槽位在沿边方向上的起点（相对面板）。"""
        pad = self.geo.pad
        content = self.geo.content_len(n)
        span = content - 2 * pad                  # 图标条本身的总长
        if content <= self.geo.panel_len(n):
            return (self.geo.panel_len(n) - span) // 2
        return pad + self._scroll

    def slot_rect(self, index: int) -> QRect:
        """第 index 个槽位在面板坐标系里的矩形（用来画占位凹槽）。"""
        b = self.geo.btn
        along = self._content_base(len(self.buttons)) + index * self.geo.step
        if self.geo.horizontal:
            return QRect(along, self.geo.cross, b, b)
        return QRect(self.geo.cross, along, b, b)

    def _drop_index_at(self, pos: QPoint) -> int:
        """把鼠标位置换算成「应该插到第几个槽位」。"""
        n = len(self.buttons)
        if n <= 1:
            return 0
        along = pos.x() if self.geo.horizontal else pos.y()
        # 槽位中心依次在 base + i*step + b/2，反解出最近的那个 i
        k = int(round((along - self._content_base(n) - self.geo.btn / 2.0)
                      / float(self.geo.step)))
        return max(0, min(n - 1, k))

    def _place_buttons(self) -> None:
        n = len(self.buttons)
        if not n:
            return
        for b in self.buttons:
            b.stop_glide()                 # 重新排布时先取消未完成的滑回动画

        # 拖动排序时：被拖的那枚不参与排布，其余图标整体前移一格，
        # 空出来的位置就是「将要落下的槽位」，视觉上就是那个虚线凹槽。
        drag_i = self.drag_index
        if drag_i is None:
            order = list(range(n))
            slots = order
        else:
            target = drag_i if self.drop_index is None else self.drop_index
            order = [i for i in range(n) if i != drag_i]
            slots = [i for i in range(n) if i != target]

        base = self._content_base(n)
        for slot, idx in zip(slots, order):
            along = base + slot * self.geo.step
            if self.geo.horizontal:
                self.buttons[idx].move(along, self.geo.cross)
            else:
                self.buttons[idx].move(self.geo.cross, along)

    # ------------------------------------------------------------------
    #  动画
    # ------------------------------------------------------------------
    def _on_reveal(self, value) -> None:
        self.reveal = float(value)
        self.panel.move(self.geo.panel_offset(self.reveal))
        # 注意：动画第一帧的 reveal 还是 0，只按 reveal 判断会把刚在 expand()
        # 里关掉的鼠标穿透又打开一帧，拖拽落点就可能被穿过去。
        # 所以只要「目标状态是展开」，就一律保持可交互。
        interactive = self.reveal > 0.02 or self.target > 0.5
        winapi.set_click_through(int(self.winId()), not interactive)
        if self.reveal < 0.02:
            self.toast.hide_name()
        self.update()

    def _animate_to(self, value: float, duration: int = 220) -> None:
        if abs(self.target - value) < 0.001 and abs(self.reveal - value) < 0.001:
            return
        self.target = value
        self._anim.stop()
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.OutCubic if value > 0.5
                                  else QEasingCurve.InOutCubic)
        self._anim.setStartValue(self.reveal)
        self._anim.setEndValue(float(value))
        self._anim.start()

    def expand(self) -> None:
        if self.suspended:
            return
        self._dwell = 0
        self._away = 0
        # 立刻关掉鼠标穿透，否则拖拽落点会被穿过（拖放需要在展开瞬间就可命中）
        winapi.set_click_through(int(self.winId()), False)
        self._animate_to(1.0, 240)

    def collapse(self) -> None:
        if self.pinned:
            return
        self._animate_to(0.0, 200)

    def toggle(self) -> None:
        if self.suspended:
            return
        if self.target > 0.5:
            self.pinned = False
            self.collapse()
        else:
            self.expand()

    def set_pinned(self, on: bool) -> None:
        self.pinned = bool(on)
        self.cfg["pin"] = self.pinned
        self.cfg.save()
        if self.pinned:
            self.expand()

    def set_suspended(self, on: bool) -> None:
        """全屏游戏/全屏视频期间让路：整条边栏藏起来，也不再响应贴边。

        只是隐藏窗口，不销毁、不重建 —— 退出游戏后原样回来，图标的
        布局和滚动位置都还在。
        """
        on = bool(on)
        if on == self.suspended:
            return
        self.suspended = on
        if on:
            self.toast.hide_name()
            self._anim.stop()
            self.reveal = self.target = 0.0
            self._on_reveal(0.0)
            self._dwell = self._away = 0
            self._poll.stop()                 # 停止轮询：不再判定贴边
            self.hide()
        else:
            self.show()
            self._apply_win_style()           # 重新贴 TOOLWINDOW / 穿透，并重启轮询
            if self.pinned:                   # 之前钉住的，回来还是钉住的
                self.expand()

    # ------------------------------------------------------------------
    #  轮询：贴边唤出 / 移开收起
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self.suspended or not self.isVisible():
            return
        pos = QCursor.pos()
        cfg = self.cfg
        if self.target < 0.5:
            px = max(1, int(cfg["trigger_px"]))
            # 按住左键拖东西时立刻弹出（不等停留判定）；
            # 同时把触发带收窄到面板正上方，避免拖窗口到顶部最大化时被误触。
            dragging = bool(winapi.user32.GetAsyncKeyState(0x01) & 0x8000)
            in_zone = self.geo.trigger_hit(pos, px, len(self.buttons),
                                           slack=0 if dragging else 60)
            if in_zone:
                self._dwell += self._poll.interval()
                if dragging or self._dwell >= max(0, int(cfg["dwell"])):
                    self.expand()
            else:
                self._dwell = 0
        else:
            # 拖动排序期间不要自动收起，否则拖到一半抽屉没了
            if self.pinned or self.hold_open or self.drag_index is not None:
                self._away = 0
                return
            keep = self.geo.panel_screen_rect(len(self.buttons), 1.0)
            m = int(cfg["keep_open_px"])
            keep = keep.adjusted(-m, -m, m, m)
            if self.toast.isVisible():
                keep = keep.united(self.toast.geometry())
            if keep.contains(pos):
                self._away = 0
            else:
                self._away += self._poll.interval()
                if self._away >= max(120, int(cfg["hide_delay"])):
                    self.collapse()

    # ------------------------------------------------------------------
    #  事件
    # ------------------------------------------------------------------
    def _on_activate(self, key: str) -> None:
        self.launchRequested.emit(key)
        if self.cfg["hide_after_launch"] and not self.pinned:
            QTimer.singleShot(120, self.collapse)

    def _on_hover(self, name: str, entered: bool, global_rect: QRect) -> None:
        if not self.cfg["show_labels"] or self.drag_index is not None:
            return
        if not entered:
            self.toast.hide_name()
            return
        self.toast.show_name(name, global_rect, self.geo.edge)

    # ------------------------------------------------------------------
    #  抽屉内拖动排序
    # ------------------------------------------------------------------
    def _auto_scroll(self, local: QPoint) -> None:
        """拖到面板两端时自动滚动，图标很多时也能拖到首尾。"""
        overflow = self._content_len - self.geo.panel_len(len(self.buttons))
        if overflow <= 0:
            return
        length = self.geo.panel_len(len(self.buttons))
        along = local.x() if self.geo.horizontal else local.y()
        edge = max(26, self.geo.btn)
        if along < edge:
            delta = 16
        elif along > length - edge:
            delta = -16
        else:
            return
        new = max(-overflow, min(0, self._scroll + delta))
        if new != self._scroll:
            self._scroll = new
            self._place_buttons()

    def _on_drag_started(self, btn) -> None:
        try:
            self.drag_index = self.buttons.index(btn)
        except ValueError:
            return
        self.drop_index = self.drag_index
        self.toast.hide_name()                     # 拖动时不要弹名称浮标
        btn.raise_()
        self._place_buttons()
        self.panel.update()

    def _on_drag_moved(self, btn, global_pos: QPoint) -> None:
        if self.drag_index is None:
            return
        local = self.panel.mapFromGlobal(global_pos)
        p = QPointF(local) - btn.grab_offset       # 让图标保持在手指「按住」的位置
        b = self.geo.btn
        panel_len = self.geo.panel_len(len(self.buttons))
        # 只在「沿边方向」跟手，横过来那一位固定在图标条上：
        # 否则鼠标往下拖会把图标带出面板、被裁掉看不见。
        # 再夹一下两端，保证图标始终完整露在面板里。
        cross = self.slot_rect(self.drag_index)
        raw = p.x() if self.geo.horizontal else p.y()
        along = max(2, min(int(round(raw)), panel_len - b - 2))
        btn.move(QPoint(along, cross.y()) if self.geo.horizontal
                 else QPoint(cross.x(), along))
        self._auto_scroll(local)
        k = self._drop_index_at(local)
        if k != self.drop_index:
            self.drop_index = k
            self._place_buttons()
        self.panel.update()

    def _on_drag_finished(self, btn, committed: bool) -> None:
        src, dst = self.drag_index, self.drop_index
        self.drag_index = None
        self.drop_index = None
        btn.update()
        dropped_at = btn.pos()                      # 松手时图标停在哪儿
        moved = committed and src is not None and dst is not None and src != dst
        if moved:
            # buttons 与 cfg.items 的顺序始终一一对应，一起搬
            self.buttons.insert(dst, self.buttons.pop(src))
            self.cfg.move_item_to(btn.key, dst)
            self.cfg.save()
        self._place_buttons()
        if moved:
            # 从松手的位置滑回槽位，别硬跳
            target = btn.pos()
            btn.move(dropped_at)
            btn.glide_to(target)
        self.panel.update()

    def _on_menu(self, key: str, global_pos: QPoint) -> None:
        menu = self._menu()
        it = self.cfg.find(key) or {"path": key, "name": ""}
        # 判据是「能不能真拉起来」：快捷方式被删了、记下的目标还在，照样能开，
        # 这种情况下还把「打开」置灰就说不通了。
        act_open = menu.addAction("打开")
        act_open.setEnabled(self.cfg.launchable(it))
        where = _existing_path(it)
        act_loc = menu.addAction("打开文件所在位置")
        # 商店应用（只有 appid）压根没有磁盘上的位置，这一项直接置灰
        act_loc.setEnabled(bool(where))
        menu.addSeparator()
        hint = menu.addAction("按住图标拖动即可调顺序")
        hint.setEnabled(False)                     # 灰色小提示，点不了
        act_front = menu.addAction("移到最前")
        act_back = menu.addAction("移到最后")
        menu.addSeparator()
        act_kill = menu.addAction("从抽屉中移除")
        menu.addSeparator()
        self._add_tail(menu)                       # 设置… / 退出

        act_open.triggered.connect(lambda: self.launchRequested.emit(key))
        act_loc.triggered.connect(lambda: reveal_in_explorer(where))
        act_front.triggered.connect(lambda: self._reorder(key, -999))
        act_back.triggered.connect(lambda: self._reorder(key, 999))
        act_kill.triggered.connect(lambda: self._remove(key))
        self._popup(menu, global_pos)

    def _reorder(self, key: str, delta: int) -> None:
        items = self.cfg.items
        for idx, it in enumerate(items):
            if self.cfg.key(it) == key:
                new = 0 if delta < 0 else len(items) - 1
                items.insert(new, items.pop(idx))
                break
        self.cfg.save()
        self.rebuild()

    def _remove(self, key: str) -> None:
        self.cfg.remove_item(key)
        self.cfg.save()
        self.rebuild()

    def _menu(self) -> QMenu:
        """统一样式的右键菜单（抽屉空白处、图标上共用）。"""
        menu = QMenu(self)
        menu.setStyleSheet(theme_mod.menu_qss(self.t))
        return menu

    def _add_tail(self, menu: QMenu) -> None:
        """两个右键菜单的尾巴都是这两项，别写两遍。"""
        menu.addAction("设置…", self.settingsRequested.emit)
        menu.addAction("退出 EdgeDock", self.quitRequested.emit)

    def _popup(self, menu: QMenu, pos: QPoint) -> None:
        """弹菜单期间把抽屉按住，别让它按时收起。

        菜单挂在抽屉窗口上，是它的子窗口：鼠标一离开面板，hide_delay(700ms)
        一到抽屉就收，菜单跟着一起没影 —— 手慢一点，菜单就是「闪一下」。
        这里临时按住，松开时还原上一手的状态（设置窗口开着的时候本来就是
        按住的，不能被我这一趟给松掉）。
        """
        prev = self.hold_open
        self.hold_open = True
        self._away = 0
        try:
            menu.exec(pos)
        finally:
            self.hold_open = prev
            self._away = 0
            menu.deleteLater()        # 每次右键都新建一个，别攒着

    def contextMenuEvent(self, event):
        menu = self._menu()
        a_pin = menu.addAction("固定展开")
        a_pin.setCheckable(True)
        a_pin.setChecked(self.pinned)
        a_pin.toggled.connect(self.set_pinned)
        menu.addSeparator()
        self._add_tail(menu)
        self._popup(menu, event.globalPos())

    def wheelEvent(self, event):
        overflow = self._content_len - self.geo.panel_len(len(self.buttons))
        if overflow <= 0:
            return
        delta = event.angleDelta().x() or event.angleDelta().y()
        self._scroll = max(-overflow, min(0, self._scroll + int(delta * 0.6)))
        self._place_buttons()

    # ------------------------------------------------------------------
    #  拖放：从桌面 / 资源管理器把快捷方式拖进抽屉
    # ------------------------------------------------------------------
    @staticmethod
    def _dropped_files(event) -> list[str]:
        """拖进来的本地文件 / 文件夹（也允许拖文件夹）。"""
        md = event.mimeData()
        if not md.hasUrls():
            return []
        return [p for p in (u.toLocalFile() for u in md.urls())
                if p and (os.path.isfile(p) or os.path.isdir(p))]

    def dragEnterEvent(self, event):
        if self._dropped_files(event):
            self.drag_over = True
            self.panel.update()
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._dropped_files(event):
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drag_over = False
        self.panel.update()

    def dropEvent(self, event):
        paths = self._dropped_files(event)
        self.drag_over = False
        self.panel.update()
        added = 0
        for p in paths:
            if self.cfg.add_item(p):
                added += 1
        if added:
            self.cfg.save()
            self.rebuild()
            self.expand()
            self.toast.show_name("已加入抽屉：%d 个" % added,
                                 self.geo.panel_screen_rect(len(self.buttons), 1.0),
                                 self.geo.edge)
            QTimer.singleShot(1600, self.toast.hide_name)
        self.dropped.emit(added, len(paths) - added)
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        """不画投影（面板直接贴边，视觉上更干净）。"""
        return


# ==========================================================================
#  面板绘制
# ==========================================================================
class _Panel(QWidget):
    def __init__(self, owner: "DrawerWindow"):
        super().__init__(owner)
        self.owner = owner
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        ow = self.owner
        t = ow.t
        geo = ow.geo
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # 贴着屏幕边的那条边不画圆角，免得看起来像悬空的胶囊
        half = min(r.width(), r.height()) / 2.0
        rad = min(18.0 if t["name"] == "dark" and geo.horizontal else 16.0, half)

        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)

        grad = QLinearGradient(r.topLeft(), r.bottomLeft() if geo.horizontal
                               else r.topRight())
        hi, lo = QColor(t["panel_hi"]), QColor(t["panel_lo"])
        op = max(0.35, min(1.0, ow.cfg["panel_opacity"] / 100.0))
        hi.setAlpha(int(hi.alpha() * op))
        lo.setAlpha(int(lo.alpha() * op))
        grad.setColorAt(0.0, hi)
        grad.setColorAt(1.0, lo)
        p.fillPath(path, grad)

        # 内侧高光
        hl = QPainterPath()
        hl.addRoundedRect(r.adjusted(1, 1, -1, -1), max(0, rad - 1), max(0, rad - 1))
        p.setPen(QPen(t["edge_light"], 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(hl)
        p.setPen(QPen(t["border"], 1.0))
        p.drawPath(path)

        # 抽屉内拖动排序：空出来的槽位画一个虚线凹槽
        if ow.drag_index is not None and ow.drop_index is not None:
            sr = QRectF(ow.slot_rect(ow.drop_index)).adjusted(0.5, 0.5, -0.5, -0.5)
            hole = QPainterPath()
            hole.addRoundedRect(sr, 11, 11)
            tint = QColor(t["hover"])
            tint.setAlpha(min(255, tint.alpha() + 30))
            p.fillPath(hole, tint)
            pen = QPen(t["accent"], 1.4, Qt.DashLine)
            pen.setDashPattern([3, 3])
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(hole)

        # 拖拽悬停：琥珀橙描边 + 淡橙底色
        if ow.drag_over:
            tint = QColor(t["accent"])
            tint.setAlpha(38)
            p.fillPath(path, tint)
            p.setPen(QPen(t["accent"], 2.0))
            p.setBrush(Qt.NoBrush)
            inner = QPainterPath()
            inner.addRoundedRect(r.adjusted(1, 1, -1, -1), max(0, rad - 1),
                                 max(0, rad - 1))
            p.drawPath(inner)

        # 收起时露出的「触手条」高光：中间亮、两头淡出
        if ow.reveal < 0.75:
            grip = QColor(t["grip"])
            grip.setAlpha(int(210 * (1.0 - ow.reveal / 0.75)))
            fade = QColor(grip)
            fade.setAlpha(0)
            if geo.horizontal:
                y = int(r.bottom() - 3.0 if geo.edge == "top" else r.top() + 2.0)
                x1, y1, x2, y2 = int(r.left() + 4), y, int(r.right() - 4), y
                gg = QLinearGradient(r.left(), 0, r.right(), 0)
            else:
                x = int(r.right() - 3.0 if geo.edge == "left" else r.left() + 2.0)
                x1, y1, x2, y2 = x, int(r.top() + 4), x, int(r.bottom() - 4)
                gg = QLinearGradient(0, r.top(), 0, r.bottom())
            gg.setColorAt(0.0, fade)
            gg.setColorAt(0.5, grip)
            gg.setColorAt(1.0, fade)
            p.setPen(QPen(gg, 2.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(x1, y1, x2, y2)

        if not ow.buttons and ow.reveal > 0.4:
            p.setPen(QColor(t["accent"] if ow.drag_over else t["subtext"]))
            p.setFont(QFont("Microsoft YaHei UI", 9))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "松开即可加入抽屉" if ow.drag_over
                       else "抽屉还是空的 · 从桌面拖个快捷方式进来")
        p.end()

    def wheelEvent(self, event):
        self.owner.wheelEvent(event)


# ==========================================================================
#  工具函数
# ==========================================================================
def _existing_path(it: dict) -> str:
    """条目里第一个真实存在的路径（快捷方式优先，其次记下的目标）。"""
    for key in ("path", "target"):
        p = it.get(key) or ""
        if p and os.path.exists(p):
            return p
    return ""


def reveal_in_explorer(path: str) -> None:
    if not path:
        return
    try:
        if os.path.isdir(path):
            os.startfile(path)  # noqa: S606
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except Exception:
        pass
