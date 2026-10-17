# -*- coding: utf-8 -*-
"""应用主控：托盘、全局快捷键、开机自启、单实例。"""
from __future__ import annotations

import os
import sys
import winreg

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import config as config_mod
from . import theme as theme_mod
from . import winapi
from .drawer import DrawerWindow
from .icons import IconStore
from .settings import SettingsDialog

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "EdgeDock"


# ----------------------------------------------------------------------
def launch_item(it: dict) -> bool:
    """打开抽屉里的一个条目，成功返回 True。

    启动程序这活儿交给 **explorer**，不用 ShellExecuteW。实测下来
    ShellExecute 对着 .exe 和 .lnk 都返回成功码（>32），进程却一个都不起来 ——
    典型的「谎报成功」，光看返回值根本发现不了，用户看到的就是点了没反应。
    explorer 走的是 shell 自己的激活链路，才真能把程序拉起来。

    优先级：
      1) **有 appid** -> explorer 打开 ``shell:AppsFolder\\<标识>``。
         商店应用只认这条路，桌面上根本没有它的快捷方式。
      2) 快捷方式还在 -> 交给 explorer 打开它。.lnk 上挂着启动参数、工作目录、
         「以管理员身份运行」标记、应用标识，走它最保真；explorer 会照办提权。
      3) 快捷方式没了，但记着真实目标 -> 交给 explorer 打开目标本身。
      4) 条目里额外填了启动参数 -> 只能退回 ShellExecuteW，因为 explorer
         没法把参数转交给目标程序。
    """
    appid = (it.get("appid") or "").strip()
    if appid:
        return winapi.explorer_open(winapi.app_spec(appid))

    link = it.get("path") or ""
    target = it.get("target") or ""
    args = it.get("args") or ""
    has_link = bool(link) and os.path.exists(link)
    has_target = bool(target) and os.path.exists(target)

    if has_link:
        return winapi.explorer_open(link)
    if has_target:
        if args and winapi.shell_execute(target, args, it.get("workdir", "")):
            return True
        return winapi.explorer_open(target)
    return False


def autostart_command() -> str:
    root = config_mod.ROOT
    pw = os.path.join(root, ".venv", "Scripts", "pythonw.exe")
    if not os.path.exists(pw):
        pw = sys.executable
    return '"%s" "%s"' % (pw, os.path.join(root, "main.pyw"))


