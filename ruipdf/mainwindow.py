"""主窗口：顶部工具栏 + 左侧竖排工具栏 + 多标签页画布 + 右侧侧栏 + 状态栏。"""
import hashlib
import json
import os
import sys
import time

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, QStandardPaths, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QFont, QIcon, QImage, QKeySequence,
                           QPainter, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QApplication, QVBoxLayout, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDockWidget, QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QScrollBar, QSlider,
                               QSpinBox, QSplitter, QStackedWidget, QStyledItemDelegate, QTabWidget, QToolBar,
                               QToolButton, QWidget)

from . import __author__, __version__, i18n
from .appsettings import app_settings
from .i18n import T
from .canvas import IMAGE_EXTS, Canvas, cursor_pixmap
from .corners import round_corners
from .document import Document
from .floatbar import FloatBar
from .textedit import FormatBar
from .newnote import NewNoteDialog
from .templates import TEMPLATES, create_notebook
from .sidebar import Sidebar
from .stroke import PEN_STYLES, item_from_json
from .theme import (ACCENT, ACCENT_SOFT, ICON, UI_FONT_DEFAULT, UI_FONTS,
                    ui_font)
from . import theme, winclaude, winglass
from .winpen import disable_pen_feedback

# 配色方案：名称 -> (4 个笔色, 3 个荧光色)。"自定义"由调色盘修改后自动生成。
PALETTES = {
    "经典": (["#D32F2F", "#2E7D32", "#1565C0", "#111111"], ["#FFEE58", "#A8F0A0", "#FFB3D9"]),
    "鲜艳": (["#FF1744", "#00C853", "#2979FF", "#000000"], ["#FFFF00", "#69F0AE", "#FF80AB"]),
    "柔和": (["#C97C7C", "#7FA58A", "#7C97C0", "#4A4A4A"], ["#F5E6A3", "#CFE8CF", "#F3D1DC"]),
    "深色": (["#8E0000", "#1B5E20", "#0D47A1", "#263238"], ["#FFE082", "#C5E1A5", "#F8BBD0"]),
    "暖色": (["#E64A19", "#F9A825", "#6D4C41", "#212121"], ["#FFE0B2", "#FFF59D", "#FFCCBC"]),
    "冷色": (["#6A1B9A", "#00838F", "#283593", "#37474F"], ["#B3E5FC", "#B2DFDB", "#D1C4E9"]),
}
CUSTOM = "自定义"
WIDTH_MODES = [("page", T("粗细随页面")), ("screen", T("粗细随屏幕"))]
# 粗细滑块的范围：目标 -> (最小, 最大, 步长, 标签)
WIDTH_RANGES = {"pen": (0.2, 10.0, 0.1, T("粗细")), "hl": (2.0, 40.0, 1.0, T("荧光笔宽")), "text": (6.0, 72.0, 1.0, T("字号"))}
# 名称, 笔宽, 荧光笔宽, 文本字号（pt）
WIDTHS = [(T("细"), 0.8, 6.0, 10.0), (T("中"), 1.4, 10.0, 14.0), (T("粗"), 2.4, 16.0, 20.0)]
SHAPE_NAMES = [("line", T("直线")), ("arrow", T("箭头")), ("rect", T("矩形")), ("ellipse", T("椭圆"))]
QUALITIES = [(1.0, T("100%（最省内存）")), (2.0, T("200%（推荐）")), (3.0, T("300%（最细腻，占内存）"))]
SMOOTHINGS = [(0.0, T("关")), (0.35, T("低")), (0.55, T("中")), (0.72, T("高（更顺滑，略有滞后）"))]
LANGUAGES = [("zh", "中文"), ("en", "English")]
CLAUDE_MODES = [("app", T("Claude 窗口（桌面应用或网页，不需要密钥）")), ("api", T("API（侧栏面板，需要密钥）"))]
AUTOSAVE_MS = 15000
# 贴在右边的对话窗口：可选的对象（代号见 winclaude.TARGETS），以及宽 / 高占本窗口的百分比（默认值, 最小, 最大）
DOCK_TARGETS = [("claude", "Claude"), ("chatgpt", "ChatGPT"), ("chrome", T("Chrome 浏览器"))]
DOCK_SIDES = [("right", T("右边")), ("left", T("左边"))]
DOCK_SHORT = {"claude": "Claude", "chatgpt": "ChatGPT", "chrome": "Chrome"}  # 按钮上用的短名字
TOOLBAR_POSITIONS = [("top", T("悬浮在上方")), ("bottom", T("悬浮在下方")), ("left", T("悬浮在左侧")),
                     ("right", T("悬浮在右侧")), ("docked", T("固定在窗口顶部（不悬浮）"))]
PASTE_SIZE_RANGE = (6.0, 36.0)   # 粘贴文字的字号（pt）；设置里存 0 表示自动
PASTE_WIDTH_DEFAULT, PASTE_WIDTH_RANGE = 60, (20, 100)  # 粘贴内容的宽度占页面宽度的百分比
DOCK_W_DEFAULT, DOCK_W_RANGE = 33, (10, 200)
DOCK_H_DEFAULT, DOCK_H_RANGE = 100, (20, 100)
INK = ICON


# ---------------------------------------------------------------------- 图标
def _pixmap(draw, size=28) -> QPixmap:
    pm = QPixmap(size * 2, size * 2)  # 2 倍像素，高分屏上不糊
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p, size)
    p.end()
    return pm


ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_system_font = None  # 系统默认的界面字体：换方案时都从它出发（只换字体和字重，大小沿用它的）


def apply_ui_font(key: str):
    """把界面字体换成某个方案（见 theme.UI_FONTS）。只影响界面文字，不影响写进 PDF 的内容。"""
    global _system_font
    app = QApplication.instance()
    if _system_font is None:
        _system_font = QFont(app.font())
    app.setFont(ui_font(key, _system_font))


def app_icon() -> QIcon:
    """应用图标（ruipdf/assets/，由 tools/make_icon.py 生成）。.ico 里有 16–256 多个尺寸，
    标题栏和任务栏各取合适的那张；文件不在时返回空图标，程序照常运行。"""
    icon = QIcon()
    for name in ("icon.ico", "icon.png"):
        path = os.path.join(ASSETS, name)
        if os.path.exists(path):
            icon.addFile(path)
    return icon


def _icon(draw, size=28) -> QIcon:
    return QIcon(theme.adapt_pixmap(_pixmap(draw, size)))  # 深色风格下线条反成浅色


def _color_icon(color, square=False):
    """色块图标。选中状态 = 外面多一圈同色的环。"""
    def shape(p, s, inset):
        r = QRectF(inset, inset + (3 if square else 0), s - 2 * inset, s - 2 * inset - (6 if square else 0))
        if square:
            p.drawRoundedRect(r, 4, 4)
        else:
            p.drawEllipse(r)

    def off(p, s):
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QColor(color))
        shape(p, s, 4.5)

    def on(p, s):
        ring = QColor(color).darker(115) if QColor(color).lightness() > 200 else QColor(color)
        p.setPen(QPen(ring, 2))
        p.setBrush(Qt.NoBrush)
        shape(p, s, 1.5)
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QColor(color))
        shape(p, s, 6)

    icon = QIcon()
    icon.addPixmap(_pixmap(off), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_pixmap(on), QIcon.Normal, QIcon.On)
    return icon


