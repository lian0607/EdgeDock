# -*- coding: utf-8 -*-
"""设置面板。"""
from __future__ import annotations

import os
import sys
import webbrowser

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup,
                               QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from . import apps as apps_mod
from . import config as cfg_mod
from . import theme as theme_mod
from . import winapi

EDGES = [("top", "顶部"), ("bottom", "底部"), ("left", "左侧"), ("right", "右侧")]
SLOTS = [("center", "居中"), ("start", "起始端"), ("end", "末端")]
THEME_OPTIONS = [("system", "跟随系统"), ("dark", "深色"), ("light", "浅色")]
HOTKEYS = ["Ctrl+Alt+D", "Ctrl+Shift+D", "Alt+`", "Ctrl+Alt+Space", "禁用"]

LABEL_W = 84        # 设置项名称列宽
SLIDER_W = 170      # 滑杆最大宽度：拉太长的话数值读数会飘到很远，眼睛要来回跑
VALUE_W = 48        # 数值读数列宽
COL_GAP = 16        # 左右两列之间的间距
CARD_GAP = 16       # 卡片之间的间距


def apply_immersive(dlg: QDialog, t: dict) -> None:
    """让标题栏跟着主题走（深色主题下不至于顶一条白条）。"""
    try:
        import ctypes
        val = ctypes.c_int(t["immersive_dark"])
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(int(dlg.winId())), ctypes.c_int(20),
            ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


