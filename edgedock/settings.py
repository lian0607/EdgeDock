# -*- coding: utf-8 -*-
"""设置面板。"""
from __future__ import annotations

import os

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
COL_GAP = 14        # 左右两列之间的间距
CARD_GAP = 14       # 卡片之间的间距


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
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("边缘抽屉")
        title.setObjectName("Title")
        ver = QLabel("EdgeDock · 吸附在屏幕边缘的应用启动器")
        ver.setObjectName("Hint")
        head.addWidget(title)
        head.addSpacing(10)
        head.addWidget(ver)
        head.addStretch(1)
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
        cv = self._card(lay_l, "吸 附 位 置")
        cv.addLayout(self._seg_row("吸附到", EDGES, "edge"))
        cv.addLayout(self._seg_row("沿边位置", SLOTS, "slot"))
        cv.addLayout(self._slider_row("沿边偏移", "offset", -420, 420, 4, "px"))

        # ---- 左列 · 外观 ----
        cv = self._card(lay_l, "外 观")
        cv.addLayout(self._slider_row("图标大小", "icon_size", 28, 62, 1, "px"))
        cv.addLayout(self._slider_row("面板不透明度", "panel_opacity", 55, 100, 1, "%"))
        cv.addLayout(self._seg_row("主题", THEME_OPTIONS, "theme"))

        # ---- 左列 · 交互 ----
        cv = self._card(lay_l, "交 互")
        cv.addLayout(self._slider_row("触手条厚度", "peek", 0, 14, 1, "px"))
        cv.addLayout(self._slider_row("触发区厚度", "trigger_px", 1, 10, 1, "px"))
        cv.addLayout(self._slider_row("停留判定", "dwell", 0, 500, 10, "ms"))
        cv.addLayout(self._slider_row("自动收起延时", "hide_delay", 120, 2500, 20, "ms"))
        cv.addWidget(self._check("鼠标悬停时浮出名称", "show_labels"))
        cv.addWidget(self._check("启动应用后自动收起", "hide_after_launch"))
        cv.addWidget(self._check("全屏游戏时隐藏边栏", "hide_in_game"))
        cv.addLayout(self._hotkey_row())
        lay_l.addStretch(1)

        # ---- 右列 · 抽屉里的应用 ----
        cv = self._card(lay_r, "抽 屉 里 的 应 用")
        self.list = QListWidget()
        self.list.setFixedHeight(330)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setIconSize(QSize(22, 22))
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.model().rowsMoved.connect(self._on_rows_moved)
        cv.addWidget(self.list)

        # 六个按钮挤一行在这个列宽下放不下，拆成「增删 / 排序」两行
        bar1 = QHBoxLayout()
        bar1.setSpacing(8)
        for text, fn in (("从系统选择…", self._pick_apps),
                         ("添加文件…", self.add_files)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar1.addWidget(b)
        bar1.addStretch(1)
        cv.addLayout(bar1)

        bar2 = QHBoxLayout()
        bar2.setSpacing(8)
        for text, fn in (("上移", lambda: self._move(-1)),
                         ("下移", lambda: self._move(1)),
                         ("移除", self._remove_selected),
                         ("清空", self._clear)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar2.addWidget(b)
        bar2.addStretch(1)
        cv.addLayout(bar2)

        hint = QLabel("提示：.lnk / .exe 可直接拖进列表添加。\n"
                      "列表项可拖动排序，抽屉里也能按住图标拖。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        cv.addWidget(hint)
        self.setAcceptDrops(True)

        # ---- 右列 · 启动 ----
        cv = self._card(lay_r, "启 动")
        cv.addWidget(self._check("开机自动启动", "autostart"))
        row = QHBoxLayout()
        row.setSpacing(8)
        btn_dir = QPushButton("打开程序目录")
        btn_dir.clicked.connect(self._open_root)
        btn_cfg = QPushButton("编辑配置文件")
        btn_cfg.clicked.connect(self._open_config)
        row.addWidget(btn_dir)
        row.addWidget(btn_cfg)
        row.addStretch(1)
        cv.addLayout(row)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.btn_shortcut = QPushButton("添加桌面图标")
        self.btn_shortcut.clicked.connect(self._add_desktop_icon)
        row2.addWidget(self.btn_shortcut)
        row2.addStretch(1)
        cv.addLayout(row2)
        lay_r.addStretch(1)

        # 页脚：一条极淡的分隔线，让「完成」不至于孤零零地飘在滚动区下面
        line = QFrame()
        line.setObjectName("FootLine")
        line.setFixedHeight(1)
        root.addWidget(line)

        foot = QHBoxLayout()
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
        """往父布局里加「小标题 + 卡片」，返回卡片内部的竖直布局。"""
        lab = QLabel(title)
        lab.setObjectName("Section")
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        # 标题跟自己的卡片贴紧一点，跟上一张卡片分开一点，层级才看得清
        wrap = QVBoxLayout()
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.setSpacing(6)
        wrap.addWidget(lab)
        wrap.addWidget(card)
        parent_layout.addLayout(wrap)
        return lay

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
        ok = winapi.create_lnk(
            lnk,
            os.path.join(cfg_mod.ROOT, "启动 EdgeDock.vbs"),
            workdir=cfg_mod.ROOT,
            icon=os.path.join(cfg_mod.ROOT, "assets", "edgedock.ico"),
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
        self.setWindowTitle("选择应用")
        self.setFixedSize(560, 660)
        self.setStyleSheet(theme_mod.settings_qss(self.t))
        self.pool = apps_mod.scan_apps()
        self._chosen = {os.path.normcase(cfg.key(i)) for i in cfg.items}
        self._chosen_names = {(i.get("name") or "").strip().lower()
                              for i in cfg.items if i.get("name")}

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
        self.chk_sys = QCheckBox("隐藏系统工具（控制面板、管理工具之类）")
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
        self._specs = [apps_mod.spec_of(it) for it in self.pool]
        # 先补首屏看得见的那些，剩下的等窗口出来了再补 —— 一百多个一起提
        # 会让第一次打开明显发木
        store.warm(self._specs[:48])
        later = QTimer(self)
        later.setSingleShot(True)
        later.timeout.connect(lambda: store.warm(self._specs))
        later.start(900)

        apply_immersive(self, self.t)

    # ------------------------------------------------------------------
    @staticmethod
    def _key_of(app: dict) -> str:
        return os.path.normcase((app.get("appid") or app.get("path") or "").strip())

    def _is_chosen(self, app: dict) -> bool:
        """这个候选应用在不在抽屉里。键对不上时按名字兜底 —— 应用标识是会
        随进程注册/注销的（比如 DeepSeek Harness），抽屉里存的可能还是旧键。"""
        if self._key_of(app) in self._chosen:
            return True
        return app["name"].strip().lower() in self._chosen_names

    @staticmethod
    def _label_of(app: dict) -> str:
        label = app["name"]
        src = apps_mod.SOURCE_LABEL.get(app.get("source", ""), "")
        # 只有不是「应用列表」的才标来源，否则满屏都是同一个标签
        if src and app.get("source") != "apps":
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
        self.lab.setText("勾选要放进抽屉的应用（共 %d 个%s）"
                         % (total, "，显示 %d" % visible if visible < total else ""))

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

    def _accept(self) -> None:
        picked, keys = [], set()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.Checked:
                app = self.pool[item.data(Qt.UserRole)]
                picked.append(app)
                keys.add(self._key_of(app))
        # 这次的勾选**管不着**池外条目：应用标识随进程注册的应用（进程一退
        # 就从「所有应用」里消失）、用户手动加的绿色软件……它们不在候选列表里，
        # 没被勾上不代表用户不要了，原样保留 —— 之前这里会把它们静默删掉。
        pool_keys = {self._key_of(a) for a in self.pool}
        out = [it for it in self.cfg.items
               if os.path.normcase(self.cfg.key(it)) not in pool_keys]
        have = {os.path.normcase(self.cfg.key(it)) for it in out}
        # 勾上的：老条目按原顺序跟上（用户可能调过序），新条目按列表顺序往后接
        for it in self.cfg.items:
            k = os.path.normcase(self.cfg.key(it))
            if k in keys and k not in have:
                out.append(it)
                have.add(k)
        for app in picked:
            if self._key_of(app) not in have:
                out.append(app)
                have.add(self._key_of(app))
        # 同名只留先来的 —— 名字兜底匹配可能让新旧两条重复入列
        seen_names = set()
        deduped = []
        for it in out:
            low = (it.get("name") or "").strip().lower()
            if low and low in seen_names:
                continue
            if low:
                seen_names.add(low)
            deduped.append(it)
        # 从「非空」清成「空」多半是误触（比如全不选之后顺手点了确定），拦一下
        if self.cfg.items and not deduped:
            ret = QMessageBox.question(
                self, "清空抽屉", "一个应用都没勾 —— 确定要清空抽屉吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.cfg.set_items(deduped)
        self.cfg.save()
        self.accept()
