# -*- coding: utf-8 -*-
"""配色方案。

抽屉用「墨黑 + 琥珀橙」，贴合壁纸、暖色更显眼；设置窗口单独走**白灰简约**
（纯白卡片 + 浅灰细线 + 近黑强调），两套配色各管一块，互不干扰。

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
    "dialog": "#18181B",
    "panel_hi": QColor(38, 40, 47, 240),      # 面板渐变顶部
    "panel_lo": QColor(18, 19, 23, 234),      # 面板渐变底部
    "border": QColor(255, 255, 255, 26),
    "edge_light": QColor(255, 255, 255, 22),  # 内侧高光
    "hover": QColor(255, 255, 255, 28),
    "hover_ring": QColor(255, 122, 45, 90),
    "text": "#EAEAEC",
    "subtext": "#9A9AA0",
    "accent": QColor(255, 122, 45),
    "grip": QColor(255, 140, 70, 190),
    "toast_bg": QColor(24, 25, 30, 242),
    "divider": QColor(255, 255, 255, 20),
    "scroll": QColor(255, 255, 255, 46),
    "immersive_dark": 1,
    # 设置界面用色：白灰简约（Codex Desktop 那种）—— 中性灰阶，只有一个
    # 近白强调色，不掺任何彩色。
    "card": "#212124",
    "card_border": "#303034",
    "btn": "#26262A",
    "btn_border": "#35353A",
    "btn_hover": "#2E2E33",
    "btn_press": "#35353B",
    "menu_sel": "rgba(255,122,45,62)",
    "menu_bg": "#1E2024",
    "input_bg": "#1B1B1E",
    "input_border": "#35353A",
    "list_sel": "rgba(255,255,255,18)",
    "list_hover": "#2A2A2E",
    "track": "#3A3A3F",
    "ind_border": "#4A4A50",
    "ind_bg": "#1B1B1E",
    "popup_bg": "#242428",
    # 设置界面的强调色。抽屉仍是琥珀橙 —— 它贴在壁纸上，暖色更显眼；
    # 设置窗口走中性灰，强调色就是「最亮的那一档」，不需要另一个色相。
    "s_accent": "#EDEDEF",
    "s_accent_soft": "#D8D8DC",
    "s_accent_text": "#17171A",
}

LIGHT = {
    "name": "light",
    "dialog": "#F6F6F7",
    # 半透明：能透出壁纸的层次，同时保持图标对比度
    "panel_hi": QColor(255, 255, 255, 202),
    "panel_lo": QColor(238, 240, 245, 184),
    "border": QColor(15, 18, 25, 46),
    "edge_light": QColor(255, 255, 255, 210),
    "hover": QColor(15, 18, 25, 26),
    "hover_ring": QColor(255, 122, 45, 130),
    "text": "#1F2328",
    "subtext": "#6E7681",
    "accent": QColor(255, 110, 30),
    "grip": QColor(255, 120, 40, 175),
    "toast_bg": QColor(252, 252, 254, 238),
    "divider": QColor(15, 18, 25, 22),
    "scroll": QColor(15, 18, 25, 60),
    "immersive_dark": 0,
    "card": "#FFFFFF",
    "card_border": "#E6E6E9",
    "btn": "#FFFFFF",
    "btn_border": "#DCDCE0",
    "btn_hover": "#F4F4F6",
    "btn_press": "#ECECEF",
    "menu_sel": "rgba(255,122,45,56)",
    "menu_bg": "#FFFFFF",
    "input_bg": "#FFFFFF",
    "input_border": "#DCDCE0",
    "list_sel": "#F0F0F2",
    "list_hover": "#F7F7F9",
    "track": "#E6E6E9",
    "ind_border": "#C9C9CE",
    "ind_bg": "#FFFFFF",
    "popup_bg": "#FFFFFF",
    "s_accent": "#1F2328",
    "s_accent_soft": "#33383F",
    "s_accent_text": "#FFFFFF",
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


UI_FONT = ('"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", '
           '"PingFang SC", sans-serif')


def settings_qss(t: dict) -> str:
    """设置窗口样式表：白灰简约。

    一张白卡片 + 一圈 1px 浅灰细线 + 8px 圆角，全局只有一个强调色（近黑 /
    近白），字用系统无衬线。没有发光、没有渐变、没有彩色标签 —— 目标是让它
    看起来像一块安静的桌面面板，而不是一块终端。
    """
    return """
    QDialog { background: %(dialog)s; }
    QWidget { color: %(text)s; font-family: %(ui)s; font-size: 12px; }
    QLabel#Title   { font-size: 16px; font-weight: 600; }
    QLabel#Brand   { color: %(subtext)s; font-size: 12px; }
    QLabel#Section { color: %(subtext)s; font-size: 11px; font-weight: 600; }
    QLabel#Hint    { color: %(subtext)s; font-size: 11px; }
    QFrame#Card    { background: %(card)s; border: 1px solid %(card_border)s;
                     border-radius: 8px; }
    QFrame#FootLine { background: %(card_border)s; border: none; }
    QPushButton { background: %(btn)s; border: 1px solid %(btn_border)s;
                  border-radius: 6px; padding: 5px 12px; }
    QPushButton:hover   { background: %(btn_hover)s;
                          border-color: %(btn_border_hover)s; }
    QPushButton:pressed { background: %(btn_press)s; }
    QPushButton:disabled { color: %(subtext)s; }
    QPushButton#Primary { background: %(accent)s; color: %(accent_text)s;
                          border: 1px solid %(accent)s; font-weight: 600; }
    QPushButton#Primary:hover { background: %(accent_soft)s;
                                border-color: %(accent_soft)s; }
    /* 内边距别调大：左列「吸附到」一行要放下四个按钮，
       稍微超出一点布局就会去压缩间距，标签和按钮就会贴到一起。 */
    QPushButton#Seg { padding: 5px 9px; }
    QPushButton#Seg:checked { background: %(accent)s; color: %(accent_text)s;
                              border: 1px solid %(accent)s; }
    QCheckBox { spacing: 8px; }
    /* 列表里的复选框必须自己画：一旦有 ::item 规则，Qt 就不再拿原生样式
       画指示器，勾没勾上都画成同一个空方框 —— 用户看见的就是「点了没反应」。 */
    QCheckBox::indicator, QListWidget::indicator {
        width: 15px; height: 15px; border-radius: 4px;
        border: 1px solid %(ind_border)s; background: %(ind_bg)s; }
    QCheckBox::indicator:checked, QListWidget::indicator:checked {
        background: %(accent)s; border: 1px solid %(accent)s; }
    QCheckBox::indicator:hover, QListWidget::indicator:hover {
        border: 1px solid %(accent_soft)s; }
    QListWidget { background: transparent; border: none; outline: none; }
    QListWidget::item { padding: 6px 8px; border-radius: 6px; }
    QListWidget::item:selected { background: %(list_sel)s; }
    QListWidget::item:hover { background: %(list_hover)s; }
    QSlider::groove:horizontal { height: 4px; border-radius: 2px;
                                 background: %(track)s; }
    QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
    QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0;
                                 border-radius: 7px; background: %(accent)s; }
    /* 输入框跟下拉框用同一套皮肤。不写这条的话 Qt 会退回 Windows 11
       原生样式 —— 底下拖一道蓝线，跟其余控件完全不是一家人。 */
    QLineEdit { background: %(input_bg)s; border: 1px solid %(input_border)s;
                border-radius: 6px; padding: 5px 9px; }
    QLineEdit:focus { border: 1px solid %(accent)s; }
    QComboBox { background: %(input_bg)s; border: 1px solid %(input_border)s;
                border-radius: 6px; padding: 4px 9px; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView { background: %(popup_bg)s; color: %(text)s;
                border: 1px solid %(input_border)s; outline: none;
                padding: 4px; border-radius: 6px;
                selection-background-color: %(accent)s;
                selection-color: %(accent_text)s; }
    QScrollArea { background: transparent; border: none; }
    QScrollArea > QWidget > QWidget { background: transparent; }
    QScrollArea > QWidget > QScrollBar { background: transparent; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
    QScrollBar::handle:vertical { background: %(scroll)s; min-height: 28px;
                                  border-radius: 4px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical
        { background: transparent; }
    """ % {
        "dialog": t["dialog"], "text": t["text"], "subtext": t["subtext"],
        "ui": UI_FONT,
        "card": t["card"], "card_border": t["card_border"],
        "btn": t["btn"], "btn_border": t["btn_border"],
        "btn_border_hover": t["ind_border"],
        "btn_hover": t["btn_hover"], "btn_press": t["btn_press"],
        "accent": t["s_accent"], "accent_soft": t["s_accent_soft"],
        "accent_text": t["s_accent_text"],
        "ind_border": t["ind_border"], "ind_bg": t["ind_bg"],
        "list_sel": t["list_sel"], "list_hover": t["list_hover"],
        "track": t["track"], "input_bg": t["input_bg"],
        "input_border": t["input_border"], "popup_bg": t["popup_bg"],
        "scroll": rgba(t["scroll"]),
    }