def run_value() -> str | None:
    """读注册表里登记的开机自启命令；没有这一项返回 None。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return winreg.QueryValueEx(k, RUN_NAME)[0] or ""
    except Exception:
        return None


def is_autostart() -> bool:
    return run_value() is not None


def sync_autostart(enabled: bool) -> bool:
    """开机自启项与当前程序目录对齐（整个文件夹被搬走时自动纠正）。"""
    want = autostart_command() if enabled else None
    if run_value() == want:
        return True                     # 注册表里已经是对的
    return set_autostart(enabled)


def set_autostart(on: bool) -> bool:
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------
def app_icon(t: dict) -> QIcon:
    """用代码画一个托盘图标：抽屉 + 琥珀橙高光。"""
    sizes = (16, 24, 32, 48, 64, 128, 256)
    icon = QIcon()
    accent = QColor("#FF7A2D")
    for s in sizes:
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        u = s / 64.0
        # 抽屉外框
        body = QRectF(6 * u, 16 * u, 52 * u, 34 * u)
        path = QPainterPath()
        path.addRoundedRect(body, 9 * u, 9 * u)
        g = QLinearGradient(body.topLeft(), body.bottomLeft())
        g.setColorAt(0.0, QColor(52, 55, 64))
        g.setColorAt(1.0, QColor(24, 25, 30))
        p.fillPath(path, g)
        p.setPen(QPen(QColor(255, 255, 255, 40), max(1.0, 1.2 * u)))
        p.drawPath(path)
        # 拉开的那一段
        p.setPen(QPen(accent, 3.4 * u, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(14 * u, 33 * u), QPointF(50 * u, 33 * u))
        # 把手
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 205))
        p.drawRoundedRect(QRectF(25 * u, 41 * u, 14 * u, 3.4 * u), 1.7 * u, 1.7 * u)
        p.end()
        icon.addPixmap(pm)
    return icon


# ----------------------------------------------------------------------
class EdgeDock(QObject):
    HOTKEY_POLL = 40

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.cfg = config_mod.Config()
        self._first_run = not self.cfg["seeded"]

        if self._first_run:
            self.cfg.set_items(config_mod.seed_items())
            self.cfg["seeded"] = True
            self.cfg.save()

        self.store = IconStore(config_mod.CACHE_DIR, self)
        self.t = theme_mod.get(self.cfg["theme"])

        # 快捷方式被删、被改名、被挪走都是常事。启动时先过一遍：能就地修好的
        # 就修好，这样点图标一定能打开，而不是静默地什么都不发生。
        if self.cfg.repair():
            self.cfg.save()

        self.drawer = DrawerWindow(self.cfg, self.store)
        self.drawer.launchRequested.connect(self._launch)
        self.drawer.settingsRequested.connect(self.open_settings)
        self.drawer.quitRequested.connect(self.quit)
        self.drawer.dropped.connect(self._on_dropped)

        self.settings_dlg: SettingsDialog | None = None
        self._hot_prev = False
        self._hotkey_timer = QTimer(self)
        self._hotkey_timer.setInterval(self.HOTKEY_POLL)
        self._hotkey_timer.timeout.connect(self._poll_hotkey)
        self._hotkey_timer.start()

        self._build_tray()
        # 主题选了「跟随系统」时，系统一换配色就跟着换
        self.app.styleHints().colorSchemeChanged.connect(self._on_system_theme)
        # 开机自启：以注册表实际状态为准；若路径变了（换过目录）顺手纠正
        self.cfg["autostart"] = is_autostart()
        sync_autostart(bool(self.cfg["autostart"]))
        self.cfg.save()

        if self._first_run:
            QTimer.singleShot(900, self._first_run_hint)

    def _on_system_theme(self, *_args) -> None:
        """系统在深色/浅色之间切换了。只有选了「跟随系统」才需要动。

        还要比对解析出来的实际配色：系统有时只是广播一下、颜色并没有真的换，
        这种情况不值得把抽屉拆了重画一遍。
        """
        if (self.cfg["theme"] == theme_mod.SYSTEM
                and theme_mod.system_theme() != self.t["name"]):
            self.apply_settings()

    # ------------------------------------------------------------------
    def _build_tray(self) -> None:
        t = self.t
        self.tray = QSystemTrayIcon(app_icon(t), self)
        self.tray.setToolTip("EdgeDock · 边缘抽屉")
        menu = QMenu()
        menu.setStyleSheet(theme_mod.menu_qss(t))

        self.act_show = menu.addAction("唤出抽屉")
        self.act_show.triggered.connect(self.drawer.expand)
        self.act_hide = menu.addAction("收起抽屉")
        self.act_hide.triggered.connect(self.drawer.collapse)
        menu.addSeparator()
        self.act_pin = menu.addAction("固定展开（不自动收起）")
        self.act_pin.setCheckable(True)
        self.act_pin.setChecked(self.drawer.pinned)
        self.act_pin.toggled.connect(self.drawer.set_pinned)
        menu.addSeparator()
        menu.addAction("添加应用…", self.add_files)
        menu.addAction("设置…", self.open_settings)
        menu.addSeparator()
        self.act_boot = menu.addAction("开机自动启动")
        self.act_boot.setCheckable(True)
        self.act_boot.setChecked(is_autostart())
        self.act_boot.toggled.connect(self._toggle_autostart)
        menu.addSeparator()
        menu.addAction("退出 EdgeDock", self.quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.drawer.toggle()

    def _toggle_autostart(self, on: bool) -> None:
        ok = set_autostart(on)
        if not ok:
            self.act_boot.setChecked(False)
            self.tray.showMessage("EdgeDock", "写入开机启动项失败，请检查权限。",
                                  QSystemTrayIcon.Warning, 3500)
            return
        self.cfg["autostart"] = on
        self.cfg.save()

    def _on_dropped(self, added: int, dup: int) -> None:
        if added == 0 and dup:
            self.tray.showMessage("EdgeDock", "这些项目已经在抽屉里了。",
                                  QSystemTrayIcon.Information, 2500)

    # ------------------------------------------------------------------
    def _launch(self, key: str) -> None:
        """点图标了。抽屉只递过来一个标识（appid 或路径），这里翻出完整条目再启动。"""
        it = self.cfg.find(key) or {"path": key, "name": ""}
        if launch_item(it):
            return
        # 打不开就去修：重解析快捷方式、或按名字另找一个入口，补齐目标再启动
        if self.cfg.relocate(it):
            self.cfg.save()
            self.drawer.rebuild()
            if launch_item(it):
                return
        # 到这儿是真打不开了 —— 必须说出来，不能像以前那样静默失败
        name = it.get("name") or os.path.splitext(
            os.path.basename(it.get("path", "")))[0] or "这个应用"
        self.tray.showMessage(
            "EdgeDock", "打不开「%s」：这个应用已经不在这台机器上了。\n"
            "请在设置里重新选择（或右键该图标 → 从抽屉中移除）。" % name,
            QSystemTrayIcon.Warning, 5000)

    # ------------------------------------------------------------------
    def _poll_hotkey(self) -> None:
        text = self.cfg["hotkey"]
        parsed = winapi.parse_hotkey(text) if text and text != "禁用" else None
        if not parsed:
            self._hot_prev = False
            return
        mods, vk = parsed
        u = winapi.user32
        down = bool(u.GetAsyncKeyState(vk) & 0x8000)
        # 修饰键必须全部按下才算数（MOD_KEYS 表在 winapi 里，别每 40ms 重建一次）
        ok = all(u.GetAsyncKeyState(code) & 0x8000
                 for bit, code in winapi.MOD_KEYS if mods & bit)
        if down and ok and not self._hot_prev:
            self.drawer.toggle()
        self._hot_prev = down

    # ------------------------------------------------------------------
    def _ensure_settings(self) -> SettingsDialog:
        if self.settings_dlg is None:
            self.settings_dlg = SettingsDialog(self.cfg, self.store)
            self.settings_dlg.changed.connect(self.apply_settings)
            self.settings_dlg.minimizedChanged.connect(self._on_settings_minimized)
            self.settings_dlg.finished.connect(self._settings_closed)
        return self.settings_dlg

    def open_settings(self) -> None:
        dlg = self._ensure_settings()
        self._hold_drawer(True)
        # showNormal()：之前最小化过的话，从托盘菜单唤回来要能还原
        # （show() 只负责显示，不会把最小化的窗口拉回来）
        dlg.showNormal()
        dlg.raise_()
        dlg.activateWindow()

    def add_files(self) -> None:
        self.open_settings()
        self.settings_dlg.add_files()

    def _hold_drawer(self, hold: bool) -> None:
        """按住 / 松开抽屉：按住时保持展开且不抢置顶，松开时交给自动收起。"""
        self.drawer.hold_open = hold
        if hold:
            self.drawer.expand()
        winapi.set_topmost(int(self.drawer.winId()), not hold)

    def _on_settings_minimized(self, mini: bool) -> None:
        """设置窗口最小化时把抽屉松开，还原时再按住。

        不然最小化之后抽屉还钉在这儿挡着别的窗口，而设置窗口又找不着了。
        """
        # 最小化状态下直接关窗口时，Qt 先发 finished 再发一条「已不最小化」，
        # 那条迟到的信号会把抽屉按住不放 —— 认一下发信人是不是当前这个窗口。
        if self.sender() is not self.settings_dlg:
            return
        self._hold_drawer(not mini)

    def _settings_closed(self, _result) -> None:
        self.settings_dlg = None
        self._hold_drawer(False)

    def apply_settings(self) -> None:
        self.cfg.save()
        self.t = theme_mod.get(self.cfg["theme"])
        if self.settings_dlg is not None:
            self.settings_dlg.t = self.t
            self.settings_dlg.setStyleSheet(theme_mod.settings_qss(self.t))
        self.drawer.rebuild()

    # ------------------------------------------------------------------
    def _first_run_hint(self) -> None:
        self.tray.showMessage(
            "EdgeDock 已就绪",
            "鼠标移到屏幕%s边缘即可唤出抽屉。\n右键托盘图标可添加应用或调整设置。"
            % {"top": "上", "bottom": "下", "left": "左", "right": "右"}
            .get(self.cfg["edge"], "上"),
            QSystemTrayIcon.Information, 6000)
        self.drawer.expand()

    def quit(self) -> None:
        self.store.stop()
        self.tray.hide()
        self.app.quit()


# ----------------------------------------------------------------------
def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("EdgeDock")
    app.setApplicationDisplayName("EdgeDock")
    app.setQuitOnLastWindowClosed(False)

    if not winapi.acquire_single_instance():
        QMessageBox.information(None, "EdgeDock",
                                "EdgeDock 已经在运行了（请看系统托盘）。")
        return 0

    winapi.ensure_com()
    dock = EdgeDock(app)
    app._dock = dock
    return app.exec()
