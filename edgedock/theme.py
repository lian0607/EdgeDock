# -*- coding: utf-8 -*-
"""配色方案。

深色方案以「墨黑 + 琥珀橙」为主，贴合深色壁纸；浅色方案为纯净白。

注意：Qt 样式表里的 rgba() 第 4 个参数必须是 0~255 的整数，
写成 0.05 这种小数会被当成满不透明，务必用 Rgba() 辅助函数生成。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication

ACCENT = "#FF7A2D"          # 琥珀橙主色
ACCENT_SOFT = "#FFA35C"

SYSTEM = "system"           # 主题配置里的「跟随系统」
PERSONALIZE_KEY = (r"Software\Microsoft\Windows\CurrentVersion"
                   r"\Themes\Personalize")

DARK = {
    "name": "dark",
    "dialog": "#17181C",
    "panel_hi": QColor(38, 40, 47, 240),      # 面板渐变顶部
    "panel_lo": QColor(18, 19, 23, 234),      # 面板渐变底部
    "border": QColor(255, 255, 255, 26),
    "edge_light": QColor(255, 255, 255, 22),  # 内侧高光
    "hover": QColor(255, 255, 255, 28),
    "hover_ring": QColor(255, 122, 45, 90),
    "text": "#E9EBEF",
    "subtext": "#98A0AC",
    "accent": QColor(255, 122, 45),
    "accent_soft": QColor(255, 163, 92, 150),
    "grip": QColor(255, 140, 70, 190),
    "toast_bg": QColor(24, 25, 30, 242),
    "divider": QColor(255, 255, 255, 20),
    "scroll": QColor(255, 255, 255, 46),
    "immersive_dark": 1,
    # 设置界面用色
    "card": "rgba(255,255,255,12)",
    "card_border": "rgba(255,255,255,22)",
    "btn": "rgba(255,255,255,18)",
    "btn_border": "rgba(255,255,255,26)",
    "btn_hover": "rgba(255,255,255,34)",
    "btn_press": "rgba(255,255,255,48)",
    "menu_sel": "rgba(255,122,45,62)",
    "menu_bg": "#1E2024",
    "input_bg": "rgba(255,255,255,18)",
    "input_border": "rgba(255,255,255,28)",
    "list_sel": "rgba(255,122,45,58)",
    "list_hover": "rgba(255,255,255,16)",
    "track": "rgba(255,255,255,36)",
    "ind_border": "rgba(255,255,255,72)",
    "ind_bg": "rgba(255,255,255,13)",
    "popup_bg": "#22242A",
}

LIGHT = {
    "name": "light",
    "dialog": "#F4F5F7",
    # 半透明：能透出壁纸的层次，同时保持图标对比度
    "panel_hi": QColor(255, 255, 255, 202),
    "panel_lo": QColor(238, 240, 245, 184),
    "border": QColor(15, 18, 25, 46),
    "edge_light": QColor(255, 255, 255, 210),
    "hover": QColor(15, 18, 25, 26),
    "hover_ring": QColor(255, 122, 45, 130),
    "text": "#1B1D22",
    "subtext": "#5C6472",
    "accent": QColor(255, 110, 30),
    "accent_soft": QColor(255, 150, 70, 150),
    "grip": QColor(255, 120, 40, 175),
    "toast_bg": QColor(252, 252, 254, 238),
    "divider": QColor(15, 18, 25, 22),
    "scroll": QColor(15, 18, 25, 60),
    "immersive_dark": 0,
    "card": "#FFFFFF",
    "card_border": "rgba(15,18,25,20)",
    "btn": "#FFFFFF",
    "btn_border": "rgba(15,18,25,26)",
    "btn_hover": "#F0F1F4",
    "btn_press": "#E4E6EB",
    "menu_sel": "rgba(255,122,45,56)",
    "menu_bg": "#FFFFFF",
    "input_bg": "#FFFFFF",
    "input_border": "rgba(15,18,25,26)",
    "list_sel": "rgba(255,122,45,52)",
    "list_hover": "#F0F1F4",
    "track": "rgba(15,18,25,36)",
    "ind_border": "rgba(15,18,25,72)",
    "ind_bg": "#FFFFFF",
    "popup_bg": "#FFFFFF",
}

THEMES = {"dark": DARK, "light": LIGHT}


def system_theme() -> str:
    """问 Windows 现在是深色还是浅色。

    优先用 Qt 6.5+ 的 colorScheme()：它跟着系统走，还能发变更信号，
    在主流系统上比查注册表可靠。拿不到就退回读注册表，再不行按深色处理。
    """
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except Exception:
        pass
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY) as k:
            # AppsUseLightTheme: 1 = 浅色，0 = 深色
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        return "dark"


def resolve(name: str) -> str:
    """把配置里的主题名解析成真实的 dark / light（system 就现问系统）。"""
    if name == SYSTEM:
        return system_theme()
    return name if name in THEMES else "dark"


def get(name: str) -> dict:
    return THEMES[resolve(name)]


def rgba(c: QColor) -> str:
    return "rgba(%d,%d,%d,%d)" % (c.red(), c.green(), c.blue(), c.alpha())


def menu_qss(t: dict) -> str:
    """右键菜单样式（抽屉 / 托盘共用）。"""
    return (
        "QMenu{background:%(bg)s;color:%(fg)s;border:1px solid %(bd)s;"
        "border-radius:10px;padding:6px;}"
        "QMenu::item{padding:6px 26px 6px 14px;border-radius:7px;}"
        "QMenu::item:selected{background:%(sel)s;}"
        "QMenu::item:disabled{color:%(dis)s;}"
        "QMenu::separator{height:1px;margin:5px 10px;background:%(sep)s;}"
        "QMenu::indicator{width:14px;height:14px;}"
    ) % {"bg": t["menu_bg"], "fg": t["text"], "bd": t["btn_border"],
         "sel": t["menu_sel"], "sep": rgba(t["divider"]),
         "dis": t["subtext"]}


def settings_qss(t: dict) -> str:
    """设置窗口样式表。"""
    d = t["name"] == "dark"
    return """
    QDialog { background: %(dialog)s; }
    QWidget { color: %(text)s;
              font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
              font-size: 13px; }
    QLabel#Title   { font-size: 16px; font-weight: 600; }
    QLabel#Section { color: %(subtext)s; font-size: 11px; font-weight: 600;
                     letter-spacing: 1px; }
    QLabel#Hint    { color: %(subtext)s; font-size: 12px; }
    QFrame#Card    { background: %(card)s; border: 1px solid %(card_border)s;
                     border-radius: 12px; }
    QFrame#FootLine { background: %(card_border)s; border: none; }
    QPushButton { background: %(btn)s; border: 1px solid %(btn_border)s;
                  border-radius: 8px; padding: 6px 14px; }
    QPushButton:hover   { background: %(btn_hover)s; }
    QPushButton:pressed { background: %(btn_press)s; }
    QPushButton#Primary { background: %(accent)s; color: #FFFFFF; border: none;
                          font-weight: 600; }
    QPushButton#Primary:hover { background: %(accent_soft)s; }
    /* 内边距别调大：左列「吸附到」一行要放下四个按钮，
       稍微超出一点布局就会去压缩间距，标签和按钮就会贴到一起。 */
    QPushButton#Seg { padding: 6px 9px; }
    QPushButton#Seg:checked { background: %(accent)s; color: #FFFFFF;
                              border: 1px solid %(accent)s; font-weight: 600; }
    QCheckBox { spacing: 8px; }
    QCheckBox::indicator { width: 16px; height: 16px; border-radius: 5px;
                           border: 1px solid %(ind_border)s;
                           background: %(ind_bg)s; }
    QCheckBox::indicator:checked { background: %(accent)s;
                                   border: 1px solid %(accent)s; }
    QListWidget { background: transparent; border: none; outline: none; }
    QListWidget::item { padding: 6px; border-radius: 8px; }
    QListWidget::item:selected { background: %(list_sel)s; }
    QListWidget::item:hover { background: %(list_hover)s; }
    QSlider::groove:horizontal { height: 4px; border-radius: 2px;
                                 background: %(track)s; }
    QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
    QSlider::handle:horizontal { width: 13px; height: 13px; margin: -6px 0;
                                 border-radius: 7px; background: #FFFFFF;
                                 border: 2px solid %(accent)s; }
    /* 输入框跟下拉框用同一套皮肤。不写这条的话 Qt 会退回 Windows 11
       原生样式 —— 底下拖一道蓝线，跟其余控件完全不是一家人。 */
    QLineEdit { background: %(input_bg)s; border: 1px solid %(input_border)s;
                border-radius: 8px; padding: 6px 10px; }
    QLineEdit:focus { border: 1px solid %(accent)s; }
    QComboBox { background: %(input_bg)s; border: 1px solid %(input_border)s;
                border-radius: 8px; padding: 5px 10px; }
    QComboBox::drop-down { border: none; width: 22px; }
    QComboBox QAbstractItemView { background: %(popup_bg)s; color: %(text)s;
                border: 1px solid %(input_border)s; outline: none;
                selection-background-color: %(accent)s;
                selection-color: #FFFFFF; }
    QScrollArea { background: transparent; border: none; }
    QScrollArea > QWidget > QWidget { background: transparent; }
    QScrollArea > QWidget > QScrollBar { background: transparent; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: %(scroll)s; border-radius: 4px;
                                  min-height: 30px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical
        { background: transparent; }
    """ % {
        "dialog": t["dialog"], "text": t["text"], "subtext": t["subtext"],
        "card": t["card"], "card_border": t["card_border"],
        "btn": t["btn"], "btn_border": t["btn_border"],
        "btn_hover": t["btn_hover"], "btn_press": t["btn_press"],
        "accent": ACCENT, "accent_soft": ACCENT_SOFT,
        "ind_border": t["ind_border"], "ind_bg": t["ind_bg"],
        "list_sel": t["list_sel"], "list_hover": t["list_hover"],
        "track": t["track"], "input_bg": t["input_bg"],
        "input_border": t["input_border"], "popup_bg": t["popup_bg"],
        "scroll": rgba(t["scroll"]),
    }
