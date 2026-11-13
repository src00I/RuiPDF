"""界面主题：浅色、扁平、圆角。颜色集中在这里，想换风格只改这个文件。"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette

ACCENT = "#0A84FF"        # 强调色（选中、滑块、当前项）
ACCENT_SOFT = "#E1ECFF"   # 选中项的浅色底
ACCENT_TEXT = "#0A64D8"
BAR = "#FFFFFF"           # 工具栏 / 状态栏底色
WINDOW = "#F2F2F4"        # 窗口底色
LINE = "#E3E3E6"          # 分隔线
TEXT = "#2C2C2E"
TEXT_DIM = "#6E6E73"
CANVAS_BG = "#E6E6EA"     # 页面周围的底色
PAGE_EDGE = "#CFCFD6"     # 页面边框
ICON = "#3A3A3C"          # 图标线条颜色

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "ui").replace("\\", "/")
STYLE = f"""
QMainWindow {{ background: {WINDOW}; }}
QToolBar {{ background: {BAR}; border: none; border-bottom: 1px solid {LINE}; spacing: 2px; padding: 4px 8px; }}
QToolBar::separator {{ background: {LINE}; width: 1px; margin: 6px 6px; }}
QToolBar QLabel {{ color: {TEXT_DIM}; }}
QToolButton {{ border: none; border-radius: 8px; padding: 4px 3px; color: {TEXT}; font-size: 13px; }}
QToolButton:hover {{ background: #F0F0F3; }}
QToolButton:pressed {{ background: #E2E2E7; }}
QToolButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; }}
QToolButton:disabled {{ color: #B8B8BD; }}
QToolButton::menu-indicator {{ image: none; }}
QToolButton#qt_toolbar_ext_button {{ padding: 0; border-radius: 4px; background: #F0F0F3; }}
QToolBar#strip QToolButton#qt_toolbar_ext_button {{ padding: 0; }}
QToolBar#strip QToolButton {{ padding: 4px 5px; }}
QToolButton[popupMode="1"] {{ padding-right: 16px; }}
QToolButton::menu-button {{ border: none; width: 14px; border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QToolButton::menu-button:hover {{ background: #E2E2E7; }}
QToolBar#strip QToolButton#swatch {{ padding: 3px; border-radius: 16px; }}
QToolButton#swatch:checked {{ background: transparent; }}
QToolButton#swatch:hover {{ background: #F0F0F3; }}
QPushButton {{ background: #F0F0F3; border: none; border-radius: 7px; padding: 5px 12px; color: {TEXT}; }}
QPushButton:hover {{ background: #E6E6EA; }}
QPushButton:pressed {{ background: #DADAE0; }}
QLineEdit {{ background: #F4F4F6; border: 1px solid #E0E0E4; border-radius: 7px; padding: 4px 8px; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: #DCDCE0; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #FFFFFF; border: 1px solid #C7C7CC; width: 16px; margin: -7px 0; border-radius: 8px; }}
QTabWidget::pane {{ border: none; }}
QTabWidget::tab-bar {{ left: 12px; }}  /* 下面的页面区是圆角的（corners.py），标签往右让开那个角 */
QMainWindow::separator {{ width: 7px; height: 7px; background: transparent; }}  /* 页面区和侧栏之间的缝 */
QTabBar {{ background: {WINDOW}; }}
QTabBar::tab {{ background: transparent; color: {TEXT_DIM}; padding: 7px 14px; border: none;
               border-top-left-radius: 8px; border-top-right-radius: 8px; margin-top: 0; }}
QTabBar::tab:selected {{ background: {BAR}; color: #1C1C1E; }}
QTabBar::tab:hover:!selected {{ background: #E9E9EC; }}
/* 标签页的关闭按钮：系统自带的那个叉又粗又突兀，换成细的灰色叉，移上去时垫一个淡淡的圆 */
QTabBar::close-button {{ image: url(@UI@/tab_close.png); subcontrol-position: right; width: 16px; height: 16px; margin: 0 2px; }}
QTabBar::close-button:hover {{ image: url(@UI@/tab_close_hover.png); }}
QTabBar::close-button:pressed {{ image: url(@UI@/tab_close_pressed.png); }}
QStatusBar {{ background: {BAR}; border-top: 1px solid {LINE}; color: {TEXT_DIM}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {TEXT_DIM}; }}
QMenu {{ background: {BAR}; border: 1px solid #DADADF; padding: 5px; }}
QMenu::item {{ padding: 6px 24px 6px 24px; border-radius: 6px; color: {TEXT}; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT_TEXT}; }}
QMenu::separator {{ height: 1px; background: #E8E8EB; margin: 5px 8px; }}
QDockWidget {{ color: {TEXT}; }}
QDockWidget::title {{ background: {BAR}; padding: 7px 10px; border-bottom: 1px solid {LINE}; }}
/* 侧栏标题上的关闭按钮：和标签页的关闭按钮同一个样子（细的灰色叉，移上去垫一个淡淡的圆） */
QDockWidget {{ titlebar-close-icon: url(@UI@/tab_close.png); }}
QDockWidget::close-button {{ border: none; background: transparent; border-radius: 9px; padding: 1px;
           subcontrol-position: right center; subcontrol-origin: margin; right: 8px; }}
QDockWidget::close-button:hover {{ background: rgba(60,60,67,34); }}
QDockWidget::close-button:pressed {{ background: rgba(60,60,67,62); }}
QListWidget, QTreeWidget {{ background: #FAFAFB; border: none; outline: 0; color: {TEXT}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {ACCENT_SOFT}; color: #1C1C1E; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #C4C4CA; border-radius: 3px; min-height: 30px; margin: 2px 3px; }}
QScrollBar::handle:vertical:hover {{ background: #A9A9B0; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QSplitter::handle {{ background: #D6D6DB; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QToolTip {{ background: #2C2C2E; color: #FFFFFF; border: none; padding: 4px 8px; }}
""".replace("@UI@", _UI_DIR)

# 液态玻璃：在上面的样式之后追加，后写的规则覆盖前面的。
# 窗口本身透明，后面是系统的毛玻璃（见 winglass.py）；工具栏做成一条条半透明的"玻璃胶囊"：
# 上亮下暗的白色渐变当高光，一圈更亮的细边当玻璃的边缘。页面区域保持不透明，不影响看讲义。
_GLASS_FILL = ("qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,178), "
               "stop:0.45 rgba(255,255,255,112), stop:1 rgba(255,255,255,140))")
GLASS_STYLE = STYLE + f"""
QMainWindow {{ background: transparent; }}
QToolBar {{ background: {_GLASS_FILL}; border: 1px solid rgba(255,255,255,200); border-radius: 13px;
           margin: 4px 0 1px 0; padding: 2px 6px; }}
QToolBar::separator {{ background: rgba(60,60,67,36); }}
QToolButton:hover {{ background: rgba(255,255,255,150); }}
QToolButton:pressed {{ background: rgba(255,255,255,205); }}
QToolButton:checked {{ background: rgba(10,132,255,46); border: 1px solid rgba(10,132,255,70); color: {ACCENT_TEXT}; }}
QToolButton#swatch:checked {{ background: transparent; border: none; }}
QToolButton#swatch:hover {{ background: rgba(255,255,255,150); }}
QToolButton#qt_toolbar_ext_button {{ background: rgba(255,255,255,150); }}
QToolButton::menu-button:hover {{ background: rgba(255,255,255,205); }}
QPushButton {{ background: rgba(255,255,255,140); border: 1px solid rgba(255,255,255,200); }}
QPushButton:hover {{ background: rgba(255,255,255,190); }}
QPushButton:pressed {{ background: rgba(255,255,255,230); }}
QLineEdit {{ background: rgba(255,255,255,160); border: 1px solid rgba(255,255,255,210); }}
QTabBar {{ background: transparent; }}
/* 文档标签那一行右端的查找框 */
QWidget#findBox QLineEdit {{ border-radius: 9px; padding: 3px 8px; }}
QWidget#findBox QToolButton {{ padding: 2px 6px; font-size: 14px; }}
QWidget#findBox QLabel {{ color: {TEXT_DIM}; }}
/* 标签太多放不下时两端的翻页小按钮：圆角、没有方框 */
QTabBar QToolButton {{ background: transparent; border: none; border-radius: 7px; margin: 3px 1px; padding: 0; }}
QTabBar QToolButton:hover {{ background: rgba(60,60,67,28); }}
QTabBar::tab:selected {{ background: rgba(255,255,255,205); border: 1px solid rgba(255,255,255,220); border-bottom: none; }}
QTabBar::tab:hover:!selected {{ background: rgba(255,255,255,110); }}
QStatusBar {{ background: {_GLASS_FILL}; border: 1px solid rgba(255,255,255,200); border-radius: 10px; }}
QDockWidget::title {{ background: {_GLASS_FILL}; border-bottom: 1px solid rgba(255,255,255,200); }}
QDockWidget {{ background: transparent; }}
QListWidget, QTreeWidget {{ background: rgba(255,255,255,165); }}
QSplitter::handle {{ background: rgba(255,255,255,120); }}

/* 下拉框、数字框：和按钮一样的半透明圆角胶囊。一旦自定义外观，Qt 就不画自带的小箭头了，
   所以箭头用 assets/ui/ 里的图（tools/make_ui_assets.py 生成）。 */
QComboBox, QAbstractSpinBox {{ background: {_GLASS_FILL}; border: 1px solid rgba(255,255,255,215);
           border-radius: 9px; padding: 3px 8px; min-height: 20px; color: {TEXT};
           selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; }}
QComboBox:hover, QAbstractSpinBox:hover {{ background: rgba(255,255,255,190); }}
QComboBox:focus, QAbstractSpinBox:focus {{ border: 1px solid rgba(10,132,255,150); }}
QComboBox {{ padding-right: 24px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }}
QComboBox::down-arrow {{ image: url(@UI@/arrow_down.png); width: 12px; height: 12px; }}
QAbstractSpinBox {{ padding-right: 20px; }}
QAbstractSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 18px; border: none;
           margin: 2px 2px 0 0; border-top-right-radius: 7px; }}
QAbstractSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 18px; border: none;
           margin: 0 2px 2px 0; border-bottom-right-radius: 7px; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: rgba(255,255,255,200); }}
QAbstractSpinBox::up-arrow {{ image: url(@UI@/spin_up.png); width: 9px; height: 9px; }}
QAbstractSpinBox::down-arrow {{ image: url(@UI@/spin_down.png); width: 9px; height: 9px; }}

/* 弹出来的东西（菜单、下拉列表）：圆角的玻璃片。窗口本身的透明、圆角和毛玻璃由 prepare_popup() 和
   winglass.enable_popup() 负责，这里只管颜色和形状。 */
QMenu {{ background: rgba(255,255,255,128); border: 1px solid rgba(255,255,255,205); border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 26px 6px 22px; border-radius: 7px; margin: 1px 0; }}
QMenu::item:selected {{ background: rgba(10,132,255,56); color: {ACCENT_TEXT}; }}
QMenu::separator {{ height: 1px; background: rgba(60,60,67,40); margin: 5px 10px; }}
QComboBox QAbstractItemView {{ background: rgba(255,255,255,128); border: 1px solid rgba(255,255,255,205);
           border-radius: 10px; padding: 5px; outline: 0; }}
QComboBox QAbstractItemView::item {{ padding: 5px 10px; border-radius: 7px; min-height: 22px; color: {TEXT}; }}
QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{
           background: rgba(10,132,255,56); color: {ACCENT_TEXT}; }}

/* 对话框的底是不透明的浅灰，上面的控件要有一圈淡淡的深色边才看得出轮廓 */
QDialog QComboBox, QDialog QAbstractSpinBox, QDialog QLineEdit {{ background: rgba(255,255,255,215);
           border: 1px solid rgba(60,60,67,42); }}
QDialog QComboBox:focus, QDialog QAbstractSpinBox:focus, QDialog QLineEdit:focus {{ border: 1px solid rgba(10,132,255,170); }}
QDialog QPushButton {{ background: rgba(255,255,255,215); border: 1px solid rgba(60,60,67,42); border-radius: 9px;
           padding: 5px 16px; min-width: 56px; }}
QDialog QPushButton:hover {{ background: #FFFFFF; }}
QDialog QPushButton:default {{ background: rgba(10,132,255,225); border: 1px solid rgba(10,132,255,240); color: #FFFFFF; }}
QDialog QPushButton:default:hover {{ background: rgba(10,132,255,245); }}

/* 其余小控件 */
QSlider::groove:horizontal {{ background: rgba(60,60,67,46); }}
QSlider::handle:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #E9EEF6);
           border: 1px solid rgba(255,255,255,235); }}
QCheckBox {{ color: {TEXT}; }}
QToolTip {{ background: rgba(44,44,46,235); border-radius: 6px; }}
/* 滚动条的滑块：两头是圆的。圆角半径不能超过滑块宽度的一半，超过了 Qt 就整个不画圆角（出过：写 4px 结果是方的）。
   滚动条宽 12，左右各留 3，滑块宽 6，所以半径是 3。 */
QScrollBar::handle:vertical {{ background: rgba(60,60,67,90); border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(60,60,67,140); }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: rgba(60,60,67,90); border-radius: 3px; min-width: 30px; margin: 3px 2px; }}
QScrollBar::handle:horizontal:hover {{ background: rgba(60,60,67,140); }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
""".replace("@UI@", _UI_DIR)

# 文字输入框上方那条格式工具条（textedit.FormatBar）的两种外观。它浮在页面上，后面没有毛玻璃可透，
# 所以玻璃版用的是更实一些的磨砂白，形状和高光与工具栏一致。
FORMAT_BAR_STYLE = (
    "FormatBar { background: #FFFFFF; border: 1px solid #C7C7CC; border-radius: 6px; }"
    "QToolButton { border: none; border-radius: 4px; padding: 2px 6px; min-width: 18px; font-size: 13px; }"
    "QToolButton:hover { background: #E9E9EE; } QToolButton:checked { background: #D6E4FF; }"
    "QToolButton::menu-indicator { image: none; }")
FORMAT_BAR_GLASS = (
    "FormatBar { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,246),"
    " stop:1 rgba(240,244,250,236)); border: 1px solid rgba(60,60,67,50); border-radius: 12px; }"
    "FormatBar QComboBox, FormatBar QAbstractSpinBox { background: rgba(60,60,67,13); border: 1px solid rgba(60,60,67,34); }"
    "FormatBar QComboBox:hover, FormatBar QAbstractSpinBox:hover { background: rgba(60,60,67,24); }"
    "QToolButton { border: none; border-radius: 8px; padding: 3px 7px; min-width: 18px; font-size: 13px; }"
    "QToolButton:hover { background: rgba(10,132,255,26); }"
    "QToolButton:checked { background: rgba(10,132,255,46); border: 1px solid rgba(10,132,255,70); }"
    "QToolButton::menu-indicator { image: none; }")

# 浮在页面上的工具条（floatbar.FloatBar）和它旁边的笔设置面板的两种外观。里面的两条工具栏自己不再画底，
# 整条浮条才是那块"玻璃"。它后面是页面，没有毛玻璃可透，所以玻璃版用的是带高光的磨砂白。
_FLOAT_COMMON = (
    "QToolBar { background: transparent; border: none; margin: 0; padding: 2px 4px; }"
    "QToolBar[orientation=\"2\"] { padding: 4px 0; }"  # 竖排时左右不留边，条才能拖得窄
    "QToolBar::separator:horizontal { width: 1px; margin: 7px 6px; }"
    "QToolBar::separator:vertical { height: 1px; margin: 6px 7px; }"
    "QToolButton#flyBtn { padding: 4px 5px; margin: 2px 0; }")
FLOAT_OPACITY_RANGE = (15, 100)  # 悬浮工具条的不透明度（百分比）可调范围
_FLOAT_GLASS_CONTROLS = (
    "QComboBox, QAbstractSpinBox { background: rgba(60,60,67,13); border: 1px solid rgba(60,60,67,32); }"
    "QComboBox:hover, QAbstractSpinBox:hover { background: rgba(60,60,67,24); }"
    "QPushButton { background: rgba(60,60,67,13); border: 1px solid rgba(60,60,67,32); }"
    "QPushButton:hover { background: rgba(60,60,67,24); }"
    "QToolButton:hover { background: rgba(60,60,67,20); }"
    "QToolButton:pressed { background: rgba(60,60,67,36); }"
    "QToolButton#swatch:hover { background: rgba(60,60,67,20); }")


def prepare_popup(widget):
    """菜单、下拉列表这类弹出窗口：在它第一次显示之前调用，让它的背景可以透明（这样才能有圆角和毛玻璃）。
    只要机器支持就做，不管液态玻璃现在开没开：开关可以在运行中切换，而背景透明只能在窗口创建之前定。
    之后每次显示时由主窗口装的事件过滤器按当时的开关给它铺上 / 撤掉毛玻璃。"""
    if glass_capable:
        widget.setAttribute(Qt.WA_TranslucentBackground)
        widget.setWindowFlag(Qt.NoDropShadowWindowHint)  # 老式的方形阴影不要；圆角窗口由系统自己加阴影
        widget.setProperty("ruiGlass", True)

# 界面字体方案（只管工具栏、菜单这些界面文字；写进 PDF 的文本框和粘贴内容各有各的字体，不受影响）。
# 代号 -> (名称, 西文字体, 中文字体, 字重, 字距 px)。字体按顺序找，机器上没有的自动跳到下一个，
# 最后都落到微软雅黑，所以哪台机器上都能用。名称是界面文字，显示时再过 T()。
UI_FONTS = {
    "system": ("系统默认（微软雅黑）", [], [], 400, 0.0),
    "modern": ("现代（Segoe UI Variable + 思源黑体）", ["Segoe UI Variable Text", "Segoe UI"],
               ["Noto Sans SC", "Microsoft YaHei UI"], 400, 0.2),
    "medium": ("现代 · 略粗（玻璃底上更清楚）", ["Segoe UI Variable Text", "Segoe UI"],
               ["Noto Sans SC Medium", "Noto Sans SC", "Microsoft YaHei UI"], 500, 0.2),
    "light": ("轻盈（细一些）", ["Segoe UI Variable Text Semilight", "Segoe UI Semilight", "Segoe UI"],
              ["Noto Sans SC DemiLight", "Noto Sans SC", "Microsoft YaHei UI Light", "Microsoft YaHei UI"], 350, 0.3),
}
UI_FONT_DEFAULT = "modern"


def ui_font(key: str, base: QFont) -> QFont:
    """某个方案对应的界面字体。base 是系统默认的界面字体（大小沿用它的，只换字体、字重、字距）。"""
    _name, latin, cjk, weight, spacing = UI_FONTS.get(key, UI_FONTS["system"])
    f = QFont(base)
    if latin or cjk:
        f.setFamilies(latin + cjk + [base.family()])
        f.setWeight(QFont.Weight(weight))
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
        f.setHintingPreference(QFont.PreferNoHinting)  # 不做字形微调，笔画形状更匀称，高分屏上更好看
    return f


def light_palette() -> QPalette:
    """固定用浅色调色板：即使 Windows 开了深色模式，界面也保持一致。"""
    p = QPalette()
    for role, color in (
        (QPalette.Window, WINDOW), (QPalette.WindowText, TEXT), (QPalette.Base, "#FFFFFF"),
        (QPalette.AlternateBase, "#F7F7F9"), (QPalette.Text, "#1C1C1E"), (QPalette.Button, "#F4F4F6"),
        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT), (QPalette.HighlightedText, "#FFFFFF"),
        (QPalette.ToolTipBase, "#2C2C2E"), (QPalette.ToolTipText, "#FFFFFF"),
        (QPalette.PlaceholderText, "#A0A0A6"), (QPalette.Light, "#FFFFFF"), (QPalette.Midlight, "#EDEDF0"),
        (QPalette.Mid, "#C7C7CC"), (QPalette.Dark, "#A0A0A6"), (QPalette.Shadow, "#8E8E93"),
    ):
        p.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#B8B8BD"))
    return p


# ---------------------------------------------------------------------- 界面风格
# 六种风格共用同一套样式（GLASS_STYLE：圆角胶囊工具栏、半透明的白），区别只有：
#   * 窗口的底：液态玻璃是透明的（后面是系统毛玻璃），其余是一种纯色；
#   * 页面周围的底色、强调色；
#   * 深色：把样式表里的颜色整体"反过来"（见 adapt），图标也反色（adapt_pixmap）。
# 代号 -> (名称, 窗口底色（None = 透明）, 页面周围的底色, 强调色 RGB, 是不是深色)。名称显示时再过 T()。
THEMES = {
    "glass": ("液态玻璃", None, "#EEF2F8", (10, 132, 255), False),
    "light": ("浅色", "#ECEFF4", "#F5F7FA", (10, 132, 255), False),
    "dark": ("深色主题", "#1B1C20", "#24262B", (70, 160, 255), True),
    "green": ("浅绿色", "#D9EEE0", "#ECF6EF", (36, 156, 98), False),
    "purple": ("浅紫色", "#E6DEF5", "#F2EEFA", (132, 92, 206), False),
    "blue": ("浅蓝色", "#D8E6F7", "#EBF2FB", (24, 116, 228), False),
}
current = "glass"       # 现在用的风格（主窗口按设置定，运行中可以切换）
glass_capable = False   # 这台机器上能不能做液态玻璃（主窗口启动时定）
glass_enabled = False   # 现在是不是液态玻璃（= current == "glass" 且机器支持）
_BASE_ACCENT = (10, 132, 255)


def is_dark() -> bool:
    return THEMES[current][4]


def canvas_bg() -> str:
    """页面周围的底色。"""
    return THEMES[current][2]


def window_color() -> str:
    """窗口的底色（液态玻璃是透明的，这时返回的颜色只在个别地方垫底用）。"""
    return THEMES[current][1] or WINDOW


def _mix(rgb, other, k):
    return tuple(round(a * (1 - k) + b * k) for a, b in zip(rgb, other))


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(rgb)


def _dark_grey(r, g, b):
    """深色风格：把一个灰色（包括黑、白）的明暗反过来；有颜色的不动（返回 None）。"""
    if max(r, g, b) - min(r, g, b) > 24:
        return None
    v = round((0.13 + (1 - (r + g + b) / 765) * 0.80) * 255)
    return v, v, min(255, v + 3)


def _dark_rgba(m):
    r, g, b, a = (int(x) for x in m.groups())
    if min(r, g, b) >= 225:  # 半透明的白：很实的（浮在页面上的条）换成深色实底，其余的变成一层很淡的白
        return "rgba(46,47,52,%d)" % a if a >= 220 else "rgba(255,255,255,%d)" % round(a * 0.14)
    if (r, g, b) == (60, 60, 67):  # 半透明的深灰（分隔线、悬停底色）：换成半透明的浅灰
        return "rgba(235,235,245,%d)" % a
    return m.group(0)


def _dark_hex(m):
    v = int(m.group(1), 16)
    out = _dark_grey(v >> 16, (v >> 8) & 255, v & 255)
    return m.group(0) if out is None else _hex(out)


def adapt(css: str) -> str:
    """把一段按"浅色 + 蓝色强调"写的样式表换成当前风格的：换强调色；深色时再把灰度反过来、箭头图换成浅色的。"""
    import re
    _name, _bg, _cbg, accent, dark = THEMES[current]
    soft = _hex(_mix(accent, (27, 28, 32), 0.70) if dark else _mix(accent, (255, 255, 255), 0.86))
    text = _hex(_mix(accent, (255, 255, 255), 0.35) if dark else _mix(accent, (0, 0, 0), 0.25))
    if dark:  # 先把灰度反过来，再放进强调色（强调色的深浅两种不是灰色，但放在前面保险）
        css = css.replace(ACCENT_SOFT, "@SOFT@").replace(ACCENT_TEXT, "@ATEXT@").replace(ACCENT, "@ACCENT@")
        css = re.sub(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", _dark_rgba, css)
        css = re.sub(r"#([0-9A-Fa-f]{6})\b", _dark_hex, css)
        css = css.replace(_UI_DIR + "/", _UI_DIR + "_dark/")
        css = css.replace("@SOFT@", ACCENT_SOFT).replace("@ATEXT@", ACCENT_TEXT).replace("@ACCENT@", ACCENT)
    css = css.replace(ACCENT_SOFT, soft).replace(ACCENT_TEXT, text).replace(ACCENT, _hex(accent))
    return css.replace("%d,%d,%d" % _BASE_ACCENT, "%d,%d,%d" % accent)


def stylesheet() -> str:
    """当前风格的主窗口样式表。"""
    css = GLASS_STYLE
    bg = THEMES[current][1]
    if bg:  # 不是液态玻璃：弹出菜单后面没有毛玻璃，得是实底，否则会透出下面的东西
        css += ("\nQMenu, QComboBox QAbstractItemView { background: #FBFBFD; border: 1px solid #D5D5DB; }")
    css = adapt(css)
    if bg:
        css += "\nQMainWindow { background: %s; }" % bg
    return css


def format_bar_style() -> str:
    return adapt(FORMAT_BAR_GLASS)


def float_style(opacity: int = 100) -> str:
    """悬浮工具条的样式表。opacity 是不透明度（百分比）：只管那块底，上面的按钮和文字不跟着变淡。"""
    k = max(0.0, min(1.0, opacity / 100))
    if is_dark():
        stops, edge = ((50, 51, 57, 250), (44, 45, 50, 244), (40, 41, 46, 248)), "rgba(255,255,255,%d)" % round(40 * k)
    else:
        stops = ((255, 255, 255, 244), (246, 249, 253, 226), (238, 243, 250, 236))
        edge = "rgba(255,255,255,%d)" % round(255 * max(k, 0.45))
    fill = ", ".join("stop:%s rgba(%d,%d,%d,%d)" % (pos, r, g, b, round(a * k))
                     for pos, (r, g, b, a) in zip(("0", "0.5", "1"), stops))
    return ("FloatBar, QFrame#FloatFlyout { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, %s);"
            " border: 1px solid %s; border-radius: 18px; }" % (fill, edge)) + adapt(_FLOAT_COMMON + _FLOAT_GLASS_CONTROLS)


def adapt_pixmap(pm):
    """深色风格：把图标里的灰色线条反成浅色（有颜色的部分不动）。其余风格原样返回。"""
    if not is_dark():
        return pm
    from PySide6.QtGui import QImage, QPixmap
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    buf = img.bits()
    for i in range(0, img.sizeInBytes(), 4):
        b, g, r, a = buf[i], buf[i + 1], buf[i + 2], buf[i + 3]
        if a and max(r, g, b) - min(r, g, b) <= 40:
            buf[i], buf[i + 1], buf[i + 2] = 255 - b, 255 - g, 255 - r
    out = QPixmap.fromImage(img)
    out.setDevicePixelRatio(pm.devicePixelRatio())
    return out


def palette() -> QPalette:
    """当前风格的调色板（对话框等没有被样式表管到的地方用它）。"""
    p = light_palette()
    accent = QColor(*THEMES[current][3])
    if is_dark():
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            for role in (QPalette.Window, QPalette.WindowText, QPalette.Base, QPalette.AlternateBase, QPalette.Text,
                         QPalette.Button, QPalette.ButtonText, QPalette.PlaceholderText, QPalette.Light,
                         QPalette.Midlight, QPalette.Mid, QPalette.Dark, QPalette.Shadow,
                         QPalette.ToolTipBase, QPalette.ToolTipText):
                c = p.color(group, role)
                out = _dark_grey(c.red(), c.green(), c.blue())
                if out:
                    p.setColor(group, role, QColor(*out))
    p.setColor(QPalette.Highlight, accent)
    return p