def _width_icon(w):
    def draw(p, s):
        p.setPen(QPen(QColor(INK), w * 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(6, s - 8, s - 6, 8)
    return _icon(draw)


def _pen_icon():
    def draw(p, s):
        p.setPen(QPen(QColor(INK), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(7, s - 7, s - 9, 9)
        p.drawLine(s - 9, 9, s - 6, 6)
        p.setPen(QPen(QColor(INK), 1.2))
        p.drawLine(5, s - 5, 9, s - 6)
    return _icon(draw)


def _hl_icon():
    def draw(p, s):
        p.setPen(QPen(QColor("#FFD600"), 9, Qt.SolidLine, Qt.FlatCap))
        p.drawLine(5, s - 9, s - 5, s - 9)
        p.setPen(QPen(QColor(INK), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(9, s - 12, s - 8, 7)
    return _icon(draw)


def _eraser_icon():
    def draw(p, s):
        p.setPen(QPen(QColor(INK), 1.6))
        p.setBrush(QColor("#f4b6c2"))
        p.translate(s / 2, s / 2)
        p.rotate(-35)
        p.drawRoundedRect(-9, -6, 18, 12, 2.5, 2.5)
        p.drawLine(-2, -6, -2, 6)
    return _icon(draw)


def _lasso_icon():
    def draw(p, s):
        p.setPen(QPen(QColor(INK), 1.6, Qt.DashLine))
        p.drawEllipse(4, 5, s - 8, s - 13)
        p.setPen(QPen(QColor(INK), 1.6))
        p.drawLine(9, s - 9, 6, s - 4)
    return _icon(draw)


def _sliders_icon():
    def draw(p, s):  # 三条带旋钮的滑杆：表示"设置"
        for k, knob in enumerate((0.68, 0.34, 0.56)):
            y = 8 + k * 6
            p.setPen(QPen(QColor(INK), 1.6, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(6, y, s - 6, y)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(6 + (s - 12) * knob, y), 2.6, 2.6)
    return _icon(draw)


def _select_icon():
    def draw(p, s):  # 一段被选中（蓝底）的文字
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 132, 255, 80))
        p.drawRoundedRect(3, 7, s - 6, s - 14, 2, 2)
        f = p.font()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(INK))
        p.drawText(0, 0, s, s, Qt.AlignCenter, "Aa")
    return _icon(draw)


def _shape_icon(kind):
    def draw(p, s):
        p.setPen(QPen(QColor(INK), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if kind == "rect":
            p.drawRect(5, 7, s - 10, s - 14)
        elif kind == "ellipse":
            p.drawEllipse(4, 7, s - 8, s - 14)
        else:
            p.drawLine(6, s - 6, s - 6, 6)
            if kind == "arrow":
                p.drawLine(s - 6, 6, s - 14, 7)
                p.drawLine(s - 6, 6, s - 7, 14)
    return _icon(draw)


def _cursor_icon(style) -> QIcon:
    """光标样式菜单里的预览图：把真实的光标图裁到内容大小，放进 16×16 的小图标。"""
    box = 16
    if style == "arrow":
        def draw(p, s):
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.setBrush(QColor("#111111"))
            p.drawPolygon([QPointF(3, 1), QPointF(3, 13), QPointF(6.2, 10.2), QPointF(8.3, 15),
                           QPointF(10.3, 14.1), QPointF(8.2, 9.5), QPointF(12.5, 9.5)])
        content = _pixmap(draw, box).toImage()
    else:
        pm, _ = cursor_pixmap(style, "#111111", 3.0, 2.0)
        img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
        xs = [x for x in range(img.width()) for y in range(img.height()) if img.pixelColor(x, y).alpha() > 8]
        ys = [y for y in range(img.height()) for x in range(img.width()) if img.pixelColor(x, y).alpha() > 8]
        content = img.copy(min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
        limit = (box - 2) * 2
        if max(content.width(), content.height()) > limit:
            content = content.scaled(limit, limit, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        content.setDevicePixelRatio(2)

    def compose(selected):
        def draw(p, s):
            if selected:  # 当前选中的样式：浅蓝底 + 蓝边
                p.setPen(QPen(QColor(ACCENT), 1))
                p.setBrush(QColor(ACCENT_SOFT))
                p.drawRoundedRect(QRectF(0.5, 0.5, s - 1, s - 1), 3, 3)
            w, h = content.width() / 2, content.height() / 2
            p.drawImage(QPointF((s - w) / 2, (s - h) / 2), content)
        return _pixmap(draw, box)

    icon = QIcon()
    icon.addPixmap(compose(False), QIcon.Normal, QIcon.Off)
    icon.addPixmap(compose(True), QIcon.Normal, QIcon.On)
    return icon


def _mask_icon():
    def draw(p, s):
        p.setPen(QPen(QColor("#607D8B"), 1.2))
        p.setBrush(QColor("#B0BEC5"))
        p.drawRoundedRect(4, 8, s - 8, s - 16, 2, 2)
    return _icon(draw)


def _text_icon():
    def draw(p, s):
        f = p.font()
        f.setPixelSize(20)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(INK))
        p.drawText(0, 0, s, s, Qt.AlignCenter, "T")
    return _icon(draw)


class _GlassPopups(QObject):
    """液态玻璃：让所有弹出来的菜单和下拉列表都是圆角毛玻璃，不用在每个创建它们的地方各写一遍。

    装在整个应用上的事件过滤器，只做两件事：
      * 菜单 / 下拉框第一次要用之前（Polish 事件，这时弹出窗口还没真正创建），把弹出窗口设成背景透明；
      * 弹出窗口每次显示时（Show 事件），让系统给它铺毛玻璃、切圆角。
    """

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.Polish:
            if isinstance(obj, QMenu):
                theme.prepare_popup(obj)
            elif isinstance(obj, QComboBox) and not obj.property("ruiGlassReady"):
                obj.setProperty("ruiGlassReady", True)
                theme.prepare_popup(obj.view().window())  # 下拉列表其实是装在一个单独的小窗口里的
                if not isinstance(obj, QFontComboBox):  # 字体下拉框有自己的画法（每项用那种字体写），不换
                    obj.setItemDelegate(QStyledItemDelegate(obj))  # 换成认样式表的画法，列表项才有圆角高亮
        elif t == QEvent.Type.Show and obj.isWidgetType() and obj.isWindow() and obj.property("ruiGlass"):
            (winglass.enable_popup if theme.glass_enabled else winglass.disable_popup)(int(obj.winId()))
        return False


# ---------------------------------------------------------------------- 标签页
class DocTab(QWidget):
    """一个打开的 PDF：画布 + 滚动条 + 各自的保存状态。"""

    def __init__(self):
        super().__init__()
        self.canvas = Canvas()
        self.vbar = QScrollBar(Qt.Vertical)
        self.dirty = False
        self.backup_stale = False  # 有改动还没写进自动备份
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.canvas, 1)
        lay.addWidget(self.vbar)
        self.vbar.valueChanged.connect(self.canvas.scroll_to)
        round_corners(self)  # 页面区四个角切圆，和工具栏的胶囊一个风格

    def paintEvent(self, _ev):
        # 滚动条那一竖条也涂成页面周围的底色，这样画布和滚动条合起来是一整块圆角卡片
        # （不涂的话滚动条后面是窗口的底色，卡片的右边两个角就成了方的）
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.canvas_bg()))
        p.end()
        self.canvas.scrollRangeChanged.connect(self._sync_bar)

    def _sync_bar(self, maximum, page_step, value):
        self.vbar.blockSignals(True)
        self.vbar.setRange(0, maximum)
        self.vbar.setPageStep(page_step)
        self.vbar.setSingleStep(60)
        self.vbar.setValue(value)
        self.vbar.blockSignals(False)

    @property
    def doc(self):
        return self.canvas.doc


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RuiPDF")
        self.setWindowIcon(app_icon())
        self.resize(1360, 900)
        self.setAcceptDrops(True)
        self.settings = app_settings()
        # 液态玻璃效果：窗口背景透明 + 系统毛玻璃（见 winglass.py）+ 半透明的工具栏样式。
        # 背景透明必须在窗口创建之前定下来（运行中切换会留下重影）。所以只要机器支持，窗口一律建成背景透明的；
        # 开关只是换样式表、铺上 / 撤掉毛玻璃——关着的时候样式表把窗口涂成不透明的，看起来和普通窗口一样。
        # 工具和笔设置两条工具栏放在哪：浮在画布的上 / 下 / 左 / 右，或者像原来那样固定在窗口顶部
        self.toolbar_pos = self.settings.value("toolbar_pos", "top")
        if self.toolbar_pos not in dict(TOOLBAR_POSITIONS):
            self.toolbar_pos = "top"
        self.ui_font_key = self.settings.value("ui_font", UI_FONT_DEFAULT)
        if self.ui_font_key not in UI_FONTS:
            self.ui_font_key = UI_FONT_DEFAULT
        apply_ui_font(self.ui_font_key)
        # 界面风格（theme.THEMES）。以前只有"液态玻璃效果"一个开关（设置键 glass），没选过风格时按它来定
        theme.glass_capable = winglass.available()
        key = self.settings.value("theme", "")
        if key not in theme.THEMES:
            key = "glass" if self.settings.value("glass", "true") == "true" else "light"
        if key == "glass" and not theme.glass_capable:
            key = "light"
        self.theme_key = theme.current = key
        self.glass_on = theme.glass_enabled = key == "glass"
        QApplication.instance().setPalette(theme.palette())
        self._was_maximized = False  # 进全屏之前是不是最大化的（退出全屏时恢复）
        try:
            self.toolbar_opacity = int(self.settings.value("toolbar_opacity", 100))
        except (TypeError, ValueError):
            self.toolbar_opacity = 100
        if theme.glass_capable:
            self.setAttribute(Qt.WA_TranslucentBackground)
            self._glass_popups = _GlassPopups(self)  # 菜单、下拉列表也做成玻璃的
            QApplication.instance().installEventFilter(self._glass_popups)
        self.setStyleSheet(theme.stylesheet())
        self._feedback_off = False
        self._dock_hwnd = 0  # 正贴在右边跟随本窗口的对话窗口句柄，0 表示没有
        self.dock_target = self.settings.value("dock_target", "claude")
        self.dock_side = self.settings.value("dock_side", "right")  # 对话窗口贴在本窗口的哪一边
        if self.dock_side not in dict(DOCK_SIDES):
            self.dock_side = "right"
        self._dock_min = 0  # 量到的对方窗口的最小宽度（物理像素），贴左边时要按它来对齐
        if self.dock_target not in dict(DOCK_TARGETS):
            self.dock_target = "claude"
        self.dock_w = int(max(DOCK_W_RANGE[0], min(DOCK_W_RANGE[1], self._setting_float("dock_w", DOCK_W_DEFAULT))))
        self.dock_h = int(max(DOCK_H_RANGE[0], min(DOCK_H_RANGE[1], self._setting_float("dock_h", DOCK_H_DEFAULT))))
        self._load_paste_style()
        # 工具状态是全局的，所有标签页共用
        self.tool = "pen"
        self.shape = "line"
        self.palette_name = self.settings.value("palette", "经典")
        self.pen_colors, self.hl_colors = self._palette(self.palette_name)
        self.color_idx, self.hl_idx = 3, 0
        self.color, self.hl_color = self.pen_colors[3], self.hl_colors[0]
        self.widths = {"pen": WIDTHS[1][1], "hl": WIDTHS[1][2], "text": WIDTHS[1][3]}
        for k in self.widths:
            try:
                self.widths[k] = float(self.settings.value("width/" + k, self.widths[k]))
            except (TypeError, ValueError):
                pass
        self.quality = float(max(1, min(3, round(self._setting_float("quality", 2.0)))))
        self.smoothing = self._setting_float("smoothing", 0.35)
        self.claude_mode = self.settings.value("claude_mode", "app")
        self.pen_style = self.settings.value("pen_style", "f")
        self.width_mode = self.settings.value("width_mode", "page")
        self.cursor_style = self.settings.value("cursor_style", "dot")

        # 两栏标签页：平时只用左栏；"分屏"把标签移到右栏，两个 PDF 并排显示
        self.panes = []
        for _ in range(2):
            tw = QTabWidget()
            tw.setDocumentMode(True)
            tw.setTabsClosable(True)
            tw.setMovable(True)
            tw.tabBar().setDrawBase(False)  # 不要系统样式在标签栏边上画的那条细线（玻璃背景上很显眼）
            tw.tabCloseRequested.connect(lambda i, tw=tw: self.close_tab(tw.widget(i)))
            tw.currentChanged.connect(lambda _i, tw=tw: self._pane_current_changed(tw))
            self.panes.append(tw)
        self.tabs = self.panes[0]
        self.active = self.tabs  # 当前栏：工具栏、快捷键、侧栏都针对它的当前标签
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.panes[0])
        self.splitter.addWidget(self.panes[1])
        self.splitter.setChildrenCollapsible(False)
        self.panes[1].hide()
        self._find_hits = []  # 搜索结果 [(页号, QRectF)]
        self._find_i = -1
        self._find_text = ""
        hint = QLabel(T("新建笔记（Ctrl+N），打开 PDF（Ctrl+O），或把文件拖进来"))
        hint.setAlignment(Qt.AlignCenter)
        self.hint = hint
        self._style_hint()
        self.stack = QStackedWidget()
        self.stack.addWidget(hint)
        self.stack.addWidget(self.splitter)
        self.setCentralWidget(self.stack)
        round_corners(hint)
        self.setContentsMargins(7, 0, 7, 6)  # 页面区、侧栏、状态栏四周留一圈缝，圆角才看得出来
        self.stack.setContentsMargins(0, 0, 0, 6)  # 页面区和下面的状态栏之间也留一条缝

        self.sidebar = Sidebar()
        self.dock = QDockWidget(T("侧栏"), self)
        # 侧栏外面套一层，下面留 6 px：和页面区一样在状态栏上方留一条缝，两边的下沿对齐
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.addWidget(self.sidebar)
        self.dock.setWidget(box)
        self.dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        round_corners(self.dock, (0, 1))      # 上面两个角在标题那里
        round_corners(self.sidebar, (2, 3))   # 下面两个角在内容的底边（再往下是留的缝）
        self.dock.setVisible(self.settings.value("sidebar", "false") == "true")

        self._build_top_bar()
        # 顶部这几条（文件 | 更多 | 视图）放在自己的容器里，不交给主窗口的工具栏区：
        # 在工具栏区里，放不下的按钮点 » 时 Qt 会把整条工具栏往下撑开，盖住下面一行（窄窗口时出过重叠）；
        # 不在工具栏区里的工具栏，放不下的按钮是列在一个弹出的小菜单里，不会盖住别的东西。
        self.topbar = QWidget()
        col = QVBoxLayout(self.topbar)
        col.setContentsMargins(0, 0, 0, 5)  # 和下面的页面区、侧栏之间留一条缝
        col.setSpacing(0)
        self._top_row1, self._top_row2 = QHBoxLayout(), QHBoxLayout()
        for row in (self._top_row1, self._top_row2):
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)  # 胶囊之间的缝；两端不留，和下面的页面区、侧栏的边对齐
            col.addLayout(row)
        self._top_row1.addWidget(self.tb_file)
        self._top_row1.addWidget(self.tb_more)
        self._top_row1.addWidget(self.tb_view, 1)
        self.setMenuWidget(self.topbar)
        self._build_tool_bar()
        self._build_status_bar()
        self._build_find_bar()
        self.floatbar = FloatBar(self.stack, self.tb_tools, self.tb_settings, self.act_flyout, self)
        for k in ("h", "v", "t"):
            try:
                self.floatbar.length[k] = max(0, int(self.settings.value("toolbar_len_" + k, 0)))
            except (TypeError, ValueError):
                pass
        self.floatbar.set_opacity(self.toolbar_opacity)
        self._float_timer = QTimer(self)  # 一连串变化（改大小、切标签…）只在最后重新摆一次
        self._float_timer.setSingleShot(True)
        self._float_timer.timeout.connect(self._place_floatbar_now)
        self.stack.installEventFilter(self)
        self.splitter.splitterMoved.connect(lambda *_: self.place_floatbar())
        self._apply_toolbar_pos(self.toolbar_pos)
        self.sidebar.searchRequested.connect(self._sidebar_search)
        self.sidebar.hitActivated.connect(self._goto_hit)
        self.sidebar.ai.pasteRequested.connect(lambda text: self.canvas and self.canvas.add_text_block(text))

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._autosave)
        self.timer.start(AUTOSAVE_MS)

    # ------------------------------------------------------------------ 当前标签页
    def _setting_float(self, key, default):
        try:
            return float(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def tab(self) -> DocTab:
        return self.active.currentWidget() or self.panes[0].currentWidget() or self.panes[1].currentWidget()

    def _pane_of(self, t):
        for pane in self.panes:
            if pane.indexOf(t) >= 0:
                return pane
        return None

    @property
    def canvas(self) -> Canvas:
        t = self.tab()
        return t.canvas if t else None

    @property
    def dirty(self) -> bool:
        t = self.tab()
        return bool(t and t.dirty)

    def _all_tabs(self):
        return [pane.widget(i) for pane in self.panes for i in range(pane.count())]

    def _with_canvas(self, fn):
        """把动作包装成"对当前画布执行"。"""
        def run(*_):
            c = self.canvas
            if c:
                fn(c)
        return run

    # ------------------------------------------------------------------ 界面
    def _act(self, text, slot, shortcut=None, tip=None, icon=None, checkable=False):
        a = QAction(text, self)
        if icon:
            a.setIcon(icon)
        if shortcut:
            a.setShortcuts([QKeySequence(s) for s in ([shortcut] if isinstance(shortcut, str) else shortcut)])
        first = shortcut if isinstance(shortcut, str) else (shortcut[0] if shortcut else None)
        a.setToolTip(f"{tip or text}  ({first})" if first else (tip or text))
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        self.addAction(a)
        return a

    def _menu_button(self, tb, text, menu):
        """工具栏上点一下弹出菜单的按钮。做成带菜单的普通动作（不是塞进去的控件）：窗口太窄、它被收进
        右端的 » 里时，Qt 能把它列在弹出的小菜单里；塞控件的话 Qt 会把整条工具栏往下撑开盖住别的东西。"""
        act = QAction(text + " ▾", self)
        act.setMenu(menu)
        tb.addAction(act)
        btn = tb.widgetForAction(act)
        btn.setPopupMode(QToolButton.InstantPopup)
        return btn

    def _build_top_bar(self):
        tb = QToolBar(T("文件"))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        # 新建 / 打开 / 保存 / 另存为收在"文件"一个按钮下面（用户要求，省地方）；快捷键照旧
        file_menu = QMenu(self)
        file_menu.addAction(self._act(T("新建"), self.new_note, "Ctrl+N", tip=T("新建笔记：选一种模板纸，生成一个新的 PDF")))
        file_menu.addAction(self._act(T("打开"), self.open_dialog, "Ctrl+O"))
        file_menu.addAction(self._act(T("保存"), lambda: self.save(), "Ctrl+S"))
        file_menu.addAction(self._act(T("另存为"), self.save_as, "Ctrl+Shift+S"))
        self._menu_button(tb, T("文件"), file_menu)
        self._act(T("关闭标签页"), lambda: self.close_tab(self.tab()), "Ctrl+W")
        self._act(T("查找"), self.show_find, "Ctrl+F")
        self._act(T("查找下一个"), lambda: self.find_step(1), "F3")
        self._act(T("查找上一个"), lambda: self.find_step(-1), "Shift+F3")
        self._act(T("下一个标签页"), lambda: self._cycle_tab(1), "Ctrl+Tab")
        self._act(T("上一个标签页"), lambda: self._cycle_tab(-1), "Ctrl+Shift+Tab")
        tb.addSeparator()
        self.act_undo = self._act(T("撤销"), self._with_canvas(lambda c: c.undo()), "Ctrl+Z")
        self.act_redo = self._act(T("重做"), self._with_canvas(lambda c: c.redo()), ["Ctrl+Y", "Ctrl+Shift+Z"])
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()
        tb.addAction(self._act(T("缩小"), self._with_canvas(lambda c: c.set_zoom(c.zoom / 1.15)), "Ctrl+-"))
        tb.addAction(self._act(T("放大"), self._with_canvas(lambda c: c.set_zoom(c.zoom * 1.15)), ["Ctrl+=", "Ctrl++"]))
        tb.addAction(self._act(T("适合宽度"), self._with_canvas(lambda c: c.fit_width()), "Ctrl+0"))
        tb.addSeparator()

        page_menu = QMenu(self)
        page_menu.addAction(self._act(T("在当前页后插入空白页"), self._with_canvas(lambda c: c.insert_blank_after()), "Ctrl+Shift+N"))
        tpl_menu = page_menu.addMenu(T("插入模板页"))
        for key, name in TEMPLATES:
            a = tpl_menu.addAction(name)
            a.triggered.connect(lambda _=False, k=key: self.canvas and self.canvas.insert_blank_after(None, k))
        page_menu.addAction(self._act(T("插入图片…"), self.insert_image_dialog, "Ctrl+Shift+I"))
        # 快捷键 Ctrl+V 由画布自己处理（这样在页面上打字时 Ctrl+V 是往输入框里粘贴），这里只是给鼠标一个入口
        page_menu.addAction(T("粘贴剪贴板里的内容（Ctrl+V）")).triggered.connect(
            lambda _=False: self.canvas and self.canvas.paste())
        page_menu.addAction(self._act(T("当前页右侧加留白"), self._with_canvas(lambda c: c.add_margin("right")), "Ctrl+Shift+R"))
        page_menu.addAction(self._act(T("当前页底部加留白"), self._with_canvas(lambda c: c.add_margin("bottom")), "Ctrl+Shift+B"))
        page_menu.addAction(self._act(T("调整当前页的留白…"), self.edit_margins,
                                      tip=T("自己定右侧 / 底部留白的宽度，或把加过的留白改小、去掉")))
        page_menu.addAction(self._act(T("去掉当前页的留白"), lambda: self.edit_margins(remove=True)))
        page_menu.addSeparator()
        page_menu.addAction(self._act(T("删除当前空白页"), self.delete_blank_page))
        page_menu.addSeparator()
        page_menu.addAction(self._act(T("给当前页加书签"), lambda: self.sidebar.add_bookmark(), "Ctrl+D"))
        page_menu.addSeparator()
        page_menu.addAction(self._act(T("导出有标注的页…"), self.export_annotated))
        self._menu_button(tb, T("页面"), page_menu)

        review = QMenu(self)
        review.addAction(self._act(T("全部遮住"), self._with_canvas(lambda c: c.set_masks_shown(False)), "Ctrl+H"))
        review.addAction(self._act(T("全部揭开"), self._with_canvas(lambda c: c.set_masks_shown(True)), "Ctrl+Shift+H"))
        self._menu_button(tb, T("复习"), review)

        # 第一行的后半段单独一条：窗口不够宽时整条换到下一行（见 _reflow_toolbars），
        # 否则 Qt 会把放不下的按钮收进右端的 » 里
        self.tb_file = tb
        # 窗口窄、后半段放不下时，后半段先收起来，这一行右端出现"更多"按钮，点它展开 / 收起（见 _reflow_toolbars）。
        # 它单独占一条小工具栏：放在前半段里的话，窗口再窄一点它自己就会被 Qt 收进"…"里点不到
        tb = QToolBar(T("更多"))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.act_more = self._act(T("更多") + " ▾", self._toggle_more,
                                  tip=T("展开 / 收起其余的按钮（问 Claude、分屏、设置等）"), checkable=True)
        tb.addAction(self.act_more)
        tb.hide()
        self.tb_more = tb
        tb = QToolBar(T("视图"))
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.tb_view = tb
        self._view_wrapped = False
        self._view_sep = tb.addSeparator()  # 两段并排时的分隔线，换行后隐藏
        self.act_ask = self._act(T("问 Claude"), self.ask_claude, "Ctrl+K")
        tb.addAction(self.act_ask)
        self.act_dock = self._act(T("Claude 分屏"), self.tile_with_claude, "Ctrl+Shift+K",
                                  tip=T("把对话窗口（Claude / ChatGPT / Chrome，在“设置”里选对象和大小）"
                                        "贴在本窗口右边，并跟着本窗口移动和缩放；再点一次取消"))
        self.act_dock.setCheckable(True)
        self._retitle_ai()
        tb.addAction(self.act_dock)
        tb.addAction(self._act(T("分屏"), self.move_to_other_pane, "Ctrl+\\",
                               tip=T("把当前标签移到另一栏，两个 PDF 并排显示；再按一次移回来")))
        tb.addAction(self._act(T("侧栏"), self._toggle_sidebar, "F9", tip=T("缩略图 / 目录 / 书签 / 标注汇总")))
        tb.addAction(self._act(T("全屏"), self._toggle_fullscreen, "F11"))
        tb.addSeparator()

        menu = QMenu(self)

        def choice_menu(title, items, current, slot, icon_for=None):
            sub = menu.addMenu(title)
            group = QActionGroup(sub)
            actions = {}
            for key, name in items:
                a = sub.addAction(name)
                if icon_for:
                    a.setIcon(icon_for(key))
                a.setCheckable(True)
                a.setChecked(key == current)
                a.triggered.connect(lambda _=False, k=key: slot(k))
                group.addAction(a)
                actions[key] = a
            return actions

        choice_menu(T("书写分辨率"), QUALITIES, self.quality, self._pick_quality)
        choice_menu(T("笔迹平滑"), SMOOTHINGS, self.smoothing, self._pick_smoothing)
        choice_menu(T("光标样式"), Canvas.CURSOR_STYLES, self.cursor_style, self._pick_cursor, _cursor_icon)
        choice_menu(T("“问 Claude”发到哪里"), CLAUDE_MODES, self.claude_mode, self._pick_claude_mode)
        choice_menu(T("贴靠 / 粘贴的对象"), DOCK_TARGETS, self.dock_target, self._pick_dock_target)
        choice_menu(T("贴靠在哪一边"), DOCK_SIDES, self.dock_side, self._pick_dock_side)
        menu.addAction(T("贴靠窗口的大小…")).triggered.connect(lambda _=False: self._edit_dock_size())
        menu.addAction(T("粘贴内容的字体和大小…")).triggered.connect(lambda _=False: self._edit_paste_style())
        menu.addSeparator()
        self._theme_actions = choice_menu(T("界面风格"), [(k, T(v[0])) for k, v in theme.THEMES.items()],
                                          self.theme_key, self._pick_theme)
        self._theme_actions["glass"].setEnabled(theme.glass_capable)  # 液态玻璃需要 Windows 11
        choice_menu(T("界面字体"), [(k, T(v[0])) for k, v in UI_FONTS.items()], self.ui_font_key, self._pick_ui_font)
        self._pos_actions = choice_menu(T("工具栏位置"), TOOLBAR_POSITIONS, self.toolbar_pos, self._pick_toolbar_pos)
        menu.addAction(T("悬浮工具栏的不透明度…")).triggered.connect(lambda _=False: self._edit_toolbar_opacity())
        choice_menu("语言 / Language", LANGUAGES, i18n.LANG, self._pick_language)
        self._menu_button(tb, T("设置"), menu)
        tb.addAction(self._act(T("关于"), self.show_about))

        # ---- 笔的设置：接在第二行工具条的后面（见 _build_tool_bar）----
        tb2 = QToolBar(T("笔设置"))
        tb2.setMovable(False)
        self.tb_settings = tb2

        def combo(items, current, slot, tip):
            cb = QComboBox()
            cb.setFocusPolicy(Qt.NoFocus)  # 不抢键盘焦点，单键快捷键才能一直可用
            cb.setToolTip(tip)
            for key, name in items:
                cb.addItem(name, key)
            cb.setCurrentIndex(max(0, cb.findData(current)))
            cb.activated.connect(lambda _i, cb=cb: slot(cb.currentData()))
            return cb

        tb2.addWidget(combo(PEN_STYLES, self.pen_style, self._pick_pen_style, T("笔触风格（只影响之后写的笔画）")))
        tb2.addSeparator()
        self.lbl_width = QLabel(T("  粗细 "))
        tb2.addWidget(self.lbl_width)
        self.sld = QSlider(Qt.Horizontal)
        self.sld.setFixedWidth(110)
        self.sld.setFocusPolicy(Qt.NoFocus)
        self.spin = QDoubleSpinBox()
        self.spin.setSuffix(" pt")
        self.spin.setFocusPolicy(Qt.ClickFocus)
        self.spin.setKeyboardTracking(False)
        self.sld.valueChanged.connect(lambda v: self._on_width_edit(v / 10))
        self.spin.valueChanged.connect(self._on_width_edit)
        self.spin.editingFinished.connect(lambda: self.canvas and self.canvas.setFocus())
        tb2.addWidget(self.sld)
        tb2.addWidget(self.spin)
        tb2.addWidget(QLabel(" "))
        tb2.addWidget(combo(WIDTH_MODES, self.width_mode, self._pick_width_mode,
                            T("粗细随页面：线按页面算，放大后看起来也变粗，写出来始终一样粗\n"
                            "粗细随屏幕：放大后笔看起来不变粗，实际画出的线更细，适合放大写小字")))
        tb2.addSeparator()
        self.cb_palette = combo([(n, T(n)) for n in list(PALETTES) + [CUSTOM]], self.palette_name,
                                self._pick_palette, T("配色方案：一次换掉左侧 4 个笔色和 3 个荧光色"))
        tb2.addWidget(self.cb_palette)
        btn = QPushButton(T("调色盘…"))
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setToolTip(T("自选颜色，替换左侧当前选中的那个色块（当前是荧光笔时替换荧光色）"))
        btn.clicked.connect(self._open_color_dialog)
        tb2.addWidget(btn)

    def _build_tool_bar(self):
        # 第二行：工具条（工具 | 笔色 | 荧光色 | 粗细预设），后面接笔的设置
        tb = QToolBar(T("工具"))
        tb.setMovable(False)
        tb.setIconSize(QSize(26, 26))
        tb.setObjectName("strip")
        self.tb_tools = tb
        self.addToolBarBreak(Qt.TopToolBarArea)
        self.addToolBar(Qt.TopToolBarArea, tb)
        self.addToolBar(Qt.TopToolBarArea, self.tb_settings)
        self._settings_wrapped = False

        tools = QActionGroup(self)
        self.act_pen = self._act(T("笔"), lambda: self._pick_tool("pen"), "P", icon=_pen_icon(), checkable=True)
        self.act_hl = self._act(T("荧光笔"), lambda: self._pick_tool("hl"), "H", icon=_hl_icon(), checkable=True)
        self.act_eraser = self._act(T("橡皮"), lambda: self._pick_tool("eraser"), "E",
                                    tip=T("橡皮（整个对象擦除；按住笔侧键可临时使用）"),
                                    icon=_eraser_icon(), checkable=True)
        self.act_lasso = self._act(T("套索"), lambda: self._pick_tool("lasso"), "L",
                                   tip=T("套索选择：圈住后可拖动、拉右下角缩放、点颜色改色；右键有复制 / 剪切 / 粘贴 / 删除"),
                                   icon=_lasso_icon(), checkable=True)
        self.act_shape = self._act(T("形状"), lambda: self._pick_tool(self.shape), "S",
                                   tip=T("形状（点右侧小箭头换种类）"), icon=_shape_icon(self.shape), checkable=True)
        self.act_text = self._act(T("文本"), lambda: self._pick_tool("text"), "T",
                                  tip=T("文本框：点空白处新建，点已有文字修改"), icon=_text_icon(), checkable=True)
        self.act_mask = self._act(T("遮挡"), lambda: self._pick_tool("mask"), "M",
                                  tip=T("遮挡块：拖出一块盖住答案；点一下揭开，用本工具再点一下重新遮住"),
                                  icon=_mask_icon(), checkable=True)
        self.act_select = self._act(T("选字"), lambda: self._pick_tool("select"), "V",
                                    tip=T("选择文字：在 PDF 自带的文字上拖过去选中，Ctrl+C 复制成文本；"
                                          "点“问”把选中的文字粘贴到对话窗口。扫描件没有文字可选"),
                                    icon=_select_icon(), checkable=True)
        for a in (self.act_pen, self.act_hl, self.act_eraser, self.act_lasso, self.act_select, self.act_shape,
                  self.act_text, self.act_mask):
            tools.addAction(a)
            tb.addAction(a)
        self.act_pen.setChecked(True)
        shape_menu = QMenu(self)
        self._shape_menu_actions = []
        for kind, name in SHAPE_NAMES:
            a = shape_menu.addAction(_shape_icon(kind), name)
            a.triggered.connect(lambda _=False, k=kind: self._pick_shape(k))
            self._shape_menu_actions.append((a, kind))
        btn = tb.widgetForAction(self.act_shape)
        btn.setMenu(shape_menu)
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        tb.addSeparator()

        colors = QActionGroup(self)
        self.color_actions = []
        for n, hexcol in enumerate(self.pen_colors):
            a = self._act(T("笔色 {}").format(n + 1), lambda _=False, i=n: self._pick_color_idx(i), str(n + 1),
                          icon=_color_icon(hexcol), checkable=True)
            colors.addAction(a)
            tb.addAction(a)
            tb.widgetForAction(a).setObjectName("swatch")
            a.setChecked(n == self.color_idx)
            self.color_actions.append(a)
        tb.addSeparator()

        hl_colors = QActionGroup(self)
        self.hl_actions = []
        for n, hexcol in enumerate(self.hl_colors):
            a = self._act(T("荧光色 {}").format(n + 1), lambda _=False, i=n: self._pick_hl_idx(i), str(n + 5),
                          icon=_color_icon(hexcol, square=True), checkable=True)
            hl_colors.addAction(a)
            tb.addAction(a)
            tb.widgetForAction(a).setObjectName("swatch")
            a.setChecked(n == self.hl_idx)
            self.hl_actions.append(a)
        tb.addSeparator()

        widths = QActionGroup(self)
        widths.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self.width_actions = []
        for key, preset in zip("QWR", WIDTHS):
            a = self._act(preset[0], lambda _=False, p=preset: self._pick_width(p), key,
                          tip=T("{}（预设：笔、荧光笔、文本字号一起变）").format(preset[0]),
                          icon=_width_icon(preset[1]), checkable=True)
            widths.addAction(a)
            tb.addAction(a)
            a.setChecked(all(abs(self.widths[k] - v) < 1e-6 for k, v in zip(("pen", "hl", "text"), preset[1:])))
            self.width_actions.append(a)
        self._sync_width_controls()
        # 工具条悬浮在左 / 右侧时是竖排的，笔设置那一条放不下，收在旁边的小面板里，用这个按钮展开 / 收起
        self.act_flyout = self._act(T("笔设置"), lambda: None, tip=T("展开 / 收起笔的设置（笔触、粗细、配色）"),
                                    icon=_sliders_icon(), checkable=True)

    def _build_status_bar(self):
        sb = self.statusBar()
        self.lbl_page, self.lbl_zoom, self.lbl_pen = QLabel(""), QLabel(""), QLabel("")
        sb.addWidget(self.lbl_page)
        sb.addWidget(self.lbl_zoom)
        sb.addPermanentWidget(self.lbl_pen)

    def _build_find_bar(self):
        """查找框：放在文档标签那一行的右端（用户要求，原来是顶部工具栏上的一个按钮 + 窗口底部的一条）。
        一直显示着：输入后回车 = 下一处，Shift+回车 = 上一处，Esc = 清掉。"""
        bar = QWidget()
        bar.setObjectName("findBox")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 4, 3)
        lay.setSpacing(2)
        self.find_label = QLabel("")
        lay.addWidget(self.find_label)
        self.find_edit = QLineEdit()
        self.find_edit.setFixedWidth(190)
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.setPlaceholderText(T("查找（Ctrl+F）"))
        self.find_edit.setToolTip(T("搜索 PDF 里的文字：回车 = 下一处，Shift+回车 = 上一处，Esc = 清掉"))
        self.find_edit.returnPressed.connect(
            lambda: self.find_step(-1 if QApplication.keyboardModifiers() & Qt.ShiftModifier else 1))
        self.find_edit.textChanged.connect(lambda text: text or self._clear_find())  # 点了清除按钮：高亮也去掉
        lay.addWidget(self.find_edit)
        for text, tip, slot in (("‹", T("上一个"), lambda: self.find_step(-1)), ("›", T("下一个"), lambda: self.find_step(1)),
                                ("☰", T("在侧栏里列出全部搜索结果，点一条跳过去"), self.show_search_list)):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _=False, f=slot: f())
            lay.addWidget(b)
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self.find_edit)
        esc.setContext(Qt.WidgetShortcut)
        esc.activated.connect(self.hide_find)
        self.panes[0].setCornerWidget(bar, Qt.TopRightCorner)
        self.find_bar = bar

    # ------------------------------------------------------------------ 查找
    def show_find(self):
        self.find_edit.setFocus()
        self.find_edit.selectAll()

    def hide_find(self):
        """清掉这次查找（查找框本身一直在）。"""
        self.find_edit.blockSignals(True)
        self.find_edit.clear()
        self.find_edit.blockSignals(False)
        self._clear_find()
        if self.canvas:
            self.canvas.setFocus()

    def show_search_list(self):
        """打开侧栏的搜索页（全部结果的列表）。"""
        self.dock.setVisible(True)
        self.sidebar.show_search()

    def _sidebar_search(self, text: str):
        """侧栏搜索页里按了回车：和查找栏共用同一份结果。"""
        self.find_edit.setText(text)
        self._find_text = ""  # 同一个词再按回车也重新搜一遍
        if text:
            self.find_step(1)
        else:
            self._clear_find()

    def _goto_hit(self, i: int):
        """跳到第 i 处搜索结果（点了侧栏结果列表里的一条）。"""
        if 0 <= i < len(self._find_hits) and self.find_edit.text().strip() == self._find_text:
            self._find_i = i - 1
            self.find_step(1)

    def _clear_find(self):
        self._find_hits, self._find_i, self._find_text = [], -1, ""
        self.find_label.setText("")
        self.sidebar.set_search_results("", [])
        for t in self._all_tabs():
            if t.canvas.hits:
                t.canvas.set_hits({})

    def find_step(self, step):
        c = self.canvas
        text = self.find_edit.text().strip()
        if not c or not text:
            return
        if text != self._find_text:  # 新的搜索词：重新搜
            self._find_text = text
            found = c.doc.search_with_context(text)
            self._find_hits = [(page, QRectF(x0, y0, x1 - x0, y1 - y0)) for page, (x0, y0, x1, y1), _line in found]
            self.sidebar.set_search_results(text, [(page, line) for page, _rect, line in found])
            cur = c.current_page()  # 从当前页开始往后找第一条
            self._find_i = next((i for i, (page, _) in enumerate(self._find_hits) if page >= cur), 0) - step
        if not self._find_hits:
            self.find_label.setText(T("  没有找到  "))
            c.set_hits({})
            return
        self._find_i = (self._find_i + step) % len(self._find_hits)
        by_page = {}
        for page, rect in self._find_hits:
            by_page.setdefault(page, []).append(rect)
        c.set_hits(by_page, self._find_hits[self._find_i])
        self.find_label.setText(T("  第 {} / {} 处  ").format(self._find_i + 1, len(self._find_hits)))
        self.sidebar.select_hit(self._find_i)

    # ------------------------------------------------------------------ 分屏
    def _pane_current_changed(self, pane):
        if pane.count():
            self.active = pane
        self._tab_changed()

    def _activate(self, t):
        """某个画布拿到了焦点：它所在的栏成为当前栏。"""
        pane = self._pane_of(t)
        if pane is not None and pane is not self.active:
            self.active = pane
            self._tab_changed()

    def _move_tab(self, t, dst):
        src = self._pane_of(t)
        i = src.indexOf(t)
        text, tip = src.tabText(i), src.tabToolTip(i)
        for pane in self.panes:
            pane.blockSignals(True)
        src.removeTab(i)
        j = dst.addTab(t, text)
        dst.setTabToolTip(j, tip)
        dst.setCurrentIndex(j)
        for pane in self.panes:
            pane.blockSignals(False)

    def move_to_other_pane(self):
        t = self.tab()
        if not t:
            return
        if len(self._all_tabs()) < 2:
            QMessageBox.information(self, T("分屏"), T("分屏需要至少打开两个 PDF。"))
            return
        src = self._pane_of(t)
        dst = self.panes[1] if src is self.panes[0] else self.panes[0]
        self._move_tab(t, dst)
        self.active = dst
        self._tab_changed()
        if self.panes[1].isVisible():
            half = self.splitter.width() // 2
            self.splitter.setSizes([half, half])
        QTimer.singleShot(0, self._refit_visible)

    def _refit_visible(self):
        """分屏 / 合并后栏宽变了，让两栏当前的页面重新适合宽度。"""
        for pane in self.panes:
            t = pane.currentWidget()
            if t and pane.isVisible():
                t.canvas.fit_width()

    # ------------------------------------------------------------------ 工具状态
    def _apply_tools(self, c: Canvas):
        c.ask_label = self.act_ask.text()
        c.set_cursor_style(self.cursor_style)
        c.color, c.hl_color = self.color, self.hl_color  # 直接赋值：不触发"给选区改色"
        c.set_width(self.widths["pen"], self.widths["hl"], self.widths["text"])
        c.set_pen_style(self.pen_style)
        c.set_width_mode(self.width_mode)
        c.set_quality(self.quality)
        c.set_smoothing(self.smoothing)
        c.set_tool(self.tool)

    def _pick_tool(self, tool):
        self.tool = tool
        for t in self._all_tabs():
            t.canvas.set_tool(tool)
        self._sync_width_controls()

    def _pick_shape(self, kind):
        self.shape = kind
        self.act_shape.setIcon(_shape_icon(kind))
        self.act_shape.trigger()

    def _pick_color(self, c):
        if self.canvas and self.canvas.editing_text():
            self.canvas.set_color(c)  # 正在页面上输入文字：只给输入框里选中的字改色，不换工具也不改默认颜色
            return
        self.color = c
        for t in self._all_tabs():
            t.canvas.color = c
        cv = self.canvas
        if cv:
            cv.set_color(c)  # 有选区时同时给选区改色
            if cv.has_selection():
                return
        if self.tool in ("hl", "eraser", "lasso", "select"):
            self.act_pen.trigger()  # 选颜色时自动切回笔（形状、文本工具保持不变）

    def _pick_hl_color(self, c):
        self.hl_color = c
        for t in self._all_tabs():
            t.canvas.hl_color = c
        cv = self.canvas
        if cv:
            cv.set_hl_color(c)
            if cv.has_selection():
                return
        self.act_hl.trigger()  # 选荧光色时自动切到荧光笔

    def _pick_color_idx(self, i):
        self.color_idx = i
        self._pick_color(self.pen_colors[i])

    def _pick_hl_idx(self, i):
        self.hl_idx = i
        self._pick_hl_color(self.hl_colors[i])

    # ---- 粗细 ----
    def _width_target(self) -> str:
        """滑块当前调的是哪一项：荧光笔宽、文本字号，其余工具都是笔的粗细。"""
        return self.tool if self.tool in ("hl", "text") else "pen"

    def _apply_widths(self):
        for t in self._all_tabs():
            t.canvas.set_width(self.widths["pen"], self.widths["hl"], self.widths["text"])
        for k, v in self.widths.items():
            self.settings.setValue("width/" + k, v)

    def _sync_width_controls(self):
        """让滑块和数字框显示当前工具对应的那一项。"""
        target = self._width_target()
        lo, hi, step, label = WIDTH_RANGES[target]
        v = max(lo, min(hi, self.widths[target]))
        self.lbl_width.setText(f"  {label} ")
        for wdg in (self.sld, self.spin):
            wdg.blockSignals(True)
        self.sld.setRange(round(lo * 10), round(hi * 10))
        self.sld.setSingleStep(round(step * 10))
        self.sld.setPageStep(round(step * 50))
        self.sld.setValue(round(v * 10))
        self.spin.setRange(lo, hi)
        self.spin.setSingleStep(step)
        self.spin.setDecimals(1)
        self.spin.setValue(v)
        for wdg in (self.sld, self.spin):
            wdg.blockSignals(False)

    def _on_width_edit(self, value):
        """滑块或数字框改了粗细（自定义值）。"""
        self.widths[self._width_target()] = round(float(value), 1)
        for a in self.width_actions:  # 自定义值不属于任何预设
            a.setChecked(False)
        self._apply_widths()
        self._sync_width_controls()

    def _pick_width(self, preset):
        self.widths = {"pen": preset[1], "hl": preset[2], "text": preset[3]}
        for a, p in zip(self.width_actions, WIDTHS):
            a.setChecked(p is preset)
        self._apply_widths()
        self._sync_width_controls()
        if self.tool == "eraser":
            self.act_pen.trigger()

    def _pick_pen_style(self, style):
        self.pen_style = style
        self.settings.setValue("pen_style", style)
        for t in self._all_tabs():
            t.canvas.set_pen_style(style)
        if self.tool != "pen":
            self.act_pen.trigger()

    def _pick_width_mode(self, mode):
        self.width_mode = mode
        self.settings.setValue("width_mode", mode)
        for t in self._all_tabs():
            t.canvas.set_width_mode(mode)

    # ---- 配色 ----
    def _palette(self, name):
        """返回 (笔色列表, 荧光色列表) 的副本。"""
        if name == CUSTOM:
            try:
                pens, hls = json.loads(self.settings.value("custom_palette", ""))
                if len(pens) == 4 and len(hls) == 3 and all(QColor(c).isValid() for c in pens + hls):
                    return list(pens), list(hls)
            except Exception:
                pass
            name = "经典"
        pens, hls = PALETTES.get(name, PALETTES["经典"])
        return list(pens), list(hls)

    def _refresh_swatches(self):
        for a, c in zip(self.color_actions, self.pen_colors):
            a.setIcon(_color_icon(c))
        for a, c in zip(self.hl_actions, self.hl_colors):
            a.setIcon(_color_icon(c, square=True))

    def _pick_palette(self, name):
        """换配色方案：只影响之后写的内容，已有笔迹和选区不变。"""
        self.palette_name = name
        self.settings.setValue("palette", name)
        self.pen_colors, self.hl_colors = self._palette(name)
        self.color, self.hl_color = self.pen_colors[self.color_idx], self.hl_colors[self.hl_idx]
        self._refresh_swatches()
        for t in self._all_tabs():
            t.canvas.color, t.canvas.hl_color = self.color, self.hl_color
            t.canvas.set_cursor_style(self.cursor_style)  # 刷新光标颜色

    def _open_color_dialog(self):
        """调色盘：自选颜色，替换当前选中的色块，并把结果存成"自定义"配色方案。"""
        hl = self.tool == "hl"
        current = self.hl_color if hl else self.color
        col = QColorDialog.getColor(QColor(current), self, T("调色盘"))
        if not col.isValid():
            return
        name = col.name().upper()
        if hl:
            self.hl_colors[self.hl_idx] = name
        else:
            self.pen_colors[self.color_idx] = name
        self.palette_name = CUSTOM
        self.settings.setValue("palette", CUSTOM)
        self.settings.setValue("custom_palette", json.dumps([self.pen_colors, self.hl_colors]))
        self.cb_palette.setCurrentIndex(self.cb_palette.findData(CUSTOM))
        self._refresh_swatches()
        if hl:
            self._pick_hl_color(name)
        else:
            self._pick_color(name)
        if self.canvas:
            self.canvas.setFocus()

    def _pick_quality(self, q):
        self.quality = q
        self.settings.setValue("quality", q)
        for t in self._all_tabs():
            t.canvas.set_quality(q)

    def _pick_smoothing(self, v):
        self.smoothing = v
        self.settings.setValue("smoothing", v)
        for t in self._all_tabs():
            t.canvas.set_smoothing(v)

    def _pick_claude_mode(self, mode):
        self.claude_mode = mode
        self.settings.setValue("claude_mode", mode)
        self._retitle_ai()

    def _retitle_ai(self):
        """两个按钮和右键菜单的文字跟着设置里选的对象走：问 Claude / 问 ChatGPT / 问 Chrome。
        "问"走 API 面板时始终是 Claude（面板只接 Claude）；"分屏"只看贴靠的对象。"""
        dock = DOCK_SHORT.get(self.dock_target, "Claude")
        ask = "Claude" if self.claude_mode == "api" else dock
        self.act_ask.setText(T("问 {}").format(ask))
        self.act_ask.setToolTip(T("把套索选中的内容（没有选中则是当前页）发给 {} 提问").format(ask) + "  (Ctrl+K)")
        self.act_dock.setText(T("{} 分屏").format(dock))
        for t in self._all_tabs():
            t.canvas.ask_label = self.act_ask.text()
        if hasattr(self, "_settings_wrapped"):  # 按钮宽度变了，换行的临界宽度也跟着变
            QTimer.singleShot(0, self._reflow_toolbars)

    def ask_claude(self):
        """把选区 / 圈出的区域（都没有就是当前页）的截图交给 Claude；用选字工具选中了文字时，交的是那段文字。

        默认方式：截图放进系统剪贴板，切到 Claude 窗口并自动粘贴进对话框，你接着打字提问即可。
        API 方式：放进侧栏的 Claude 面板（需要 API 密钥）。
        """
        c = self.canvas
        if not c:
            return
        target = c.ask_target()
        picked = c.selected_text()  # 选字工具选中的文字：发文字，不发截图
        if picked:
            image, text = c.grab_image(*c.text_sel_target()), picked
        elif target is not None:
            image, text = c.grab_image(*target), ""
        else:
            page = c.current_page()
            image, text = c.grab_image(page), c.doc.page_text(page)
        if self.claude_mode == "api":
            if not self.dock.isVisible():
                self._toggle_sidebar()
            self.sidebar.setCurrentWidget(self.sidebar.ai)
            self.sidebar.ai.attach(image, text)
            return
        if picked:
            QApplication.clipboard().setText(picked)
        else:
            QApplication.clipboard().setImage(image)
        name = self._dock_name()
        # 正贴着的那个窗口优先；没有贴靠就按设置里选的对象去找
        hwnd = self._dock_hwnd if winclaude.is_alive(self._dock_hwnd) else winclaude.find_window(self.dock_target)
        if not hwnd or not winclaude.activate(hwnd):
            self.statusBar().showMessage(
                T("已复制。没找到 {} 的窗口，请打开它后按 Ctrl+V 粘贴。").format(name), 8000)
            return
        QTimer.singleShot(250, lambda: self._paste_into(hwnd))  # 等窗口切到前台再粘贴
        self.statusBar().showMessage(T("已粘贴到 {}，输入问题后回车发送。").format(name), 6000)

    def _paste_into(self, hwnd, tries=0):
        """先把键盘焦点放进对方的对话输入框，再发 Ctrl+V。

        对方窗口切到前台后输入框不一定有焦点，直接粘贴会落空（用户得先点一下输入框）。
        输入框一时找不到（对方的界面信息是第一次被问到才开始准备的）就隔 200 ms 再试，
        最多 5 次；始终找不到就照旧直接粘贴。
        """
        if not winclaude.focus_input(hwnd) and tries < 5:
            QTimer.singleShot(200, lambda: self._paste_into(hwnd, tries + 1))
            return
        QTimer.singleShot(120, winclaude.send_paste)  # 给对方一点时间把焦点落定

    def _dock_name(self):
        return dict(DOCK_TARGETS).get(self.dock_target, "Claude")

    def tile_with_claude(self):
        """把对话窗口（设置里选的 Claude / ChatGPT / Chrome）贴在 RuiPDF 右边当侧边对话：
        顶部对齐，宽高是 RuiPDF 的一个比例（设置里可改），之后跟着 RuiPDF 移动和缩放。
        再点一次取消跟随（那个窗口留在原地）。"""
        if self._dock_hwnd:
            self._set_dock(0)
            self.statusBar().showMessage(T("已取消贴靠。"), 4000)
            return
        hwnd = winclaude.find_window(self.dock_target)
        if not hwnd:
            self._set_dock(0)
            QMessageBox.information(
                self, self.act_dock.text(),
                T("没找到 {} 的窗口。请先打开它（Claude / ChatGPT 也可以是浏览器里正显示着的网页），再点一次。")
                .format(self._dock_name()))
            return
        if self.isFullScreen() or self.isMaximized():
            self.showNormal()
        self._set_dock(hwnd)
        QTimer.singleShot(0, self._start_dock)  # 等窗口从全屏 / 最大化还原完再量位置

    def _set_dock(self, hwnd):
        self._dock_hwnd = hwnd
        self.act_dock.setChecked(bool(hwnd))

    def _start_dock(self):
        if not self._dock_hwnd:
            return
        own = int(self.winId())
        wr, hr, side = self.dock_w / 100, self.dock_h / 100, self.dock_side
        self._dock_min = 0
        winclaude.make_room(own, wr, side=side)  # 那一边位置不够时先挪 / 缩自己
        if winclaude.dock_right(own, self._dock_hwnd, wr, restore=True, hratio=hr, side=side):
            # 对方窗口有最小宽度，要求的宽度比它还窄时它会比要求的宽：按它实际的宽度重新留位置
            got = winclaude.frame_width(self._dock_hwnd)
            if got > round(winclaude.frame_width(own) * wr) + 2:
                self._dock_min = got
                winclaude.make_room(own, wr, got, side=side)
                winclaude.dock_right(own, self._dock_hwnd, wr, restore=True, hratio=hr, side=side, min_other=got)
            self.statusBar().showMessage(
                T("{} 已贴在{}，会跟着这个窗口移动和缩放；再点一次取消。").format(self._dock_name(), dict(DOCK_SIDES)[side]), 6000)
        QTimer.singleShot(0, self._refit_visible)

    def _follow_claude(self):
        """RuiPDF 的窗口动了：让贴靠着的窗口跟上。"""
        if not self._dock_hwnd:
            return
        if not winclaude.is_alive(self._dock_hwnd):  # 对方窗口被关掉了
            self._set_dock(0)
            return
        c = self.canvas
        if c and c.busy() and not c.editing_text():
            return  # 笔正按着写字：这时候不去动别的窗口的位置和叠放次序，免得打断这一笔的输入
        winclaude.dock_right(int(self.winId()), self._dock_hwnd, self.dock_w / 100, hratio=self.dock_h / 100,
                             side=self.dock_side, min_other=self._dock_min)

    def _pick_dock_side(self, side):
        self.dock_side = side
        self.settings.setValue("dock_side", side)
        if self._dock_hwnd:  # 正贴着：马上换到另一边
            self._start_dock()

    def _pick_dock_target(self, key):
        self.dock_target = key
        self.settings.setValue("dock_target", key)
        self._set_dock(0)  # 换了对象：原来贴着的窗口不再跟随
        self._retitle_ai()

    def _load_paste_style(self):
        """把设置里的粘贴排版参数填到 Canvas 上（所有标签页共用）。"""
        Canvas.paste_font = self.settings.value("paste_font", "") or ""
        Canvas.paste_size = max(0.0, min(PASTE_SIZE_RANGE[1], self._setting_float("paste_size", 0.0)))
        Canvas.paste_width = max(PASTE_WIDTH_RANGE[0], min(PASTE_WIDTH_RANGE[1],
                                                           self._setting_float("paste_width", PASTE_WIDTH_DEFAULT)))

    def _edit_paste_style(self):
        """设置粘贴文字（AI 的回答）时用的字体、字号和宽度。只影响之后粘贴的内容。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(T("粘贴内容的字体和大小"))
        form = QFormLayout(dlg)
        font = QFontComboBox()
        font.setCurrentFont(QFont(Canvas.paste_font or QApplication.font().family()))
        default_font = QCheckBox(T("用默认字体"))
        default_font.setChecked(not Canvas.paste_font)
        font.setEnabled(bool(Canvas.paste_font))
        default_font.toggled.connect(lambda on: font.setEnabled(not on))
        size = QDoubleSpinBox()
        size.setRange(*PASTE_SIZE_RANGE)
        size.setDecimals(1)
        size.setSingleStep(0.5)
        size.setSuffix(" pt")
        size.setValue(Canvas.paste_size or 11.0)
        auto = QCheckBox(T("自动（按页面宽度：A4 约 11 pt，宽屏幻灯片 16 pt）"))
        auto.setChecked(not Canvas.paste_size)
        size.setEnabled(bool(Canvas.paste_size))
        auto.toggled.connect(lambda on: size.setEnabled(not on))
        width = QSpinBox()
        width.setRange(*PASTE_WIDTH_RANGE)
        width.setSuffix(" %")
        width.setValue(round(Canvas.paste_width))
        form.addRow(T("字体"), font)
        form.addRow("", default_font)
        form.addRow(T("字号"), size)
        form.addRow("", auto)
        form.addRow(T("宽度（页面宽度的百分比）"), width)
        note = QLabel(T("公式用 KaTeX 自己的数学字体，不受这里的字体影响。贴进去之后还可以用套索拉右下角整体缩放。"))
        note.setWordWrap(True)
        form.addRow(note)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return
        self.settings.setValue("paste_font", "" if default_font.isChecked() else font.currentFont().family())
        self.settings.setValue("paste_size", 0.0 if auto.isChecked() else size.value())
        self.settings.setValue("paste_width", width.value())
        self._load_paste_style()

    def _edit_dock_size(self):
        """设置贴靠窗口的宽和高，各是 RuiPDF 窗口的百分之几。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(T("贴靠窗口的大小"))
        form = QFormLayout(dlg)
        spins = []
        for label, value, lo, hi in ((T("宽度（本窗口宽度的百分比）"), self.dock_w, *DOCK_W_RANGE),
                                     (T("高度（本窗口高度的百分比）"), self.dock_h, *DOCK_H_RANGE)):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setSuffix(" %")
            sp.setValue(value)
            form.addRow(label, sp)
            spins.append(sp)
        note = QLabel(T("对方窗口有自己的最小尺寸（Claude 桌面应用宽约 600 像素），设得比它小时以它的最小尺寸为准。"))
        note.setWordWrap(True)
        form.addRow(note)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return
        self.dock_w, self.dock_h = spins[0].value(), spins[1].value()
        self.settings.setValue("dock_w", self.dock_w)
        self.settings.setValue("dock_h", self.dock_h)
        if self._dock_hwnd:  # 正贴着：马上按新比例重摆（宽了可能要重新留位置）
            self._start_dock()

    def moveEvent(self, ev):
        super().moveEvent(ev)
        self._follow_claude()

    def changeEvent(self, ev):
        super().changeEvent(ev)
        # 从最大化 / 最小化还原，或者切回本窗口：位置等事件处理完才是新的，稍后再跟
        if ev.type() in (QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange) \
                and getattr(self, "_dock_hwnd", 0) and (ev.type() != QEvent.Type.ActivationChange or self.isActiveWindow()):
            QTimer.singleShot(0, self._follow_claude)

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(T("关于 RuiPDF"))
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<h3>RuiPDF</h3>"
            f"<p>{T('版本 {}').format(__version__)}</p>"
            f"<p>{T('作者：{}').format(__author__)}</p>"
            f"<p>{T('配合数位板在 PDF 上手写标注、复习备考的工具。')}</p>")
        pm = app_icon().pixmap(QSize(64, 64), self.devicePixelRatioF())
        if not pm.isNull():
            box.setIconPixmap(pm)
        box.exec()

    def _pick_ui_font(self, key: str):
        """换界面字体，立刻生效。"""
        self.ui_font_key = key
        self.settings.setValue("ui_font", key)
        apply_ui_font(key)
        self.setStyleSheet(self.styleSheet())  # 让带样式的控件按新字体重新算一遍
        QTimer.singleShot(0, self._reflow_toolbars)  # 字宽变了，工具栏该不该换行也要重新判断

    def paintEvent(self, ev):
        # 窗口是背景透明的（为了液态玻璃能随时开关），这种窗口 Qt 不会替我们涂底色，样式表里写了也不管用。
        # 所以不是液态玻璃时自己把底涂上；液态玻璃时什么都不画，露出后面的毛玻璃。
        if not self.glass_on:
            p = QPainter(self)
            p.fillRect(ev.rect(), QColor(theme.window_color()))
            p.end()

    def _style_caption(self):
        """系统标题栏跟着风格变色（液态玻璃时用系统默认的，透出毛玻璃）。"""
        winglass.set_caption(int(self.winId()), None if self.glass_on else theme.window_color(), theme.is_dark())

    def _style_hint(self):
        self.hint.setStyleSheet("background:%s; color:#8E8E93; font-size:15px;" % theme.canvas_bg())

    def _rebuild_icons(self):
        """重画工具图标（深色和其余风格之间切换时，线条的深浅要反过来）。色块不用动。"""
        for act, make in ((self.act_pen, _pen_icon), (self.act_hl, _hl_icon), (self.act_eraser, _eraser_icon),
                          (self.act_lasso, _lasso_icon), (self.act_text, _text_icon), (self.act_mask, _mask_icon),
                          (self.act_select, _select_icon), (self.act_flyout, _sliders_icon)):
            act.setIcon(make())
        self.act_shape.setIcon(_shape_icon(self.shape))
        for act, kind in self._shape_menu_actions:
            act.setIcon(_shape_icon(kind))
        for act, preset in zip(self.width_actions, WIDTHS):
            act.setIcon(_width_icon(preset[1]))

    def _pick_theme(self, key: str):
        """换界面风格，立刻生效：换样式表和调色板；液态玻璃再铺上 / 撤掉窗口后面的毛玻璃。"""
        if key not in theme.THEMES or (key == "glass" and not theme.glass_capable):
            key = "light"
        was_dark = theme.is_dark()
        self.theme_key = theme.current = key
        self.settings.setValue("theme", key)
        self._theme_actions[key].setChecked(True)
        self.glass_on = theme.glass_enabled = key == "glass"
        QApplication.instance().setPalette(theme.palette())
        self.setStyleSheet(theme.stylesheet())
        if self._feedback_off:  # 窗口已经显示过（有句柄了）
            (winglass.enable if self.glass_on else winglass.disable)(int(self.winId()))
            self._style_caption()
        if theme.is_dark() != was_dark:
            self._rebuild_icons()
        self.floatbar.restyle()
        for bar in self.findChildren(FormatBar):  # 正开着的文字格式工具条
            bar.setStyleSheet(theme.format_bar_style())
        self._style_hint()
        self._reflow_toolbars()
        self.place_floatbar()
        for wdg in self.findChildren(QWidget):  # 画布的底色、四个圆角都是自己画的，叫它们重画
            wdg.update()
        self.update()

    def _pick_language(self, lang):
        if lang == i18n.LANG:
            return
        self.settings.setValue("language", lang)
        QMessageBox.information(self, "语言 / Language",
                                "重启 RuiPDF 后生效。\nTakes effect after restarting RuiPDF.")

    def _pick_cursor(self, key):
        self.cursor_style = key
        self.settings.setValue("cursor_style", key)
        for t in self._all_tabs():
            t.canvas.set_cursor_style(key)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized() if self._was_maximized else self.showNormal()
        else:
            self._was_maximized = self.isMaximized()
            self.showFullScreen()

    def keyPressEvent(self, ev):
        # 全屏时按 Esc 退出全屏。画布上有选区、正在输入文字、查找栏开着时，Esc 先被它们用掉（取消选区等），
        # 到不了这里；再按一次才退出全屏。
        if ev.key() == Qt.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
            return
        super().keyPressEvent(ev)

    def _toggle_sidebar(self):
        self.dock.setVisible(not self.dock.isVisible())
        self.settings.setValue("sidebar", "true" if self.dock.isVisible() else "false")

    def _cycle_tab(self, step):
        n = self.active.count()
        if n > 1:
            self.active.setCurrentIndex((self.active.currentIndex() + step) % n)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._reflow_toolbars()
        self._follow_claude()

    def _reflow_toolbars(self):
        """窗口够宽时，每行的后半段接在前半段右边；不够宽时：

        第一行（文件 / 页面 | 问 Claude … 关于）：后半段收起来，前半段右端出现"更多"按钮，点它才在下一行展开；
        第二行（工具条 | 笔的设置，固定在顶部时才有）：后半段自动换到下一行。
        """
        need = self.tb_file.sizeHint().width() + self.tb_view.sizeHint().width() + 8 + 14  # 14 = 窗口左右留的缝
        if self._view_wrapped:  # 换行后分隔线是隐藏的，把它的宽度算回来，免得在临界宽度来回跳
            need += self.tb_view.widgetForAction(self._view_sep).sizeHint().width()
        wrap = self.width() < need
        if wrap != self._view_wrapped:
            self._view_wrapped = wrap
            self._view_sep.setVisible(not wrap)
            if wrap:  # 后半段挪到第二行；第一行是 前半段（占满，放不下的进 »）+ "更多"
                self._top_row1.removeWidget(self.tb_view)
                self._top_row2.addWidget(self.tb_view, 1)
            else:
                self._top_row2.removeWidget(self.tb_view)
                self._top_row1.addWidget(self.tb_view, 1)
            self._top_row1.setStretchFactor(self.tb_file, 1 if wrap else 0)
            self.tb_more.setVisible(wrap)
            # "更多"这条不许被挤小（否则按钮自己会被收进 »）；窗口再窄就让前半段去收
            self.tb_more.setFixedWidth(self.tb_more.sizeHint().width())
            self.tb_view.setVisible(not wrap or self.act_more.isChecked())
        if getattr(self, "toolbar_pos", "docked") != "docked":
            return  # 工具和笔设置浮在画布上，不在窗口顶部，换不换行由 FloatBar 自己管
        need = self.tb_tools.sizeHint().width() + self.tb_settings.sizeHint().width() + 8
        wrap = self.width() < need
        if wrap != self._settings_wrapped:
            self._settings_wrapped = wrap
            if wrap:
                self.insertToolBarBreak(self.tb_settings)
            else:
                self.removeToolBarBreak(self.tb_settings)

    def _toggle_more(self):
        """窗口窄时展开 / 收起第一行的后半段。"""
        on = self.act_more.isChecked()
        self.act_more.setText(T("收起") + " ▴" if on else T("更多") + " ▾")
        self.tb_view.setVisible(not self._view_wrapped or on)

    # ------------------------------------------------------------------ 悬浮工具条
    def _save_toolbar_len(self):
        for k, v in self.floatbar.length.items():
            self.settings.setValue("toolbar_len_" + k, int(v))

    def _edit_toolbar_opacity(self):
        """调悬浮工具条的不透明度：拖滑块时马上看到效果，取消则恢复原样。"""
        dlg = QDialog(self)
        dlg.setWindowTitle(T("悬浮工具栏的不透明度"))
        form = QFormLayout(dlg)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(*theme.FLOAT_OPACITY_RANGE)
        slider.setValue(self.toolbar_opacity)
        slider.setMinimumWidth(260)
        label = QLabel(f"{self.toolbar_opacity} %")
        slider.valueChanged.connect(lambda v: (label.setText(f"{v} %"), self.floatbar.set_opacity(v)))
        form.addRow(slider, label)
        note = QLabel(T("只改变工具条那块底的透明程度，上面的按钮不会变淡。工具栏固定在窗口顶部时不起作用。"))
        note.setWordWrap(True)
        form.addRow(note)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() == QDialog.Accepted:
            self.toolbar_opacity = slider.value()
            self.settings.setValue("toolbar_opacity", self.toolbar_opacity)
        self.floatbar.set_opacity(self.toolbar_opacity)

    def _pick_toolbar_pos(self, pos: str):
        if pos in self._pos_actions:
            self._pos_actions[pos].setChecked(True)  # 拖动工具条换位置时，菜单里的勾也跟着换
        self.settings.setValue("toolbar_pos", pos)
        self._apply_toolbar_pos(pos)

    def _apply_toolbar_pos(self, pos: str):
        """把"工具"和"笔设置"两条工具栏放到指定的位置：浮在画布某一边，或者固定回窗口顶部。"""
        self.toolbar_pos = pos
        if pos == "docked":
            self.floatbar.release()
            for tb in (self.tb_tools, self.tb_settings):
                self.addToolBar(Qt.TopToolBarArea, tb)
                tb.show()
            self.insertToolBarBreak(self.tb_tools)  # 另起一行，排在"文件 / 视图"那一行下面
            self._settings_wrapped = False
            for t in self._all_tabs():
                t.canvas.set_insets(0, 0, 0, 0)
            self._reflow_toolbars()
        else:
            for tb in (self.tb_tools, self.tb_settings):
                if self.toolBarArea(tb) != Qt.NoToolBarArea:
                    self.removeToolBar(tb)
            self.floatbar.adopt()
            self.place_floatbar()

    def place_floatbar(self):
        """（稍后）重新摆一次悬浮工具条。窗口大小、标签页、分栏有变化时都调它。"""
        self._float_timer.start(0)

    def _place_floatbar_now(self):
        if self.toolbar_pos == "docked":
            return
        # 参考区域：当前显示着的画布（分屏时是两栏合起来）；没有打开文档时就是整个中间区域
        rects = []
        for pane in self.panes:
            t = pane.currentWidget()
            if t and pane.isVisible() and self.stack.currentIndex() == 1:
                rects.append((pane, QRect(t.canvas.mapTo(self.stack, QPoint(0, 0)), t.canvas.size())))
        ref = self.stack.rect()
        if rects:
            ref = rects[0][1]
            for _pane, r in rects[1:]:
                ref = ref.united(r)
        used = self.floatbar.arrange(self.toolbar_pos, ref)
        # 每一栏的画布让出被工具条占掉的那一边（同一栏里没显示出来的标签页跟着用一样的）
        for pane, cr in rects:
            ins = {"top": (0, max(0, used.bottom() + 1 - cr.top()), 0, 0),
                   "bottom": (0, 0, 0, max(0, cr.bottom() + 1 - used.top())),
                   "left": (max(0, used.right() + 1 - cr.left()), 0, 0, 0),
                   "right": (0, 0, max(0, cr.right() + 1 - used.left()), 0)}[self.toolbar_pos]
            for i in range(pane.count()):
                pane.widget(i).canvas.set_insets(*ins)

    def eventFilter(self, obj, ev):
        if obj is self.stack and ev.type() == QEvent.Type.Resize:
            self.place_floatbar()
        return super().eventFilter(obj, ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._reflow_toolbars()
        self.place_floatbar()
        if not self._feedback_off:
            self._feedback_off = True
            disable_pen_feedback(int(self.winId()))
            if self.glass_on:
                winglass.enable(int(self.winId()))
            elif theme.glass_capable:
                winglass.disable(int(self.winId()))
            self._style_caption()

    # ------------------------------------------------------------------ 标签页状态同步
    def _tab_changed(self, _index=None):
        left, right = self.panes
        if left.count() == 0 and right.count() > 0:  # 左栏空了：把右栏的标签并回来
            for t in [right.widget(i) for i in range(right.count())]:
                self._move_tab(t, left)
            self.active = left
            QTimer.singleShot(0, self._refit_visible)
        right.setVisible(right.count() > 0)
        if self.active.count() == 0:
            self.active = left
        if self._find_hits or self._find_text:
            self._clear_find()
        t = self.tab()
        self.stack.setCurrentIndex(1 if t else 0)
        self.place_floatbar()
        self.sidebar.set_canvas(t.canvas if t else None)
        self._refresh_title()
        if not t:
            self.lbl_page.setText("")
            self.lbl_zoom.setText("")
            self.act_undo.setEnabled(False)
            self.act_redo.setEnabled(False)
            return
        c = t.canvas
        self._show_page(t, c.current_page() + 1, len(c.doc))
        self._show_zoom(t, c.zoom)
        self.act_undo.setEnabled(bool(c.undo_stack))
        self.act_redo.setEnabled(bool(c.redo_stack))
        c.setFocus()

    def _show_page(self, t, i, n):
        if t is self.tab():
            self.lbl_page.setText(T("  第 {} / {} 页  ").format(i, n))
            self.sidebar.set_current(i - 1)

    def _show_zoom(self, t, z):
        if t is self.tab():
            self.lbl_zoom.setText(T("缩放 {}%").format(round(z * 100 * 72 / 96)))

    def _show_history(self, t, u, r):
        if t is self.tab():
            self.act_undo.setEnabled(u)
            self.act_redo.setEnabled(r)

    def _on_changed(self, t):
        if t is self.tab():
            self.sidebar.notes_changed()
        t.backup_stale = True
        self._set_dirty(t, True)

    def _set_dirty(self, t, dirty):
        t.dirty = dirty
        pane = self._pane_of(t)
        if pane is not None:
            i = pane.indexOf(t)
            pane.setTabText(i, ("● " if dirty else "") + os.path.basename(t.doc.path))
            pane.setTabToolTip(i, t.doc.path)
        self._refresh_title()

    def _refresh_title(self):
        t = self.tab()
        if not t:
            self.setWindowTitle("RuiPDF")
        else:
            self.setWindowTitle(f"{'● ' if t.dirty else ''}{os.path.basename(t.doc.path)} — RuiPDF")

    # ------------------------------------------------------------------ 自动保存 / 记住位置
    # 自动保存只写一份备份（在系统的应用数据目录里），不碰原 PDF；Ctrl+S 才真正写进 PDF。
    @staticmethod
    def _key(path) -> str:
        return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:20]

    def _backup_path(self, path) -> str:
        base = QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)
        folder = os.path.join(base, "RuiPDF", "autosave")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, self._key(path) + ".json")

    def _drop_backup(self, t, path=None):
        try:
            os.remove(self._backup_path(path or t.doc.path))
        except OSError:
            pass
        t.backup_stale = False

    def _autosave(self):
        for t in self._all_tabs():
            self._remember_view(t)
            if not (t.dirty and t.backup_stale) or t.canvas.busy():
                continue  # 正在写字时不打断，下一轮再存
            doc = t.doc
            data = {"path": doc.path, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "ops": doc.ops,
                    "strokes": {str(i): [s.to_json() for s in lst]
                                for i, lst in t.canvas.strokes.items() if lst}}
            target = self._backup_path(doc.path)
            try:
                with open(target + ".tmp", "w", encoding="utf-8") as f:
                    json.dump(data, f, separators=(",", ":"))
                os.replace(target + ".tmp", target)
                t.backup_stale = False
            except OSError:
                pass

    def _load_backup(self, doc):
        """打开文件时，如果有上次没保存的备份，询问是否恢复。

        恢复时先在 doc 上重放页面改动（空白页、留白、书签），返回要放回画布的笔迹；不恢复返回 None。
        """
        target = self._backup_path(doc.path)
        if not os.path.exists(target):
            return None
        try:
            with open(target, encoding="utf-8") as f:
                data = json.load(f)
            ops = data.get("ops", [])
            strokes = {int(i): [item_from_json(d) for d in lst] for i, lst in data["strokes"].items()}
        except Exception:
            os.remove(target)
            return None
        box = QMessageBox(QMessageBox.Question, T("恢复笔迹"),
                          os.path.basename(doc.path) + "\n\n" + T("上次有没保存的内容（自动备份于 {}）。要恢复吗？").format(data.get("time", "?")),
                          parent=self)
        b_yes = box.addButton(T("恢复"), QMessageBox.AcceptRole)
        box.addButton(T("丢弃"), QMessageBox.DestructiveRole)
        box.exec()
        if box.clickedButton() is not b_yes:
            os.remove(target)
            return None
        try:
            doc.apply_ops(ops)
        except Exception:
            return None
        return {i: lst for i, lst in strokes.items() if i < len(doc)}

    def _remember_view(self, t):
        view = t.canvas.get_view()
        if t.doc and view:
            self.settings.setValue("view/" + self._key(t.doc.path), json.dumps(view))

    def _restore_view(self, t):
        try:
            page, frac, zoom = json.loads(self.settings.value("view/" + self._key(t.doc.path), ""))
            t.canvas.set_view(page, frac, zoom)
        except Exception:
            pass  # 第一次打开：保持适合宽度

    # ------------------------------------------------------------------ 打开 / 保存 / 关闭
    def new_note(self):
        """新建笔记：选模板 -> 选保存位置 -> 生成 PDF 并打开。"""
        dlg = NewNoteDialog(self, self.settings.value("last_template", "lined"))
        if dlg.exec() != NewNoteDialog.Accepted or not dlg.template():
            return
        folder = self.settings.value("last_dir", "") or QStandardPaths.writableLocation(
            QStandardPaths.DocumentsLocation)
        default = os.path.join(folder, T("笔记") + " " + time.strftime("%Y-%m-%d") + ".pdf")
        path, _ = QFileDialog.getSaveFileName(self, T("保存新笔记"), default, T("PDF 文件 (*.pdf)"))
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        path = os.path.abspath(path)
        if any(os.path.normcase(t.doc.path) == os.path.normcase(path) for t in self._all_tabs()):
            QMessageBox.warning(self, T("新建笔记"), T("这个文件正开着，请换一个文件名。"))
            return
        try:
            create_notebook(path, dlg.template(), dlg.landscape(), dlg.pages())
        except Exception as e:
            QMessageBox.warning(self, T("新建笔记"), str(e))
            return
        self.settings.setValue("last_template", dlg.template())
        self.settings.remove("view/" + self._key(path))  # 同名旧文件的阅读位置不要带过来
        try:
            os.remove(self._backup_path(path))
        except OSError:
            pass
        self.open_file(path)

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, T("打开 PDF"), self.settings.value("last_dir", ""),
                                                T("PDF 文件 (*.pdf)"))
        for p in paths:
            self.open_file(p)

    def open_file(self, path):
        path = os.path.abspath(path)
        for t in self._all_tabs():  # 已经打开了就切过去
            if os.path.normcase(t.doc.path) == os.path.normcase(path):
                self.active = self._pane_of(t)
                self.active.setCurrentWidget(t)
                self._tab_changed()
                return
        try:
            doc = Document(path)
            if len(doc) == 0:
                raise ValueError(T("文件里没有页面"))
        except Exception as e:  # 损坏或加密的文件
            QMessageBox.warning(self, T("打不开"), f"{path}\n\n{e}")
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        recovered = self._load_backup(doc)

        t = DocTab()
        c = t.canvas
        self._apply_tools(c)
        c.changed.connect(lambda t=t: self._on_changed(t))
        c.pageChanged.connect(lambda i, n, t=t: self._show_page(t, i, n))
        c.zoomChanged.connect(lambda z, t=t: self._show_zoom(t, z))
        c.historyChanged.connect(lambda u, r, t=t: self._show_history(t, u, r))
        c.penInfo.connect(self.lbl_pen.setText)
        c.notice.connect(lambda msg: self.statusBar().showMessage(msg, 6000))
        c.structureChanged.connect(lambda t=t: self.sidebar.rebuild() if t is self.tab() else None)
        c.focused.connect(lambda t=t: self._activate(t))
        c.toolRequested.connect(lambda tool: self.act_lasso.trigger() if tool == "lasso" else None)
        c.askRequested.connect(self.ask_claude)

        self.stack.setCurrentIndex(1)
        pane = self.active
        pane.blockSignals(True)
        i = pane.addTab(t, os.path.basename(path))
        pane.setCurrentIndex(i)
        pane.blockSignals(False)
        QApplication.processEvents()  # 让画布拿到真实尺寸，"适合宽度"才算得对
        c.set_document(doc)
        self._restore_view(t)
        if recovered is not None:
            c.set_strokes(recovered)
            t.backup_stale = False
            self._set_dirty(t, True)
        else:
            self._set_dirty(t, False)
        self._tab_changed()

    def save(self, path=None, t=None) -> bool:
        t = t or self.tab()
        if not t:
            return False
        doc = t.doc
        old_path = doc.path
        t.canvas.commit_text_edit()  # 正在页面上输入的文字先落下，否则存不进去
        self._remember_view(t)
        try:
            doc.save(t.canvas.strokes, path or None)
        except Exception as e:
            QMessageBox.warning(self, T("保存失败"),
                                f"{e}\n\n" + T("如果这个 PDF 正被别的软件打开，请先关掉它再保存，或者用“另存为”。"))
            return False
        self._drop_backup(t, old_path)
        self._set_dirty(t, False)
        self._remember_view(t)
        self.statusBar().showMessage(T("已保存"), 3000)
        return True

    def save_as(self):
        t = self.tab()
        if not t:
            return False
        base, ext = os.path.splitext(t.doc.path)
        path, _ = QFileDialog.getSaveFileName(self, T("另存为"), base + T("_标注") + ext, T("PDF 文件 (*.pdf)"))
        return self.save(path) if path else False

    def _confirm_discard(self, t) -> bool:
        """有未保存的内容时询问。返回 True 表示可以继续关闭。"""
        if not t.dirty:
            return True
        self.active = self._pane_of(t)
        self.active.setCurrentWidget(t)
        box = QMessageBox(QMessageBox.Question, T("未保存"),
                          os.path.basename(t.doc.path) + "\n\n" + T("有内容还没有保存，要保存吗？"), parent=self)
        b_save = box.addButton(T("保存"), QMessageBox.AcceptRole)
        b_drop = box.addButton(T("不保存"), QMessageBox.DestructiveRole)
        box.addButton(T("取消"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is b_save:
            return self.save(t=t)
        if box.clickedButton() is b_drop:
            self._drop_backup(t)
            t.dirty = False
            return True
        return False

    def close_tab(self, t):
        if not t or not self._confirm_discard(t):
            return False
        self._remember_view(t)
        pane = self._pane_of(t)
        pane.removeTab(pane.indexOf(t))
        t.doc.close()
        t.deleteLater()
        self._tab_changed()
        return True

    def closeEvent(self, ev):
        for t in self._all_tabs():
            if not self._confirm_discard(t):
                ev.ignore()
                return
            self._remember_view(t)
        ev.accept()

    def export_annotated(self):
        """只导出写过东西的页（遮挡块不算），方便打印或做成错题 / 重点合集。"""
        t = self.tab()
        if not t:
            return
        pages = sorted(i for i, items in t.canvas.strokes.items()
                       if any(it.kind != "mask" for it in items))
        if not pages:
            QMessageBox.information(self, T("导出"), T("这个 PDF 里还没有标注。"))
            return
        base, ext = os.path.splitext(t.doc.path)
        path, _ = QFileDialog.getSaveFileName(self, T("导出有标注的页"), base + T("_标注页") + ext, T("PDF 文件 (*.pdf)"))
        if not path:
            return
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(t.doc.path):
            QMessageBox.warning(self, T("导出"), T("不能覆盖当前打开的文件，请换一个文件名。"))
            return
        try:
            t.doc.export_pages(t.canvas.strokes, pages, path)
        except Exception as e:
            QMessageBox.warning(self, T("导出失败"), str(e))
            return
        self.statusBar().showMessage(T("已导出 {} 页").format(len(pages)), 4000)

    def edit_margins(self, remove: bool = False):
        """调整当前页的留白：自己定宽度（毫米），或改小、去掉。改小 / 去掉前先警告：落在裁掉部分里的东西会被删掉。"""
        c = self.canvas
        if not c or not c.doc:
            return
        i = c.current_page()
        mr, mb = c.doc.page_margin(i)
        mm = 25.4 / 72  # 1 pt 是多少毫米
        if remove:
            if mr < 0.01 and mb < 0.01:
                QMessageBox.information(self, T("去掉留白"), T("这一页没有可以去掉的留白。\n（只认得这个版本开始加的留白；更早加的没有记录。）"))
                return
            right = bottom = 0.0
        else:
            dlg = QDialog(self)
            dlg.setWindowTitle(T("调整留白"))
            form = QFormLayout(dlg)
            w, h = c.doc.sizes[i]
            info = QLabel(T("第 {} 页：原来的页面 {:.0f} × {:.0f} 毫米").format(i + 1, (w - mr) * mm, (h - mb) * mm))
            form.addRow(info)
            spins = []
            for label, value in ((T("右侧留白"), mr), (T("底部留白"), mb)):
                sp = QDoubleSpinBox()
                sp.setRange(0, 2000)
                sp.setDecimals(0)
                sp.setSingleStep(10)
                sp.setSuffix(T(" 毫米"))
                sp.setValue(round(value * mm))
                form.addRow(label, sp)
                spins.append(sp)
            note = QLabel(T("填 0 就是去掉。改小或去掉留白时，留白里被裁掉的那部分上的笔迹、文字、图片会一起删掉，而且不能撤销。"))
            note.setWordWrap(True)
            form.addRow(note)
            box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            box.accepted.connect(dlg.accept)
            box.rejected.connect(dlg.reject)
            form.addRow(box)
            if dlg.exec() != QDialog.Accepted:
                return
            # 没动过的那一项保持原来精确的数（毫米是取整显示的，直接换算回去会差一点点）
            right = mr if spins[0].value() == round(mr * mm) else spins[0].value() / mm
            bottom = mb if spins[1].value() == round(mb * mm) else spins[1].value() / mm
        if right < mr - 0.01 or bottom < mb - 0.01:  # 有一边变小了：警告
            lost = len(c.margin_loss(right, bottom, i))
            text = T("留白改小后，被裁掉的那部分就没有了。")
            text += "\n" + (T("那里有 {} 个对象（笔迹、文字、图片）会被删掉。").format(lost) if lost else T("那里现在没有笔迹。"))
            text += "\n" + T("这一步不能撤销，之前的撤销记录也会清空。确定吗？")
            if QMessageBox.warning(self, T("调整留白"), text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        c.set_margins(right, bottom, i)

    def delete_blank_page(self):
        c = self.canvas
        if not c:
            return
        i = c.current_page()
        if not c.doc.is_blank(i):
            QMessageBox.information(self, T("删除空白页"), T("只能删除由 RuiPDF 插入的空白页，当前页是 PDF 原有的页面。"))
            return
        if c.strokes.get(i):
            r = QMessageBox.question(self, T("删除空白页"), T("第 {} 页上有笔迹，删除后无法撤销。确定删除吗？").format(i + 1))
            if r != QMessageBox.Yes:
                return
        c.delete_page(i)

    def insert_image_dialog(self):
        """页面 → 插入图片：选一张或几张图片，放到当前页。"""
        c = self.canvas
        if not c:
            return
        pattern = " ".join("*" + e for e in IMAGE_EXTS)
        paths, _ = QFileDialog.getOpenFileNames(self, T("插入图片"), self.settings.value("image_dir", ""),
                                                T("图片 ({})").format(pattern))
        if paths:
            self.settings.setValue("image_dir", os.path.dirname(paths[0]))
        for path in paths:
            c.insert_image(path)

    def dragEnterEvent(self, ev):
        names = [u.toLocalFile().lower() for u in ev.mimeData().urls()]
        if any(n.endswith(".pdf") or (self.canvas and n.endswith(IMAGE_EXTS)) for n in names):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            path = u.toLocalFile()
            if path.lower().endswith(".pdf"):
                self.open_file(path)
            elif path.lower().endswith(IMAGE_EXTS) and self.canvas:  # 图片文件：插到当前页
                self.canvas.insert_image(path)


def _shutdown_rich():
    """退出前关掉排版用的浏览器页面（没用过粘贴排版就什么都不用做）。"""
    mod = sys.modules.get(__package__ + ".richpaste")
    if mod is not None:
        mod.shutdown()


def _warm_rich():
    """窗口显示出来之后，趁空闲把排版用的浏览器引擎先启动好，这样第一次粘贴 AI 回答不用干等两三秒。"""
    from . import richpaste
    richpaste.warm_up()


def main():
    # 高分屏：按系统的实际缩放比（125%、150%、175%…）渲染，不四舍五入
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    # 粘贴 AI 回答时要用浏览器引擎排版，它是用到时才加载的，Qt 要求这种情况下事先打开这个开关
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    if sys.platform == "win32":
        # 给进程一个自己的任务栏身份，否则任务栏按 python.exe 归组，显示的是 Python 的图标
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RuichengShi.RuiPDF")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setWindowIcon(app_icon())
    app.aboutToQuit.connect(_shutdown_rich)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    for path in sys.argv[1:]:
        win.open_file(path)
    QTimer.singleShot(1500, _warm_rich)  # 窗口先出来能用，稍后再在后台把排版引擎启动好
    sys.exit(app.exec())