class SettingsDialog(QDialog):
    changed = Signal()
    minimizedChanged = Signal(bool)      # 窗口最小化 / 还原

    def __init__(self, cfg, store, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self.t = theme_mod.get(cfg["theme"])
        self.minimized = False
        self.setWindowTitle("EdgeDock 设置")
        try:
            avail = QApplication.primaryScreen().availableGeometry()
            # 稍微加宽一点，两列才有地方站；高度按可用高度收
            w = min(720, avail.width() - 80)
            h = min(780, avail.height() - 96)
        except Exception:
            w, h = 720, 780
        self.setFixedSize(w, h)
        # 加最小化按钮：一边改参数一边看效果时，腾开地方比关掉再开方便。
        # 必须在 _build() 之前设好 —— 里面会取 winId() 建出原生窗口，
        # 之后再改窗口标志就得整个重建。
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.setStyleSheet(theme_mod.settings_qss(self.t))
        self._deb = QTimer(self)
        self._deb.setSingleShot(True)
        self._deb.setInterval(70)
        self._deb.timeout.connect(self.changed.emit)
        self._build()
        self._refresh_list()
        self.store.ready.connect(lambda *_: self._refresh_list())

    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        # 打开时回到顶部（子控件获得焦点时滚动区会自动滚走）
        for area in self.findChildren(QScrollArea):
            area.verticalScrollBar().setValue(0)

    def changeEvent(self, event):
        # 最小化 / 还原时通知外面，好让抽屉跟着松开或按住
        if event.type() == QEvent.WindowStateChange:
            now = bool(self.windowState() & Qt.WindowMinimized)
            if now != self.minimized:
                self.minimized = now
                self.minimizedChanged.emit(now)
        super().changeEvent(event)

    def _notify(self) -> None:
        self._deb.start()

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("EdgeDock")
        title.setObjectName("Title")
        brand = QLabel("设置")
        brand.setObjectName("Brand")
        ver = QLabel("吸附在屏幕边缘的应用启动器")
        ver.setObjectName("Hint")
        head.addWidget(title)
        head.addWidget(brand)
        head.addStretch(1)
        head.addWidget(ver)
        root.addLayout(head)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 注意：不要在这里 setStyleSheet("background:transparent")，
        # 局部样式表会向下继承并覆盖掉卡片 / 按钮的背景规则。
        area.setAutoFillBackground(False)
        area.viewport().setAutoFillBackground(False)
        body = QWidget()
        body.setAutoFillBackground(False)
        area.setWidget(body)
        root.addWidget(area, 1)

        # 两列排布：左列是「参数」，右列是「内容」。
        # 单列码下来总高 1100px 往上，780px 的窗口得滚好几屏才摸得到最下面那张卡。
        cols = QHBoxLayout(body)
        cols.setContentsMargins(0, 0, 6, 0)
        cols.setSpacing(COL_GAP)
        col_l = QWidget()
        col_r = QWidget()
        for w in (col_l, col_r):
            w.setAutoFillBackground(False)
            # Ignored：让两列严格按 1:1 分宽度。
            # 否则布局会照着各自的 sizeHint 来分，左列内容宽、右列窄，
            # 结果左边卡片比右边宽十来个像素，对齐关系就散了。
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        lay_l = QVBoxLayout(col_l)
        lay_r = QVBoxLayout(col_r)
        for lay in (lay_l, lay_r):
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(CARD_GAP)
        cols.addWidget(col_l, 1)
        cols.addWidget(col_r, 1)

        # ---- 左列 · 吸附位置 ----
        cv = self._card(lay_l, "吸附位置")
        cv.addLayout(self._seg_row("吸附到", EDGES, "edge"))
        cv.addLayout(self._seg_row("沿边位置", SLOTS, "slot"))
        cv.addLayout(self._slider_row("沿边偏移", "offset", -420, 420, 4, "px"))

        # ---- 左列 · 外观 ----
        cv = self._card(lay_l, "外观")
        cv.addLayout(self._slider_row("图标大小", "icon_size", 28, 62, 1, "px"))
        cv.addLayout(self._slider_row("面板不透明度", "panel_opacity", 55, 100, 1, "%"))
        cv.addLayout(self._seg_row("主题", THEME_OPTIONS, "theme"))

        # ---- 左列 · 交互 ----
        cv = self._card(lay_l, "交互")
        cv.addLayout(self._slider_row("触手条厚度", "peek", 0, 14, 1, "px"))
        cv.addLayout(self._slider_row("触发区厚度", "trigger_px", 1, 10, 1, "px"))
        cv.addLayout(self._slider_row("停留判定", "dwell", 0, 500, 10, "ms"))
        cv.addLayout(self._slider_row("自动收起延时", "hide_delay", 120, 2500, 20, "ms"))
        cv.addWidget(self._check("鼠标悬停时浮出名称", "show_labels"))
        cv.addWidget(self._check("启动应用后自动收起", "hide_after_launch"))
        cv.addWidget(self._check("全屏游戏时隐藏边栏", "hide_in_game"))
        cv.addLayout(self._hotkey_row())

        # ---- 左列 · 关于 ----
        # 左列比右列短一大截，空着难看；顺手把「这是本地程序、不联网」说清楚
        cv = self._card(lay_l, "关于")
        cv.addWidget(self._hint("本地运行 · 不联网 · 配置即改即生效"))
        self._btn_row(cv, (("项目主页", self._open_home),))
        lay_l.addStretch(1)

        # ---- 右列 · 抽屉里的应用 ----
        cv = self._card(lay_r, "抽屉里的应用")
        self.list = QListWidget()
        self.list.setFixedHeight(330)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setIconSize(QSize(22, 22))
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        cv.addWidget(self.list)

        # 六个按钮挤一行在这个列宽下放不下，拆成「增删 / 排序」两行
        self._btn_row(cv, (("控制面板…", self._pick_apps),
                           ("添加文件…", self.add_files)))
        self._btn_row(cv, (("上移", lambda: self._move(-1)),
                           ("下移", lambda: self._move(1)),
                           ("移除", self._remove_selected),
                           ("清空", self._clear)))

        hint = QLabel("提示：.lnk / .exe 可直接拖进列表添加。\n"
                      "列表项可拖动排序，抽屉里也能按住图标拖。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        cv.addWidget(hint)
        self.setAcceptDrops(True)

        # ---- 右列 · 启动 ----
        cv = self._card(lay_r, "启动")
        cv.addWidget(self._check("开机自动启动", "autostart"))
        self._btn_row(cv, (("打开程序目录", self._open_root),
                           ("编辑配置文件", self._open_config)))
        self.btn_shortcut = self._btn_row(
            cv, (("添加桌面图标", self._add_desktop_icon),))[0]
        lay_r.addStretch(1)

        # 页脚：一条极淡的分隔线，让「完成」不至于孤零零地飘在滚动区下面
        line = QFrame()
        line.setObjectName("FootLine")
        line.setFixedHeight(1)
        root.addWidget(line)

        foot = QHBoxLayout()
        note = QLabel("改动即时生效 · 快捷键 %s" % self.cfg["hotkey"])
        note.setObjectName("Hint")
        foot.addWidget(note)
        foot.addStretch(1)
        close = QPushButton("完成")
        close.setObjectName("Primary")
        close.setMinimumWidth(96)
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        root.addLayout(foot)

        apply_immersive(self, self.t)

    # ------------------------------------------------------------------
    def _card(self, parent_layout, title: str):
        """往父布局里加「小标题 + 卡片」，返回卡片内部的竖直布局。

        标题是浅灰色的小字，压在卡片左上角：让五张卡片读起来像同一页上
        排好的五段，而不是五个各说各话的盒子。
        """
        head = QHBoxLayout()
        head.setContentsMargins(2, 0, 0, 0)
        head.setSpacing(7)
        lab = QLabel(title)
        lab.setObjectName("Section")
        head.addWidget(lab)
        head.addStretch(1)

        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(13, 12, 13, 12)
        lay.setSpacing(8)
        # 标题跟自己的卡片贴紧一点，跟上一张卡片分开一点，层级才看得清
        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(5)
        wrap.addLayout(head)
        wrap.addWidget(card)
        parent_layout.addLayout(wrap)
        return lay

    @staticmethod
    def _hint(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("Hint")
        lab.setWordWrap(True)
        return lab

    @staticmethod
    def _btn_row(parent, pairs) -> list:
        """往卡片里加一行按钮：``((文字, 回调), …)``，返回加好的按钮。

        增删、排序、启动、关于四处都是这个形状，抽出来免得写四份。
        """
        row = QHBoxLayout()
        row.setSpacing(8)
        out = []
        for text, fn in pairs:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
            out.append(b)
        row.addStretch(1)
        parent.addLayout(row)
        return out

    def _label(self, text: str, width: int = LABEL_W) -> QLabel:
        lab = QLabel(text)
        lab.setFixedWidth(width)
        return lab

    def _set(self, key: str, value) -> None:
        """写进配置、落盘、通知抽屉刷新 —— 所有控件回调都走这里。"""
        self.cfg[key] = value
        self.cfg.save()
        self._notify()

    def _slider_row(self, text, key, lo, hi, step, unit):
        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(self._label(text))
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setPageStep(max(step, (hi - lo) // 10))
        s.setValue(int(self.cfg[key]))
        # 关键：限宽 + 单靠自己吃富余宽度。
        # 滑杆拉满整行的话读数会被甩到几百像素以外，拖一下得两头看；
        # 而在行尾挂 spacer 的话富余宽度又会被 spacer 全吞掉，滑杆只剩
        # 最小宽度（之前量出来只有 96px，短得像根装饰线）。
        s.setMaximumWidth(SLIDER_W)
        s.setMinimumWidth(96)
        val = QLabel()
        val.setFixedWidth(VALUE_W)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        val.setObjectName("Hint")
        val.setText("%d%s" % (s.value(), unit))
        s.valueChanged.connect(lambda x, k=key, u=unit, l=val:
                               (l.setText("%d%s" % (x, u)), self._set(k, x)))
        row.addWidget(s, 1)
        row.addWidget(val)
        return row

    def _seg_row(self, text, options, key):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._label(text))
        group = QButtonGroup(self)
        group.setExclusive(True)
        cur = self.cfg[key]
        for value, label in options:
            b = QPushButton(label)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setChecked(cur == value)
            b.clicked.connect(lambda _=False, k=key, v=value: self._set(k, v))
            group.addButton(b)
            row.addWidget(b)
        row.addStretch(1)
        return row

    def _check(self, text, key):
        cb = QCheckBox(text)
        cb.setChecked(bool(self.cfg[key]))
        cb.toggled.connect(lambda v, k=key: self._set(k, v))
        return cb

    def _hotkey_row(self):
        row = QHBoxLayout()
        row.setSpacing(9)
        row.addWidget(self._label("全局快捷键"))
        combo = QComboBox()
        combo.addItems(HOTKEYS)
        cur = self.cfg["hotkey"]
        if cur not in HOTKEYS:
            combo.addItem(cur)
        combo.setCurrentText(cur)
        # 右边那条解释文字去掉 —— 选项本身（Ctrl+Alt+D / 禁用）已经说清楚了
        combo.setFixedWidth(190)
        combo.currentTextChanged.connect(lambda txt: self._set("hotkey", txt))
        row.addWidget(combo)
        row.addStretch(1)
        return row

    # ------------------------------------------------------------------
    #  应用列表
    # ------------------------------------------------------------------
    def _after_list_change(self) -> None:
        """列表被增删改过之后：落盘 + 重画列表 + 通知抽屉。"""
        self.cfg.save()
        self._refresh_list()
        self._notify()

    def _refresh_list(self) -> None:
        selected = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        dpr = self.devicePixelRatioF() or 1.0
        for it in self.cfg.items:
            name = it.get("name") or os.path.splitext(
                os.path.basename(it.get("path", "")))[0] or "（未命名）"
            # 图标按「应用标识优先、其次文件路径」取，和抽屉里保持一致
            icon_src = apps_mod.spec_of(it)
            if not it.get("appid"):
                path = it.get("path") or ""
                if not os.path.exists(path):
                    # 快捷方式没了不等于打不开：记住了目标就还能把程序拉起来
                    name += ("   （快捷方式已删除，按目标启动）"
                             if self.cfg.launchable(it) else "   （找不到，请重新添加）")
                    # 图标也跟着换到还在的那个路径上，不然只剩一个字母占位
                    icon_src = it.get("target") or icon_src
            item = QListWidgetItem(QIcon(self.store.pixmap(icon_src, 22, dpr)), name)
            item.setData(Qt.UserRole, self.cfg.key(it))
            # 列窄，名字会被省略，用悬停补全来源
            item.setToolTip(self._describe(it))
            self.list.addItem(item)
        self.list.blockSignals(False)
        if 0 <= selected < self.list.count():
            self.list.setCurrentRow(selected)

    @staticmethod
    def _describe(it: dict) -> str:
        """列表项的完整说明：名字 + 从哪儿来的 + 底下是什么。"""
        where = apps_mod.SOURCE_LABEL.get(it.get("source", ""), "")
        if it.get("appid"):
            detail = winapi.app_spec(it["appid"])
        elif it.get("target"):
            detail = it["target"]
        else:
            detail = it.get("path", "")
        return "\n".join(x for x in (it.get("name"), where, detail) if x)

    def _current_path(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _move(self, delta: int) -> None:
        path = self._current_path()
        if not path:
            return
        row = self.list.currentRow()
        self.cfg.move_item(path, delta)
        self._after_list_change()
        self.list.setCurrentRow(max(0, min(self.list.count() - 1, row + delta)))

    def _remove_selected(self) -> None:
        path = self._current_path()
        if not path:
            return
        self.cfg.remove_item(path)
        self._after_list_change()

    def _clear(self) -> None:
        # 清空没有撤销，条目多的时候误一下就全没了 —— 问一句
        if self.cfg.items:
            ret = QMessageBox.question(
                self, "清空抽屉", "确定要移除抽屉里的全部 %d 个应用吗？"
                % len(self.cfg.items),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.cfg.set_items([])
        self._after_list_change()

    def _on_rows_moved(self, *_args) -> None:
        # 这里故意不刷新列表 —— 排序刚落地，重画会把拖好的视觉状态打乱
        order = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        by_key = {self.cfg.key(i): i for i in self.cfg.items}
        self.cfg.set_items([by_key[k] for k in order if k in by_key])
        self.cfg.save()
        self._notify()

    def add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "添加应用到抽屉", os.path.expanduser("~"),
            "快捷方式与程序 (*.lnk *.exe *.url *.bat *.cmd);;所有文件 (*.*)")
        if not files:
            return
        for f in files:
            self.cfg.add_item(f)
        self._after_list_change()

    def _pick_apps(self) -> None:
        # 勾选窗口自己会把配置存好，这里只需要刷新显示
        if AppPicker(self.cfg, self.store, self).exec() == QDialog.Accepted:
            self._refresh_list()
            self._notify()

    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        added = False
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isfile(p):
                added |= self.cfg.add_item(p)
        if added:
            self._after_list_change()
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    @staticmethod
    def _open_home() -> None:
        webbrowser.open("https://github.com/lian0607/EdgeDock")

    def _open_root(self) -> None:
        try:
            os.startfile(cfg_mod.ROOT)
        except Exception:
            pass

    def _open_config(self) -> None:
        try:
            os.startfile(self.cfg.path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    LNK_NAME = "EdgeDock 边缘抽屉.lnk"

    def _add_desktop_icon(self) -> None:
        """在桌面放一个 EdgeDock 的快捷方式，丢了 / 挪走了就一键找回。

        已存在的话直接覆盖 —— create_lnk 每次都重写，顺带把图标和描述刷新。
        成功与否都把按钮文字临时换掉，比弹个对话框轻。
        """
        btn = self.btn_shortcut
        lnk = os.path.join(winapi.desktop_dirs()[0], self.LNK_NAME)
        if cfg_mod.FROZEN:
            # 打包版：快捷方式直接指 exe，图标已经嵌在 exe 里
            target = icon = sys.executable
        else:
            target = os.path.join(cfg_mod.ROOT, "启动 EdgeDock.vbs")
            icon = os.path.join(cfg_mod.ROOT, "assets", "edgedock.ico")
        ok = winapi.create_lnk(
            lnk, target,
            workdir=cfg_mod.ROOT,
            icon=icon,
            desc="EdgeDock · 吸附在屏幕边缘的应用启动器")
        btn.setText("已放到桌面 ✓" if ok else "创建失败 ✗")
        QTimer.singleShot(2200, lambda: btn.setText("添加桌面图标"))


# ==========================================================================
class CheckList(QListWidget):
    """整行可点的应用列表 —— 左键落在哪一行，哪一行就翻勾选。

    QSS 美化过的列表里，指示器的原生命中判定在**行未选中时**会失灵：
    第一脚只选中、第二脚才切换，用户看到的就是「点了没反应」。而且
    复选框只有小小一格，用户更习惯点图标或名字 —— 干脆整行接管，
    不再依赖官方判定。这个列表只靠勾选表达意图，选中态没有用途。
    """

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.position().toPoint())
        if (item is not None and event.button() == Qt.LeftButton
                and (item.flags() & Qt.ItemIsUserCheckable)):
            item.setCheckState(
                Qt.Unchecked if item.checkState() == Qt.Checked
                else Qt.Checked)
            event.accept()
            return
        super().mousePressEvent(event)


# ==========================================================================
class AppPicker(QDialog):
    """从系统里挑应用：搜名字、勾选、确定。

    候选来自 ``apps.scan_apps()`` —— 「所有应用」+ 开始菜单 + 桌面，同名的只留
    优先级最高的那个。所以桌面干不干净、快捷方式有没有被挪走，都不影响这里；
    商店应用也一并列出来。
    """

    def __init__(self, cfg, store, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self.t = theme_mod.get(cfg["theme"])
        self.setWindowTitle("选择程序")
        self.setFixedSize(560, 660)
        self.setStyleSheet(theme_mod.settings_qss(self.t))
        self.pool = apps_mod.scan_apps()
        self._chosen = {os.path.normcase(cfg.key(i)) for i in cfg.items}
        self._chosen_names = {(i.get("name") or "").strip().lower()
                              for i in cfg.items if i.get("name")}
        # 已经躺进抽屉的程序，它的真实目标也是同一个程序 —— 光比 path 不灵：
        # 名单里给的可能是「开始」菜单那个 .lnk，抽屉里存的是 exe 本体
        self._chosen_paths = {os.path.normcase(k)
                              for i in cfg.items
                              for k in (i.get("target"), i.get("path")) if k}

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)

        self.lab = QLabel()
        self.lab.setObjectName("Section")
        v.addWidget(self.lab)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索应用名…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        v.addWidget(self.search)

        # 系统工具（控制面板、管理工具那一类）默认不显示 —— 能打开，但没人
        # 会想把它们放进抽屉。开关状态记进配置，下次打开还保持。
        self.chk_sys = QCheckBox("隐藏系统组件（运行库、驱动、服务）")
        self.chk_sys.setChecked(bool(cfg["hide_sys"]))
        self.chk_sys.toggled.connect(self._on_hide_sys)
        v.addWidget(self.chk_sys)

        self.list = CheckList()
        self.list.setIconSize(QSize(22, 22))
        self.list.setUniformItemSizes(True)
        dpr = self.devicePixelRatioF() or 1.0
        # 同一个图标可能被多个条目共用（比如「所有应用」和开始菜单里的同一程序），
        # 建个索引，后台补图时不用每次把整个列表扫一遍
        self._by_spec: dict[str, list] = {}
        for idx, it in enumerate(self.pool):
            item = QListWidgetItem(self._label_of(it))
            item.setData(Qt.UserRole, idx)          # 下标指回 self.pool
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._is_chosen(it)
                               else Qt.Unchecked)
            item.setToolTip(it.get("appid") or it.get("path") or "")
            spec = apps_mod.spec_of(it)
            item.setIcon(QIcon(store.pixmap(spec, 22, dpr)))
            self._by_spec.setdefault(spec, []).append(item)
            self.list.addItem(item)
        v.addWidget(self.list, 1)

        row = QHBoxLayout()
        b_all = QPushButton("全选")
        b_all.clicked.connect(lambda: self._set_all(Qt.Checked))
        b_none = QPushButton("全不选")
        b_none.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        row.addWidget(b_all)
        row.addWidget(b_none)
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("确定")
        ok.setObjectName("Primary")
        ok.clicked.connect(self._accept)
        row.addWidget(ok)
        v.addLayout(row)

        # 图标是后台分批提取的，好了就把对应那行刷新一下
        store.ready.connect(self._on_icon_ready)
        # 开场先过一遍过滤：系统工具默认要藏起来，标题里的计数也靠它写
        self._apply_filter()
        # 先补首屏看得见的那些，剩下的等窗口出来了再补 —— 一百多个一起提
        # 会让第一次打开明显发木。_by_spec 的键就是去重后的寻址串，直接拿来用
        specs = list(self._by_spec)
        store.warm(specs[:48])
        later = QTimer(self)
        later.setSingleShot(True)
        later.timeout.connect(lambda: store.warm(specs))
        later.start(900)

        apply_immersive(self, self.t)

    # ------------------------------------------------------------------
    @staticmethod
    def _key_of(app: dict) -> str:
        return os.path.normcase((app.get("appid") or app.get("path") or "").strip())

    def _is_chosen(self, app: dict) -> bool:
        """这个候选应用在不在抽屉里。

        三重比对，从硬到软：应用标识 / 路径 → 真实目标 → 名字。
        只比第一层是不够的 —— 名单里给的是「开始」菜单的 .lnk，抽屉里存的
        往往是 exe 本体，键永远对不上，于是已经加过的程序显示成「没加」，
        再勾一次就多出一条重复项（名字还略有出入）。
        """
        if self._key_of(app) in self._chosen:
            return True
        for k in (app.get("target"), app.get("path")):
            if k and os.path.normcase(k) in self._chosen_paths:
                return True
        name = (app.get("name") or "").strip().lower()
        return any(apps_mod.same_name(name, n) for n in self._chosen_names)

    @staticmethod
    def _label_of(app: dict) -> str:
        label = app["name"]
        src = apps_mod.SOURCE_LABEL.get(app.get("source", ""), "")
        # 只有兜底来源才标，否则满屏都是同一个标签
        if src and app.get("source") not in ("apps", "installed"):
            label += "    · %s" % src
        return label

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().lower()
        hide_sys = self.chk_sys.isChecked()
        visible = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            it = self.pool[item.data(Qt.UserRole)]
            hide = ((bool(needle) and needle not in item.text().lower())
                    or (hide_sys and apps_mod.is_system_tool(it)))
            item.setHidden(hide)
            if not hide:
                visible += 1
        total = len(self.pool)
        self.lab.setText("控制面板里的程序 · %d 个%s"
                         % (total, "（显示 %d）" % visible if visible < total else ""))

    def _on_hide_sys(self, on: bool) -> None:
        self.cfg["hide_sys"] = bool(on)
        self.cfg.save()
        self._apply_filter()

    def _on_icon_ready(self, spec: str) -> None:
        dpr = self.devicePixelRatioF() or 1.0
        for item in self._by_spec.get(spec, ()):
            item.setIcon(QIcon(self.store.pixmap(spec, 22, dpr)))

    def _set_all(self, state) -> None:
        # 只作用于当前可见的（搜索过滤之后「全选」按用户看到的那批算）
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def _twin(self, it: dict, by_key: dict, by_path: dict) -> dict | None:
        """这个抽屉条目在候选名单里对应哪一条；认不出（池外条目）返回 None。

        三层比对，从硬到软：标识 → 真实目标 / 路径 → 名字。最后一层是给老配
        置留的：那时存的是应用标识、根本不是文件路径，前两层永远对不上，于是
        取消勾选看起来毫无作用。名字要求**唯一命中**，有歧义宁可不动。
        """
        twin = by_key.get(os.path.normcase(self.cfg.key(it)))
        if twin is not None:
            return twin
        for k in (it.get("target"), it.get("path")):
            if k and os.path.normcase(k) in by_path:
                return by_path[os.path.normcase(k)]
        name = (it.get("name") or "").strip()
        hits = [a for a in self.pool if name and apps_mod.same_name(name, a["name"])]
        return hits[0] if len(hits) == 1 else None

    def _accept(self) -> None:
        picked = [self.pool[self.list.item(i).data(Qt.UserRole)]
                  for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.Checked]
        keys = {self._key_of(a) for a in picked}

        # 候选名单按「标识」「路径 / 真实目标」建两张索引，好把抽屉里的老条目
        # 认出来。认不出对应候选的（手动拖进来的 .exe、绿色软件）属于池外，
        # 不在候选列表里不等于用户不要了，原样保留 —— 之前这里会静默删掉。
        by_key: dict[str, dict] = {}
        by_path: dict[str, dict] = {}
        for app in self.pool:
            by_key.setdefault(self._key_of(app), app)
            for k in (app.get("target"), app.get("path")):
                if k:
                    by_path.setdefault(os.path.normcase(k), app)

        out: list[dict] = []
        have: set[str] = set()
        for it in self.cfg.items:
            twin = self._twin(it, by_key, by_path)
            if twin is not None and self._key_of(twin) not in keys:
                continue                       # 在候选里、被取消了勾选 → 移出抽屉
            # **位置一寸不让**：老条目保持原来的先后，只有名字跟控制面板对齐。
            # 之前把池外条目整体提到最前，用户调好的顺序每次确定都被打乱。
            if twin is not None and twin["name"] != it.get("name"):
                it["name"] = twin["name"]
            key = os.path.normcase(self.cfg.key(it))
            if key not in have:
                out.append(it)
                have.add(key)
        # 新勾上的按列表（也就是控制面板）的顺序接在后面
        for app in picked:
            k = self._key_of(app)
            if k not in have:
                out.append(dict(app))
                have.add(k)
        # 同名只留先来的 —— 名字兜底匹配可能让新旧两条重复入列
        seen: set[str] = set()
        uniq: list[dict] = []
        for it in out:
            low = (it.get("name") or "").strip().lower()
            if low and low in seen:
                continue
            seen.add(low)
            uniq.append(it)
        out = uniq
        # 从「非空」清成「空」多半是误触（比如全不选之后顺手点了确定），拦一下
        if self.cfg.items and not out:
            ret = QMessageBox.question(
                self, "清空抽屉", "一个应用都没勾 —— 确定要清空抽屉吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.cfg.set_items(out)
        self.cfg.save()
        self.accept()
