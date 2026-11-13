"""画布：连续滚动显示 PDF，并处理数位板 / 鼠标输入。

低延迟的做法：每页缓存一张「页面 + 已有笔迹」的合成图；压感笔书写时每来一个点，
只把新增的一小段画进合成图，并只刷新那一小块屏幕区域。
荧光笔、形状、套索选中的对象则在 paintEvent 里实时叠画，松手后才并入合成图。
"""
import bisect
import math
import uuid
from collections import OrderedDict

from PySide6.QtCore import (QBuffer, QElapsedTimer, QEvent, QIODevice, QMimeData, QPointF, QRect, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QColor, QCursor, QGuiApplication, QImage, QKeySequence, QPainter, QPen, QPixmap,
                           QPointingDevice, QPolygonF)
from PySide6.QtWidgets import QMenu, QWidget

from .i18n import T
from . import theme as _theme
from .theme import PAGE_EDGE
from .stroke import (BOX_KINDS, SHAPES, ImageItem, MaskItem, RichItem, Stroke, TextItem, draw_item, draw_piece,
                     draw_tail, item_from_json, make_shape)
from .textedit import TextEditor

GAP = 18          # 页间距（px）
MARGIN = 14       # 页面左右最小留白（px）
CACHE_PIXELS = 80_000_000   # 合成图（按书写分辨率画的，书写时用）缓存的总像素上限（约 320 MB）
DISP_PIXELS = 60_000_000    # 显示图（屏幕分辨率，上屏用）缓存的总像素上限（约 240 MB）；它小，能多留十几页
IDLE_MS = 110               # 停止滚动 / 缩放这么久之后，开始做空闲时的活（换精细图、预渲染前后页）
ZOOM_SETTLE_MS = 160        # 连续缩放时，最后一格过去这么久才真正重画
PAGE_PIXELS = 36_000_000    # 单页合成图的像素上限，防止高倍放大 + 高分辨率时内存爆掉
ERASER_PX = 9     # 橡皮半径（px）
HANDLE_PX = 12    # 选区缩放手柄边长（px）
REGION_MIN_PT = 8.0  # 套索圈出的区域拖边改大小时，宽高不小于这么多 pt
MIN_ZOOM, MAX_ZOOM = 0.3, 6.0
BASE_ZOOM = 96 / 72  # 显示为 100% 时的缩放；"屏幕固定"模式以它为基准
SELECT_RATIO = 0.7  # 对象有这么大比例落在套索内就算选中
OWN_MIME = "application/x-ruipdf-items"  # 我们自己复制笔迹时放在系统剪贴板上的记号
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
IMAGE_MAX_PX = 2400  # 插入的图片长边超过这么多像素就先缩小


def cursor_pixmap(style: str, color: str, radius: float, dpr: float, erasing: bool = False):
    """画出某种样式的光标图。返回 (QPixmap, 热点)。

    radius：「圆点」样式的半径（px），即当前笔迹粗细的一半。设置菜单里的预览图也用这个函数。
    """
    size = 33
    c = size // 2
    hot = (c, c)
    pm = QPixmap(round(size * dpr), round(size * dpr))  # 按屏幕缩放比出图，高分屏上光标不糊
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if erasing:
        for col, w in (("#ffffff", 3.0), ("#222222", 1.2)):
            p.setPen(QPen(QColor(col), w))
            p.drawEllipse(QPointF(c + 0.5, c + 0.5), ERASER_PX, ERASER_PX)
    elif style == "pen":  # 一支斜放的笔，笔尖在左下角，笔尖颜色 = 当前颜色
        from PySide6.QtGui import QPolygonF
        hot = (2, size - 3)
        p.translate(hot[0] + 0.5, hot[1] + 0.5)
        p.rotate(-45)
        p.scale(0.65, 0.65)  # 笔的大小
        nib = QPolygonF([QPointF(0, 0), QPointF(8, -3.5), QPointF(8, 3.5)])
        for outline, w in (("#ffffff", 4.4), ("#222222", 1.5)):
            p.setPen(QPen(QColor(outline), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(QColor(color))
            p.drawPolygon(nib)
            p.setBrush(QColor("#f2f2f2"))
            p.drawRect(QRectF(8, -3.5, 20, 7))
            p.setBrush(QColor("#555555"))
            p.drawRect(QRectF(28, -3.5, 4, 7))
    elif style == "crosshair":
        for col, w in (("#ffffff", 3.0), (color, 1.0)):
            p.setPen(QPen(QColor(col), w))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p.drawLine(QPointF(c + 0.5 + dx * 3, c + 0.5 + dy * 3),
                           QPointF(c + 0.5 + dx * 12, c + 0.5 + dy * 12))
    elif style == "solid":  # 固定大小的黑色实心点，不随笔宽和颜色变
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.setBrush(QColor("#111111"))
        p.drawEllipse(QPointF(c + 0.5, c + 0.5), 3.2, 3.2)
    elif style == "ring":
        for col, w in (("#ffffff", 3.4), (color, 1.6)):
            p.setPen(QPen(QColor(col), w))
            p.drawEllipse(QPointF(c + 0.5, c + 0.5), 5.5, 5.5)
    else:  # dot / cross：实心点，直径约等于实际笔迹粗细
        r = max(2.0, min(7.0, radius))
        if style == "cross":
            for col, w in (("#ffffff", 3.0), ("#222222", 1.0)):
                p.setPen(QPen(QColor(col), w))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    p.drawLine(QPointF(c + 0.5 + dx * 9, c + 0.5 + dy * 9),
                               QPointF(c + 0.5 + dx * 14, c + 0.5 + dy * 14))
        p.setPen(QPen(QColor("#ffffff"), 1.2))
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(c + 0.5, c + 0.5), r, r)
    p.end()
    return pm, hot


class Canvas(QWidget):
    pageChanged = Signal(int, int)      # 当前页(从 1 开始), 总页数
    zoomChanged = Signal(float)
    penInfo = Signal(str)               # 输入设备 / 压感，显示在状态栏
    notice = Signal(str)                # 给用户的一句提示，在状态栏显示几秒
    historyChanged = Signal(bool, bool)  # 可撤销, 可重做
    scrollRangeChanged = Signal(int, int, int)  # 最大值, 页步长, 当前值
    changed = Signal()                  # 内容有改动（用于"未保存"提示）
    structureChanged = Signal()         # 页数 / 页面大小变了（侧栏要刷新）
    focused = Signal()                  # 获得键盘焦点（分屏时用来判断哪一栏是当前栏）
    toolRequested = Signal(str)         # 请主窗口切换工具（粘贴后切到套索，方便接着拖动）
    askRequested = Signal()             # 右键菜单选了"问 Claude"

    # 剪贴板：所有标签页共用，所以可以从一个 PDF 复制到另一个。
    # (对象的 JSON 列表, 选区外框 (x, y, w, h))
    clipboard = None
    _clip_token = b""  # 复制时放到系统剪贴板上的记号，见 copy_selection
    # 粘贴文字（AI 的回答）时的排版设置，主窗口从设置里读出来填到这里，所有标签页共用
    paste_font = ""      # 字体；空 = 和文本框一样的系统默认字体
    paste_size = 0.0     # 字号（pt）；0 = 按页面宽度自动定
    paste_width = 60.0   # 宽度占页面宽度的百分比
    _paste_count = 0
    ask_label = T("问 Claude")  # 右键菜单里那一项的文字；主窗口按设置里选的对象改（问 ChatGPT 等）

    CURSOR_STYLES = [("dot", T("圆点（随笔宽和颜色变化）")), ("solid", T("实心圆点（固定大小）")),
                     ("pen", T("笔")), ("ring", T("圆环")),
                     ("cross", T("圆点 + 刻度")), ("crosshair", T("细十字")), ("arrow", T("系统箭头"))]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)  # 悬停时也收到移动事件，用来保持光标样式
        self._cursor = QCursor(Qt.ArrowCursor)
        self._cursor_clock = QElapsedTimer()
        self._cursor_clock.start()
        self.doc = None
        self.zoom = 1.0          # 逻辑像素 / pt
        self.sx = 0              # 水平滚动
        self.sy = 0              # 垂直滚动
        self.tops = []           # 每页顶部 y（内容坐标）
        self.insets = (0, 0, 0, 0)  # 四边留空（左, 上, 右, 下），见 set_insets
        self._fitted = False     # 当前的缩放是不是"适合宽度"得来的（留空变化时要不要重新适合）
        self.total_h = 0
        self.content_w = 0
        self.strokes = {}        # 页号 -> [Stroke / TextItem]
        self.undo_stack, self.redo_stack = [], []
        self.cache = OrderedDict()  # 页号 -> QImage 合成图（按书写分辨率渲染，可能比屏幕分辨率高）
        self.disp = OrderedDict()   # 页号 -> 显示图（正好是屏幕上的设备像素大小），见 _display
        self._draft = set()         # 显示图还是"草稿"（滚动中快速出的）的页，空闲时换成精细的
        self._scroll_dir = 1        # 最近一次滚动的方向（1 向下，-1 向上），预渲染时先顾这一边
        self._idle = QTimer(self)   # 空闲时的活，见 _idle_work
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self._idle_work)
        self._zoom_timer = QTimer(self)  # 连续缩放：它还在走就说明还没缩完，见 set_zoom
        self._zoom_timer.setSingleShot(True)
        self._zoom_timer.timeout.connect(self._zoom_settled)
        self._zoom_stale = {}       # 缩放开始前各页的显示图，缩放过程中拉伸它们顶着

        self.tool = "pen"        # pen / hl / eraser / lasso / line / arrow / rect / ellipse / text / mask / select
        self.color = "#111111"
        self.pen_width = 1.4     # 基准线宽（pt）
        self.cursor_style = "dot"
        self.hl_color = "#FFEE58"
        self.hl_width = 10.0     # 荧光笔宽度（pt）
        self.text_size = 14.0    # 文本字号（pt）
        self.pen_style = "f"     # 笔触风格，见 stroke.PEN_STYLES
        # 粗细与缩放的关系："page" = 粗细按页面算，放大后看起来也变粗（写出来的线始终一样粗）；
        # "screen" = 粗细按屏幕算，放大后看起来不变（实际画在页面上的线更细，适合放大写小字）
        self.width_mode = "page"
        # 书写分辨率：合成图按屏幕分辨率的多少倍来画，显示时再平滑缩小。
        # 倍数越高，笔迹和文字的边缘越细腻、锯齿感越少，但更占内存、翻页略慢。
        self.quality = 2.0
        # 笔迹平滑：0 = 关；越大越顺滑，但笔迹会略微滞后于笔尖
        self.smoothing = 0.0
        self._sm = None          # 平滑后的上一个位置
        self._raw = None         # 未平滑的最新位置

        self._mode = None        # None / pen / live / erase / pan / lasso / move / scale / text / tsel / region / menu
        self._page = -1
        self._cur = None         # 正在画的笔画
        self._painter = None     # 指向当前页合成图的 QPainter
        self._pressure = 0.5
        self._erased = []
        self._last = None        # 上一个输入位置（pt 或 px，视模式而定）
        self._start = None       # 按下时的位置（pt）
        self._tablet_down = False
        self._sel = []           # 套索选中的对象
        self._sel_page = -1
        self._xf = (0.0, 0.0, 1.0)  # 拖动选区时的临时变换：dx, dy, 缩放
        self._scale_corner = (1, 1)  # 正在拖哪个角缩放：(sx, sy)，见 _handle_rects
        self._lasso = []
        self._target = None      # 被点中的遮挡块
        self._menu_pos = None    # 右键菜单要弹出的位置
        self._region = None      # 套索圈住的一块区域（没圈到笔迹时）：(页号, QRectF)，用来截图提问
        self.hits = {}           # 搜索结果：页号 -> [QRectF]
        self.hit_cur = None      # 当前这一条：(页号, QRectF)
        self._chars = {}         # 页号 -> 该页 PDF 自带文字的字符表（Document.page_chars），选字工具用
        self._tsel = None        # 选中的文字：(页号, 起始字符下标, 结束字符下标)，含两端
        self._tsel_rects = []    # 选中文字的高亮矩形（pt，每行一块）
        self._tanchor = 0        # 拖选时按下位置对应的字符下标
        self._editor = None      # 页面上的文字输入框（_TextEditor），第一次用到时创建
        self._edit = None        # 正在输入的那段文字：页、位置、字号、颜色、被修改的对象（新建时为 None）
        self._edit_clock = QElapsedTimer()  # 上一次输入结束的时刻：紧接着的那一下点击只算"点别处确认"
        self._moving = QElapsedTimer()      # 最近一次滚动 / 缩放的时刻：刚动过时新页先出草稿，见 _display
        self._tablet_clock = QElapsedTimer()  # 最近一次数位板事件的时刻，用来发现"抬笔事件丢了"（见 _input_stuck）
        self._tap_clock = QElapsedTimer()   # 上一次按下的时刻和位置，用来判断双击
        self._tap_pos = None
        self._rw = [0, None]     # 正在拖片段的宽度手柄：[哪一边 (-1 / 1), 新的宽度 (pt)]
        self._grip = (0, 0)      # 正在拖区域的哪条边 / 哪个角，见 _region_grip
        self._rgn0 = None        # 开始拖区域时它原来的矩形
        self._update_cursor()

    # ------------------------------------------------------------------ 文档
    def set_document(self, doc):
        self.commit_text_edit()
        self._end_painter()
        self.doc = doc
        self.strokes, self.undo_stack, self.redo_stack = doc.load_strokes(), [], []
        self._sel = []
        self._region = None
        self._chars, self._tsel, self._tsel_rects = {}, None, []
        self.hits, self.hit_cur = {}, None
        self._drop_images()
        self.sx = self.sy = 0
        self.fit_width()
        self.historyChanged.emit(False, False)

    # ------------------------------------------------------------------ 布局
    def set_insets(self, left: int, top: int, right: int, bottom: int):
        """四边各留出多少像素不放页面（给浮在画布上的工具条让位置）。
        上 / 下的留空是加在整篇文档的开头 / 结尾的：滚到头时第一页不会被工具条挡住，滚动中页面照样从它下面穿过。
        左 / 右的留空让页面在剩下的宽度里居中，"适合宽度"也按剩下的宽度算。"""
        insets = (int(left), int(top), int(right), int(bottom))
        if insets == self.insets:
            return
        page = self.current_page() if self.tops else 0
        at_top = self.tops and self.sy <= self.tops[0]
        self.insets = insets
        if self.doc and self._fitted:
            self.fit_width()       # 原来是"适合宽度"的：留空变了就重新适合
        else:
            self._relayout()
        if self.doc and at_top:
            self.go_to_page(page)  # 原来停在开头：让第一页仍然正好露在工具条下面
        self.update()

    def _relayout(self):
        left, top, right, bottom = self.insets
        self.tops, y, wmax = [], GAP + top, 0
        if self.doc:
            for w, h in self.doc.sizes:
                self.tops.append(y)
                y += round(h * self.zoom) + GAP
                wmax = max(wmax, round(w * self.zoom))
        self.total_h = y + bottom
        self.content_w = wmax + 2 * MARGIN + left + right
        self._clamp_scroll()

    def _clamp_scroll(self):
        self.sy = max(0, min(self.sy, self.total_h - self.height()))
        self.sx = max(0, min(self.sx, self.content_w - self.width()))
        self.scrollRangeChanged.emit(max(0, self.total_h - self.height()), self.height(), self.sy)
        if self.doc:
            self.pageChanged.emit(self.current_page() + 1, len(self.doc))

    def page_rect(self, i: int) -> QRect:
        """第 i 页在控件坐标中的矩形。"""
        w, h = self.doc.sizes[i]
        pw, ph = round(w * self.zoom), round(h * self.zoom)
        left, _top, right, _bottom = self.insets
        if self.content_w <= self.width():
            x = left + (self.width() - left - right - pw) // 2
        else:
            x = left + MARGIN + (self.content_w - 2 * MARGIN - left - right - pw) // 2 - self.sx
        return QRect(x, self.tops[i] - self.sy, pw, ph)

    def _visible_pages(self, y0: int, y1: int):
        """与控件坐标 y0..y1 相交的页号范围。"""
        if not self.tops:
            return range(0)
        a = max(0, bisect.bisect_right(self.tops, y0 + self.sy) - 1)
        b = bisect.bisect_right(self.tops, y1 + self.sy)
        return range(a, b)

    def current_page(self) -> int:
        if not self.tops:
            return 0
        return max(0, bisect.bisect_right(self.tops, self.sy + self.height() // 2) - 1)

    def _page_at(self, pos: QPointF) -> int:
        for i in self._visible_pages(int(pos.y()), int(pos.y())):
            if self.page_rect(i).contains(pos.toPoint()):
                return i
        return -1

    # ------------------------------------------------------------------ 滚动 / 缩放
    def scroll_to(self, y: int):
        self.commit_text_edit()  # 输入框是钉在控件上的，页面一动就先把字落下
        if int(y) != self.sy:
            self._scroll_dir = 1 if int(y) > self.sy else -1
        self._moving.restart()
        self._idle.start(IDLE_MS)
        self.sy = int(y)
        self._clamp_scroll()
        self.update()

    def scroll_by(self, dx: int, dy: int):
        self.sx += int(dx)
        self.scroll_to(self.sy + dy)

    def go_to_page(self, i: int):
        if self.tops:
            self.scroll_to(self.tops[max(0, min(i, len(self.tops) - 1))] - GAP - self.insets[1])

    def set_zoom(self, zoom: float, anchor_y: int = None):
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        if self._mode and self._input_stuck():
            self._abort_input()
        if not self.doc or abs(zoom - self.zoom) < 1e-4 or self._mode:
            return
        self._fitted = False  # 手动缩放过了（fit_width 调完这里会再把它设回 True）
        self.commit_text_edit()
        self._end_painter()
        if anchor_y is None:
            anchor_y = self.height() // 2
        ratio = zoom / self.zoom
        # 连续缩放（Ctrl+滚轮）时，如果每一格都把可见的页重新渲染一遍，每格要卡两三百毫秒。
        # 所以先把缩放前的显示图留下，缩放过程中拉伸它们顶着（会有点糊），停下 ZOOM_SETTLE_MS 之后才真正重画。
        if not self._zoom_timer.isActive():
            self._zoom_stale = {}
            for i in self._visible_pages(0, self.height()):
                img = self.disp.get(i) or self.cache.get(i)
                if img is not None:
                    self._zoom_stale[i] = img
        self._zoom_timer.start(ZOOM_SETTLE_MS)
        self._moving.restart()
        self.zoom = zoom
        self._drop_images()
        self.sy = round((self.sy + anchor_y) * ratio - anchor_y)
        self.sx = round(self.sx * ratio)
        self._relayout()
        self._update_cursor()
        self.zoomChanged.emit(self.zoom)
        self.update()

    def _zoom_settled(self):
        """缩放停下来了：丢掉顶替用的旧图，按新的缩放真正重画。"""
        self._zoom_stale = {}
        self._moving.restart()  # 第一下先出草稿，马上再换精细的，手感上是"立刻变清楚"
        self._idle.start(IDLE_MS)
        self.update()

    def flush_zoom(self):
        """马上结束"缩放中"的状态（要落笔、要截图、要量位置之前调用）。"""
        if self._zoom_timer.isActive():
            self._zoom_timer.stop()
            self._zoom_stale = {}
            self.update()

    def fit_width(self):
        if not self.doc:
            self._relayout()
            self.update()
            return
        wmax = max(w for w, _ in self.doc.sizes)
        self._relayout()
        page = self.current_page()
        self.set_zoom((self.width() - self.insets[0] - self.insets[2] - 2 * MARGIN) / wmax)
        self._fitted = True
        self.go_to_page(page)
        self.zoomChanged.emit(self.zoom)
        self.update()

    def busy(self) -> bool:
        return self._mode is not None or self._edit is not None

    def get_view(self):
        """(顶部所在页, 该页内的纵向比例, 缩放)，用于下次打开时回到原位置。"""
        if not self.tops:
            return None
        i = max(0, bisect.bisect_right(self.tops, self.sy) - 1)
        h = max(1, round(self.doc.sizes[i][1] * self.zoom))
        return i, (self.sy - self.tops[i]) / h, self.zoom

    def set_view(self, page: int, frac: float, zoom: float):
        if not self.tops:
            return
        self.set_zoom(zoom)
        page = max(0, min(int(page), len(self.tops) - 1))
        self.scroll_to(self.tops[page] + round(frac * self.doc.sizes[page][1] * self.zoom))

    def set_strokes(self, strokes: dict):
        """整体替换笔迹（从自动保存的备份恢复时用）。"""
        self._end_painter()
        self.strokes, self.undo_stack, self.redo_stack = strokes, [], []
        self._sel = []
        self._drop_images()
        self.historyChanged.emit(False, False)
        self.update()

    # ------------------------------------------------------------------ 页面结构
    def _structure_changed(self):
        """页数或页面大小变了：页号对不上了，所以清空撤销记录。"""
        self._end_painter()
        if self._edit is not None:  # 正在输入的文字所在的页号可能已经变了：放弃这次输入
            self._edit = None
            self._editor.hide()
        self._sel = []
        self._region = None
        self._chars, self._tsel, self._tsel_rects = {}, None, []  # 页号和页面坐标都可能变了
        self.undo_stack, self.redo_stack = [], []
        self._drop_images()
        self._relayout()
        self.update()
        self.historyChanged.emit(False, False)
        self.changed.emit()
        self.structureChanged.emit()

    def insert_blank_after(self, i: int = None, template: str = None):
        if not self.doc or self._mode:
            return
        i = self.current_page() if i is None else i
        self.doc.insert_blank(i, template)
        self.strokes = {(k + 1 if k > i else k): v for k, v in self.strokes.items()}
        self._structure_changed()
        self.go_to_page(i + 1)

    def delete_page(self, i: int):
        if not self.doc or self._mode or len(self.doc) <= 1:
            return
        self.doc.delete_page(i)
        self.strokes = {(k - 1 if k > i else k): v for k, v in self.strokes.items() if k != i}
        self._structure_changed()

    def add_margin(self, side: str, i: int = None):
        """给当前页右侧或底部再加一块留白（页面原来那个方向尺寸的 40%）。"""
        if not self.doc or self._mode:
            return
        i = self.current_page() if i is None else i
        mr, mb = self.doc.page_margin(i)
        w, h = self.doc.sizes[i]
        if side == "right":
            self.set_margins(mr + round((w - mr) * 0.4), mb, i)
        else:
            self.set_margins(mr, mb + round((h - mb) * 0.4), i)

    def margin_loss(self, right: float, bottom: float, i: int = None):
        """把第 i 页的留白改成（右 right、下 bottom，pt）会丢掉哪些对象：中心落在被裁掉的那部分里的。
        只是缩小留白时才会有；返回对象列表。"""
        i = self.current_page() if i is None else i
        mr, mb = self.doc.page_margin(i)
        w, h = self.doc.sizes[i]
        nw, nh = w - mr + max(0.0, right), h - mb + max(0.0, bottom)
        out = []
        for s in self.strokes.get(i, []):
            c = s.bbox().center()
            if c.x() > nw or c.y() > nh:
                out.append(s)
        return out

    def set_margins(self, right: float, bottom: float, i: int = None):
        """把第 i 页的留白设成右侧 right、底部 bottom（pt，0 = 去掉）。缩小时落在裁掉部分里的对象一起删掉
        （见 margin_loss；要不要先问用户由调用的地方决定）。和别的页面结构改动一样，不能撤销。"""
        if not self.doc or self._mode:
            return
        i = self.current_page() if i is None else i
        mr, mb = self.doc.page_margin(i)
        right, bottom = max(0.0, float(right)), max(0.0, float(bottom))
        if abs(right - mr) < 0.01 and abs(bottom - mb) < 0.01:
            return
        self.commit_text_edit()
        view = self.get_view()
        lost = self.margin_loss(right, bottom, i)
        if lost:
            gone = set(map(id, lost))
            self.strokes[i] = [s for s in self.strokes.get(i, []) if id(s) not in gone]
        if abs(right - mr) >= 0.01:
            self.doc.set_margin(i, "right", right)
        if abs(bottom - mb) >= 0.01:
            self.doc.set_margin(i, "bottom", bottom)
        self._structure_changed()
        if right > mr and self.content_w > self.width():
            self.fit_width()  # 页面变宽后超出窗口：自动缩小到适合宽度
        self.set_view(view[0], view[1], self.zoom)

    # ------------------------------------------------------------------ 渲染
    def _render_page(self, i: int, scale: float, tw: int, th: int) -> QImage:
        """把第 i 页连同上面的笔迹画成一张 tw×th 的图（scale = 像素 / pt）。选中的对象不画（由 paintEvent 实时画）。"""
        img = self.doc.render(i, scale)
        if img.width() != tw or img.height() != th:  # 渲染结果可能差一两个像素，补齐到精确尺寸
            exact = QImage(tw, th, QImage.Format_RGB32)
            exact.fill(Qt.white)
            ep = QPainter(exact)
            ep.drawImage(0, 0, img)
            ep.end()
            img = exact
        img.setDevicePixelRatio(scale / self.zoom)  # 之后在图上作画都用逻辑坐标
        strokes = self.strokes.get(i)
        if strokes:
            skip = {id(s) for s in self._sel} if i == self._sel_page else ()
            p = self._page_painter(img)
            for masks in (False, True):  # 遮挡块最后画，才能盖住笔迹
                for s in strokes:
                    if (s.kind == "mask") == masks and id(s) not in skip:  # 选中的对象由 paintEvent 实时画
                        draw_item(p, s)
            p.end()
        return img

    @staticmethod
    def _trim(store: OrderedDict, budget: int, keep=()):
        """缓存超出像素预算时，从最久没用的页开始丢（keep 里的页不丢，至少留两页）。"""
        total = sum(im.width() * im.height() for im in store.values())
        for old in list(store):
            if total <= budget or len(store) <= 2:
                break
            if old in keep:
                continue
            total -= store[old].width() * store[old].height()
            del store[old]

    def _composite(self, i: int):
        """第 i 页的合成图（按书写分辨率画的"页面 + 笔迹"）。书写时新的笔画就是画在它上面。"""
        img = self.cache.get(i)
        if img is not None:
            self.cache.move_to_end(i)
            return img
        img = self._render_page(i, *self._render_plan(i))
        self.cache[i] = img
        # 书写分辨率为 1 时合成图本身就是显示图，没有另一份显示图缓存，预算合在一起用
        budget = CACHE_PIXELS + (DISP_PIXELS if self._render_plan(i)[1] == self._device_size(i)[0] else 0)
        self._trim(self.cache, budget, (i, self._page) if self._mode == "pen" else (i,))
        return img

    def _display(self, i: int, draft_ok: bool = False):
        """第 i 页用于上屏的图（尺寸正好等于它在屏幕上占的设备像素）。

        书写分辨率高于屏幕时，合成图先用面积平均缩小到屏幕分辨率再显示：
        这样每个屏幕像素是多个采样的平均，边缘更细腻；直接让绘图引擎缩小会丢细线。
        显示图单独缓存（self.disp），比合成图小得多，所以能多留十几页，往回滚不用重新渲染。

        draft_ok：正在滚动 / 缩放时，新进来的页先直接按屏幕分辨率渲染一张"草稿"顶上（快三四倍），
        记进 self._draft；停下来之后 _idle_work 再换成精细的。草稿也是 1:1 上屏的，只是边缘没那么细腻。
        """
        w, h = self._device_size(i)
        d = self.disp.get(i)
        if d is not None and d.width() == w:
            self.disp.move_to_end(i)
            return d
        dpr = self.devicePixelRatioF()
        scale, tw, th = self._render_plan(i)
        if tw == w:  # 书写分辨率为 1：合成图本身就是显示图
            return self._composite(i)
        if draft_ok and i not in self.cache:
            d = self._render_page(i, w / self.doc.sizes[i][0], w, h)
            self._draft.add(i)
        else:
            d = self._composite(i).scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self._draft.discard(i)
        d.setDevicePixelRatio(dpr)
        self.disp[i] = d
        self._trim(self.disp, DISP_PIXELS, (i,))
        return d

    def _drop_images(self, page: int = None):
        """页面的样子变了（笔迹改了、缩放变了…）：丢掉缓存的图，下次重画。page 为 None 表示全部。"""
        if page is None:
            self.cache.clear()
            self.disp.clear()
            self._draft.clear()
        else:
            self.cache.pop(page, None)
            self.disp.pop(page, None)
            self._draft.discard(page)

    def _idle_work(self):
        """空闲时（停止滚动 / 缩放一小会儿之后）一次做一件事，做完再约下一次，这样随时能被新的输入打断：
        1. 把屏幕上的草稿页换成精细的；2. 把屏幕上各页的合成图备好（落笔时不用等）；
        3. 预先渲染下一页和上一页（接着滚的时候不卡）。"""
        if not self.doc or not self.isVisible() or self._zoom_timer.isActive():
            return
        if self._mode or self._edit is not None:
            self._idle.start(300)  # 正在写字 / 输入：过会儿再说
            return
        vis = list(self._visible_pages(0, self.height()))
        if not vis:
            return
        for i in vis:
            if i in self._draft:
                self.disp.pop(i, None)
                self._display(i)
                self.update(self.page_rect(i))
                return self._idle.start(15)
        for i in vis:
            if i not in self.cache:
                self._composite(i)
                return self._idle.start(15)
        ahead = [vis[-1] + 1, vis[0] - 1] if self._scroll_dir >= 0 else [vis[0] - 1, vis[-1] + 1]
        for i in ahead:
            if 0 <= i < len(self.tops) and i not in self._draft and (
                    i not in self.disp and (self._render_plan(i)[1] != self._device_size(i)[0] or i not in self.cache)):
                self._display(i)
                return self._idle.start(15)

    def _sync_display(self, page: int, r: QRectF):
        """合成图的某一块（pt）刚被画过：把显示图里对应的一小块重新缩一遍。"""
        d = self.disp.get(page)
        hi = self.cache.get(page)
        if d is None or hi is None:
            return
        dpr = d.devicePixelRatio()
        s = self.zoom * dpr
        x0, y0 = max(0, math.floor(r.left() * s) - 2), max(0, math.floor(r.top() * s) - 2)
        x1, y1 = min(d.width(), math.ceil(r.right() * s) + 2), min(d.height(), math.ceil(r.bottom() * s) + 2)
        if x1 <= x0 or y1 <= y0:
            return
        kx, ky = hi.width() / d.width(), hi.height() / d.height()
        sx0, sy0 = math.floor(x0 * kx), math.floor(y0 * ky)
        sx1, sy1 = min(hi.width(), math.ceil(x1 * kx)), min(hi.height(), math.ceil(y1 * ky))
        sub = hi.copy(sx0, sy0, sx1 - sx0, sy1 - sy0).scaled(
            x1 - x0, y1 - y0, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        sub.setDevicePixelRatio(1)
        d.setDevicePixelRatio(1)
        p = QPainter(d)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(x0, y0, sub)
        p.end()
        d.setDevicePixelRatio(dpr)

    def _device_size(self, i: int):
        """第 i 页在屏幕上实际占的设备像素（宽, 高）。"""
        dpr = self.devicePixelRatioF()
        w, h = self.doc.sizes[i]
        return round(round(w * self.zoom) * dpr), round(round(h * self.zoom) * dpr)

    def _render_plan(self, i: int):
        """第 i 页合成图的 (渲染倍率 像素/pt, 宽, 高)。

        合成图的尺寸严格等于「屏幕像素 × 整数倍」：这样缩回屏幕分辨率时每个屏幕像素正好是
        n×n 个采样的平均，上屏时也不需要任何非整数缩放。非整数比例会让笔迹发虚。
        """
        dw, dh = self._device_size(i)
        q = max(1, int(round(self.quality)))
        while q > 1 and dw * dh * q * q > PAGE_PIXELS:  # 放大很多时自动降低倍数，控制内存
            q -= 1
        return dw * q / self.doc.sizes[i][0], dw * q, dh * q

    def set_quality(self, quality: float):
        if self._mode:
            return
        self._end_painter()
        self.quality = float(max(1, min(4, round(float(quality)))))
        self._drop_images()
        self.update()

    def set_smoothing(self, value: float):
        self.smoothing = max(0.0, min(0.9, float(value)))

    def event(self, ev):
        if ev.type() == QEvent.Type.DevicePixelRatioChange:  # 窗口拖到另一块缩放比不同的屏幕
            self._end_painter()
            self._drop_images()
            self._update_cursor()
            self.update()
        return super().event(ev)

    def _page_painter(self, img) -> QPainter:
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.zoom, self.zoom)  # 之后以 pt 为单位作画
        return p

    def _invalidate(self, page: int):
        self._drop_images(page)
        if 0 <= page < len(self.tops):
            self.update(self.page_rect(page))

    def paintEvent(self, ev):
        p = QPainter(self)
        r = ev.rect()
        p.fillRect(r, QColor(_theme.canvas_bg()))
        if not self.doc:
            return
        dpr = self.devicePixelRatioF()
        zooming = self._zoom_timer.isActive()
        # 刚滚动 / 缩放过，或者正在写字：还没有图的页允许先出草稿，免得卡住这一下
        # （正在写的那一页落笔时就备好了合成图，不受影响）
        moving = bool(self._mode) or (self._moving.isValid() and self._moving.elapsed() < IDLE_MS + 60)
        if self._draft and not self._idle.isActive():
            self._idle.start(IDLE_MS)
        for i in self._visible_pages(r.top(), r.bottom()):
            pr = self.page_rect(i)
            if pr.adjusted(-2, -2, 2, 4).intersects(r):
                p.fillRect(pr.adjusted(0, 2, 0, 3), QColor(0, 0, 0, 22))  # 页面下方的淡阴影
                if zooming:
                    # 还在连续缩放：拉伸缩放前的旧图顶着（没有旧图的页先留白），停下来再重画成清楚的
                    stale = self._zoom_stale.get(i)
                    p.fillRect(pr, Qt.white)
                    if stale is not None:
                        p.setRenderHint(QPainter.SmoothPixmapTransform)
                        p.drawImage(QRectF(pr), stale)
                        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
                else:
                    # 按设备像素 1:1 贴图：不经过任何缩放和插值，笔迹和文字才是锐利的
                    img = self._display(i, draft_ok=moving)
                    p.save()
                    p.scale(1 / dpr, 1 / dpr)
                    p.drawImage(QRect(round(pr.x() * dpr), round(pr.y() * dpr), img.width(), img.height()), img)
                    p.restore()
                p.setPen(QColor(PAGE_EDGE))
                p.drawRect(pr.adjusted(-1, -1, 0, 0))
        for i in self._visible_pages(r.top(), r.bottom()):  # 搜索结果高亮
            for rect in self.hits.get(i, ()):
                cur = self.hit_cur is not None and self.hit_cur[0] == i and self.hit_cur[1] == rect
                p.fillRect(self._pt_rect_to_widget(rect, i),
                           QColor(255, 120, 0, 130) if cur else QColor(255, 213, 0, 90))
        if self._tsel is not None and self._tsel[0] < len(self.tops):  # 选中的文字
            for rect in self._tsel_rects:
                p.fillRect(self._pt_rect_to_widget(rect, self._tsel[0]), QColor(10, 132, 255, 70))
        p.setRenderHint(QPainter.Antialiasing)
        if self._mode == "live" and (self._cur.kind == "mask" or len(self._cur.pts) > 1):  # 正在画的荧光笔 / 形状
            self._paint_on_page(p, self._page, r, lambda: draw_item(p, self._cur))
        if self._sel and self._sel_page < len(self.tops):
            dx, dy, s = self._xf
            ax, ay = self._sel_anchor()

            def draw_sel():
                p.translate(ax + dx, ay + dy)
                p.scale(s, s)
                p.translate(-ax, -ay)
                for it in self._sel:
                    draw_item(p, it)
            self._paint_on_page(p, self._sel_page, r, draw_sel)
            box = self._sel_widget_rect()
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawRect(box)
            p.setPen(QPen(QColor("#1976D2"), 1, Qt.DashLine))
            p.drawRect(box)
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.setBrush(QColor("#1976D2"))
            for _corner, rect in self._handle_rects():  # 四个角都能拖着缩放
                p.drawRect(rect)
            for _side, rect in self._width_handles():   # 粘贴的片段：左右两边中间的手柄改宽度
                p.drawRoundedRect(rect, 3, 3)
            if self._mode == "rewidth" and self._rw[1]:  # 正在拖宽度：虚线标出新的左右边界
                it = self._sel[0]
                left = it.x + it.w - self._rw[1] if self._rw[0] < 0 else it.x
                pr = self.page_rect(self._sel_page)
                z = self.zoom
                p.setBrush(QColor(10, 132, 255, 18))
                p.setPen(QPen(QColor("#0A84FF"), 1.5, Qt.DashLine))
                p.drawRect(QRectF(pr.x() + left * z, pr.y() + it.y * z, self._rw[1] * z, it.h * z))
        if self._region is not None and self._region[0] < len(self.tops):
            box = QRectF(self._pt_rect_to_widget(self._region[1], self._region[0]))
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.setBrush(QColor(10, 132, 255, 22))
            p.drawRect(box)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#0A84FF"), 1, Qt.DashLine))
            p.drawRect(box)
            p.setPen(QPen(QColor("#ffffff"), 1))  # 8 个手柄：拖边 / 角改大小
            p.setBrush(QColor("#0A84FF"))
            h = HANDLE_PX * 0.6
            for _grip, c in self._region_handles():
                p.drawRect(QRectF(c.x() - h / 2, c.y() - h / 2, h, h))
        if self._mode == "lasso" and len(self._lasso) > 1:
            pr = self.page_rect(self._page)
            poly = QPolygonF([QPointF(pr.x() + x * self.zoom, pr.y() + y * self.zoom) for x, y in self._lasso])
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#ffffff"), 1.5))
            p.drawPolyline(poly)
            p.setPen(QPen(QColor("#1976D2"), 1.5, Qt.DashLine))
            p.drawPolyline(poly)

    def _paint_on_page(self, p: QPainter, page: int, clip: QRect, fn):
        """在某一页的 pt 坐标系里叠画（裁剪到页面内）。"""
        pr = self.page_rect(page)
        p.save()
        p.setClipRect(pr.intersected(clip))
        p.translate(pr.topLeft())
        p.scale(self.zoom, self.zoom)
        fn()
        p.restore()

    def resizeEvent(self, ev):
        self._relayout()

    # ------------------------------------------------------------------ 工具
    def set_tool(self, tool: str):
        if tool != "lasso":
            self.clear_selection()
        self._set_text_sel(None)
        self.tool = tool
        self._update_cursor()

    def set_color(self, color: str):
        if self._edit is not None:  # 正在输入文字：工具栏的颜色是给输入框里选中的字用的
            self._editor.set_color(color)
            return
        self.color = color
        self._recolor(color, hl=False)
        self._update_cursor()

    def set_hl_color(self, color: str):
        self.hl_color = color
        self._recolor(color, hl=True)
        self._update_cursor()

    def set_width(self, width: float, hl_width: float = None, text_size: float = None):
        self.pen_width = width
        if hl_width:
            self.hl_width = hl_width
        if text_size:
            self.text_size = text_size
        self._update_cursor()

    def set_pen_style(self, style: str):
        self.pen_style = style

    def set_width_mode(self, mode: str):
        self.width_mode = mode
        self._update_cursor()

    def _w(self, base: float) -> float:
        """设定的粗细 -> 实际画到页面上的粗细（pt）。"""
        return base * BASE_ZOOM / self.zoom if self.width_mode == "screen" else base

    def set_cursor_style(self, style: str):
        self.cursor_style = style
        self._update_cursor()

    def _set_cursor(self, cursor):
        self._cursor = QCursor(cursor)
        self.setCursor(self._cursor)

    def _reapply_cursor(self, force: bool = False):
        """重新把光标交给系统。

        用笔的时候 Windows 会自己把光标换成箭头，而 Qt 以为光标没变、不会再设一次，
        于是自定义光标就"丢"了，直到重新选一次样式。这里在笔 / 鼠标活动时主动重设（限频）。
        """
        if force or self._cursor_clock.elapsed() >= 30:
            self._cursor_clock.restart()
            if self._cursor.shape() != Qt.BitmapCursor:
                # 十字、箭头这类标准光标：Qt 发现形状没变会直接跳过，先换成空白再换回来才会真的重设
                self.setCursor(Qt.BlankCursor)
            self.setCursor(self._cursor)

    def enterEvent(self, ev):
        super().enterEvent(ev)
        self._reapply_cursor(True)

    def _update_cursor(self, erasing: bool = None):
        """笔的光标样式可选（见 CURSOR_STYLES）；橡皮固定为圆圈，大小即擦除范围。"""
        if erasing is None:
            erasing = self.tool == "eraser"
        style = self.cursor_style
        hl = self.tool == "hl"
        color = self.hl_color if hl else self.color
        line_w = self._w(self.hl_width if hl else self.pen_width)
        if not erasing and self.tool in ("lasso", "mask") + SHAPES:
            self._set_cursor(Qt.CrossCursor)
            return
        if not erasing and self.tool in ("text", "select"):
            self._set_cursor(Qt.IBeamCursor)
            return
        if style == "arrow" and not erasing:
            self._set_cursor(Qt.ArrowCursor)
            return
        pm, hot = cursor_pixmap(style, color, line_w * self.zoom * 0.5, self.devicePixelRatioF(), erasing)
        self._set_cursor(QCursor(pm, hot[0], hot[1]))

    # ------------------------------------------------------------------ 选区（套索）
    def has_selection(self) -> bool:
        return bool(self._sel)

    def clear_selection(self):
        self.commit_text_edit()
        self._set_text_sel(None)
        if self._region is not None:
            self._region = None
            self.update()
        if self._sel:
            self._sel = []
            self._xf = (0.0, 0.0, 1.0)
            self._invalidate(self._sel_page)
            self.update()

    def _sel_bbox(self) -> QRectF:
        r = QRectF()
        for it in self._sel:
            r = r.united(it.bbox())
        return r

    def _sel_anchor(self):
        """缩放的固定点：选区左上角。"""
        r = self._sel_bbox()
        return r.left(), r.top()

    def _sel_widget_rect(self) -> QRectF:
        """选区外框（含拖动中的临时变换），控件坐标。"""
        r = self._sel_bbox()
        dx, dy, s = self._xf
        pr = self.page_rect(self._sel_page)
        z = self.zoom
        return QRectF(pr.x() + (r.left() + dx) * z, pr.y() + (r.top() + dy) * z,
                      r.width() * s * z, r.height() * s * z)

    def _handle_rects(self):
        """选区四个角上的缩放手柄：[((sx, sy), QRectF)]，sx / sy 为 -1（左 / 上）或 1（右 / 下）。
        拖哪个角，就以对角为固定点整体等比缩放。"""
        box = self._sel_widget_rect()
        out = []
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):  # 右下角排第一：选区很小、手柄重叠时优先它
            cx = box.right() if sx > 0 else box.left()
            cy = box.bottom() if sy > 0 else box.top()
            out.append(((sx, sy), QRectF(cx - HANDLE_PX / 2, cy - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX)))
        return out

    def _handle_rect(self) -> QRectF:
        """右下角的那个手柄。"""
        return self._handle_rects()[0][1]

    def _handle_at(self, pos: QPointF):
        """pos 落在哪个角的手柄上：(sx, sy)；都不在返回 None。"""
        for corner, rect in self._handle_rects():
            if rect.adjusted(-4, -4, 4, 4).contains(pos):
                return corner
        return None

    def _width_handles(self):
        """只选中了一个粘贴的片段时，左右两边中间各有一个改宽度的手柄：[(side, QRectF)]，side 为 -1 / 1。
        拖它不是缩放，而是按新的宽度重新排版（字号不变，行数跟着变）。"""
        if len(self._sel) != 1 or self._sel[0].kind != "rich" or not self._sel[0].src:
            return []
        box = self._sel_widget_rect()
        cy = box.center().y()
        return [(side, QRectF((box.left() if side < 0 else box.right()) - 4, cy - 12, 8, 24)) for side in (-1, 1)]

    def _width_handle_at(self, pos: QPointF):
        for side, rect in self._width_handles():
            if rect.adjusted(-5, -4, 5, 4).contains(pos):
                return side
        return 0

    def _finish_lasso(self):
        pts, self._lasso = self._lasso, []
        self.update()
        items = self.strokes.get(self._page) or []
        poly = QPolygonF([QPointF(x, y) for x, y in pts])
        area = poly.boundingRect()
        if max(area.width(), area.height()) * self.zoom < 6:
            # 只是点了一下：点中图片、粘贴的片段或文本框就选中它（这些东西个头大，圈起来费事）
            x, y = pts[0]
            for it in reversed(items):
                if it.kind in BOX_KINDS + ("text",) and it.bbox().contains(x, y):
                    self._sel, self._sel_page, self._xf = [it], self._page, (0.0, 0.0, 1.0)
                    self._invalidate(self._page)
                    break
            return
        if len(pts) < 3:
            return
        sel = []
        for it in items:
            if not area.intersects(it.bbox()):
                continue
            sp = it.sample_points()
            inside = sum(poly.containsPoint(QPointF(x, y), Qt.OddEvenFill) for x, y in sp)
            if inside >= SELECT_RATIO * len(sp):
                sel.append(it)
        if sel:
            self._sel, self._sel_page, self._xf = sel, self._page, (0.0, 0.0, 1.0)
            self._invalidate(self._page)
        elif min(area.width(), area.height()) * self.zoom > 14:
            # 没圈到笔迹：把圈出的范围当作"区域选择"，可以右键发给 Claude
            w, h = self.doc.sizes[self._page]
            self._region = (self._page, area.intersected(QRectF(0, 0, w, h)))

    # ------------------------------------------------------------------ 圈出的区域：拖边 / 角改大小，拖中间移动
    def _region_handles(self):
        """区域外框上 8 个手柄的中心点：[((fx, fy), QPointF)]，fx / fy 为 -1（左 / 上）、0（中）、1（右 / 下）。"""
        box = QRectF(self._pt_rect_to_widget(self._region[1], self._region[0]))
        xs = {-1: box.left(), 0: box.center().x(), 1: box.right()}
        ys = {-1: box.top(), 0: box.center().y(), 1: box.bottom()}
        return [((fx, fy), QPointF(xs[fx], ys[fy])) for fx in (-1, 0, 1) for fy in (-1, 0, 1) if fx or fy]

    def _region_grip(self, pos: QPointF):
        """pos 落在区域的哪里：(fx, fy) = 抓住了哪条边 / 哪个角；(0, 0) = 在框里面（移动）；None = 在外面。"""
        if self._region is None or self._region[0] >= len(self.tops):
            return None
        reach = HANDLE_PX * 0.75
        for grip, c in self._region_handles():  # 角和边中点的手柄优先
            if abs(pos.x() - c.x()) <= reach and abs(pos.y() - c.y()) <= reach:
                return grip
        box = QRectF(self._pt_rect_to_widget(self._region[1], self._region[0]))
        if not box.adjusted(-5, -5, 5, 5).contains(pos):
            return None
        fx = -1 if abs(pos.x() - box.left()) <= 5 else (1 if abs(pos.x() - box.right()) <= 5 else 0)
        fy = -1 if abs(pos.y() - box.top()) <= 5 else (1 if abs(pos.y() - box.bottom()) <= 5 else 0)
        return fx, fy  # 贴着边 = 拖那条边；都不贴 = (0, 0) 移动

    def _drag_region(self, x: float, y: float):
        """按抓住的边 / 角（或整体移动）把区域改到笔现在的位置，限制在页面内，不小于 REGION_MIN_PT。"""
        page, _old = self._region
        fx, fy = self._grip
        r0 = self._rgn0
        dx, dy = x - self._start[0], y - self._start[1]
        pw, ph = self.doc.sizes[page]
        if (fx, fy) == (0, 0):
            dx = max(-r0.left(), min(dx, pw - r0.right()))
            dy = max(-r0.top(), min(dy, ph - r0.bottom()))
            r = r0.translated(dx, dy)
        else:
            x0, y0, x1, y1 = r0.left(), r0.top(), r0.right(), r0.bottom()
            if fx < 0:
                x0 = max(0.0, min(x0 + dx, x1 - REGION_MIN_PT))
            elif fx > 0:
                x1 = min(pw, max(x1 + dx, x0 + REGION_MIN_PT))
            if fy < 0:
                y0 = max(0.0, min(y0 + dy, y1 - REGION_MIN_PT))
            elif fy > 0:
                y1 = min(ph, max(y1 + dy, y0 + REGION_MIN_PT))
            r = QRectF(x0, y0, x1 - x0, y1 - y0)
        self._region = (page, r)
        self.update()

    # ------------------------------------------------------------------ 选字（PDF 自带的文字）
    def _page_chars(self, page: int):
        if page not in self._chars:
            self._chars[page] = self.doc.page_chars(page)
        return self._chars[page]

    def _char_at(self, page: int, x: float, y: float) -> int:
        """离 (x, y) 最近的字符的下标；这一页没有文字时返回 -1。竖直方向的距离加倍，优先落在同一行。"""
        best, best_d = -1, None
        for n, (x0, y0, x1, y1, *_rest) in enumerate(self._page_chars(page)):
            d = max(x0 - x, x - x1, 0.0) + 2.0 * max(y0 - y, y - y1, 0.0)
            if best_d is None or d < best_d:
                best, best_d = n, d
                if d == 0.0:
                    break
        return best

    def _set_text_sel(self, sel):
        """设置 / 清除选中的文字，并算好每行一块的高亮矩形。"""
        if sel is None and self._tsel is None:
            return
        self._tsel, self._tsel_rects = sel, []
        if sel is not None:
            page, a, b = sel
            chars = self._page_chars(page)
            cur, cur_line = None, None
            for x0, y0, x1, y1, _c, _blk, line in chars[a:b + 1]:
                r = QRectF(x0, y0, x1 - x0, y1 - y0)
                if line != cur_line:
                    if cur is not None:
                        self._tsel_rects.append(cur)
                    cur, cur_line = r, line
                else:
                    cur = cur.united(r)
            if cur is not None:
                self._tsel_rects.append(cur)
        self.update()

    def selected_text(self) -> str:
        """选字工具选中的文字。同一段里换行处：中日韩文字直接相连，其他文字补一个空格；段与段之间换行。"""
        if self._tsel is None:
            return ""
        page, a, b = self._tsel
        out, prev = [], None
        for _x0, _y0, _x1, _y1, c, blk, line in self._page_chars(page)[a:b + 1]:
            if prev is not None and line != prev[1]:
                last = out[-1] if out else ""
                if blk != prev[0]:
                    out.append("\n")
                elif last and not last.isspace() and not c.isspace() and ord(last) < 0x2E80 and ord(c[:1] or " ") < 0x2E80:
                    out.append(" ")
            out.append(c)
            prev = (blk, line)
        return "".join(out).strip()

    def text_sel_target(self):
        """选中文字所在的 (页号, 包住它的 QRectF)；没有选中文字时返回 None。"""
        if self._tsel is None or not self._tsel_rects:
            return None
        box = self._tsel_rects[0]
        for r in self._tsel_rects[1:]:
            box = box.united(r)
        return self._tsel[0], box

    # ------------------------------------------------------------------ 截图（发给 Claude）
    def ask_target(self):
        """当前可以拿去提问的范围：(页号, QRectF)；没有选区也没有区域时返回 None。"""
        if self._sel:
            return self._sel_page, self._sel_bbox()
        return self._region

    def grab_image(self, page: int, rect: QRectF = None, max_px: int = 1568) -> QImage:
        """把某一页（或其中一块）连同笔迹渲染成图片。遮挡块不画，让 Claude 看到完整内容。"""
        w, h = self.doc.sizes[page]
        full = QRectF(0, 0, w, h)
        r = full if rect is None else rect.adjusted(-8, -8, 8, 8).intersected(full)
        scale = max(1.0, min(3.0, max_px / max(r.width(), r.height(), 1.0)))
        img = self.doc.render(page, scale)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(scale, scale)
        for it in self.strokes.get(page, []):
            if it.kind != "mask":
                draw_item(p, it)
        p.end()
        return img.copy(QRect(round(r.x() * scale), round(r.y() * scale),
                              max(1, round(r.width() * scale)), max(1, round(r.height() * scale))))

    def add_text_block(self, text: str):
        """把一段文字（侧栏 Claude 面板里的回答）排版好贴到当前页窗口中央，并选中它方便拖动。"""
        if self.doc and not self._mode:
            self.paste_rich(text)

    def _apply_sel_transform(self):
        dx, dy, s = self._xf
        self._xf = (0.0, 0.0, 1.0)
        if abs(dx) < 1e-6 and abs(dy) < 1e-6 and abs(s - 1) < 1e-6:
            return
        ax, ay = self._sel_anchor()
        f = lambda x, y: (ax + dx + (x - ax) * s, ay + dy + (y - ay) * s)
        mods = []
        for it in self._sel:
            old = it.get_state()
            it.transform(f, s)
            mods.append((it, old, it.get_state()))
        self._push(("mod", self._sel_page, mods))
        self.update()

    def _recolor(self, color: str, hl: bool):
        """选中对象时点颜色 = 给它们改色（荧光色只改荧光笔，普通色改其余）。"""
        mods = []
        for it in self._sel:
            if it.kind not in ("mask",) + BOX_KINDS and (it.kind == "hl") == hl and it.color != color:
                old = it.get_state()
                it.color = color
                mods.append((it, old, it.get_state()))
        if mods:
            self._push(("mod", self._sel_page, mods))
            self.update()

    # ------------------------------------------------------------------ 复制 / 剪切 / 粘贴
    def _show_menu(self, pos: QPointF):
        self._tablet_down = False
        menu = QMenu(self)
        if self._tsel is not None:  # 选中了文字：只有"问"和"复制"
            a_ask = menu.addAction(self.ask_label)
            a_copy = menu.addAction(T("复制") + "\tCtrl+C")
            chosen = self._exec_menu(menu, self.mapToGlobal(pos.toPoint()))
            if chosen is a_ask:
                self.askRequested.emit()
            elif chosen is a_copy:
                self.copy_selection()
            return
        has_sel = bool(self._sel)
        a_ask = menu.addAction(self.ask_label)
        a_ask.setEnabled(self.ask_target() is not None)
        menu.addSeparator()
        a_copy = menu.addAction(T("复制") + "\tCtrl+C")
        a_cut = menu.addAction(T("剪切") + "\tCtrl+X")
        a_paste = menu.addAction(T("粘贴") + "\tCtrl+V")
        menu.addSeparator()
        a_del = menu.addAction(T("删除") + "\tDelete")
        a_copy.setEnabled(self.ask_target() is not None)
        for a in (a_cut, a_del):
            a.setEnabled(has_sel)
        a_paste.setEnabled(self.can_paste())
        chosen = self._exec_menu(menu, self.mapToGlobal(pos.toPoint()))
        if chosen is a_ask:
            self.askRequested.emit()
        elif chosen is a_copy:
            self.copy_selection()
        elif chosen is a_cut:
            self.cut_selection()
        elif chosen is a_paste:
            self.paste(pos)
        elif chosen is a_del:
            self.delete_selection()

    def _exec_menu(self, menu, global_pos):
        return menu.exec(global_pos)

    def copy_selection(self):
        """复制。选中的范围同时以图片形式放进系统剪贴板，可以直接粘贴到 Claude、微信、Word 等别的程序；
        选中的笔迹另存一份在程序内部，用于在 RuiPDF 里粘贴成可编辑的对象。"""
        if self._tsel is not None:  # 选字工具选中的文字：以文本形式复制
            QGuiApplication.clipboard().setText(self.selected_text())
            return
        target = self.ask_target()
        if target is None:
            return
        mime = QMimeData()
        mime.setImageData(self.grab_image(*target))
        if self._sel:
            r = self._sel_bbox()
            # 按页面上的先后顺序存，粘贴后叠放次序不变
            order = {id(s): i for i, s in enumerate(self.strokes.get(self._sel_page, []))}
            items = sorted(self._sel, key=lambda s: order.get(id(s), 0))
            Canvas.clipboard = ([it.to_json() for it in items], (r.left(), r.top(), r.width(), r.height()))
            Canvas._paste_count = 0
            # 在系统剪贴板上留个记号：粘贴时据此判断剪贴板里还是不是我们自己放的这份
            Canvas._clip_token = uuid.uuid4().hex.encode()
            mime.setData(OWN_MIME, Canvas._clip_token)
        # 只圈了一块区域、没有笔迹时只有图片（没有记号）：粘贴它得到的是那一块的截图
        QGuiApplication.clipboard().setMimeData(mime)

    def cut_selection(self):
        self.copy_selection()
        self.delete_selection()

    def _paste_spot(self, pos: QPointF = None):
        """新内容该放在哪：(页号, x, y)，x / y 是它的中心（pt）。
        pos 为右键菜单的位置；没有就放在当前页的窗口中央，连续粘贴时错开一点。"""
        page = self._page_at(pos) if pos is not None else -1
        if page >= 0:
            x, y = self._to_pt(pos, page)
        else:
            page = self.current_page()
            pr = self.page_rect(page)
            shift = 12 * Canvas._paste_count
            x = (self.width() / 2 - pr.x()) / self.zoom + shift
            y = (self.height() / 2 - pr.y()) / self.zoom + shift
            Canvas._paste_count += 1
        return page, x, y

    def _adopt(self, page: int, items):
        """把一批新对象加到某一页并选中它们，切到套索工具方便接着拖动。"""
        self.clear_selection()
        self.strokes.setdefault(page, []).extend(items)
        self._sel, self._sel_page, self._xf = items, page, (0.0, 0.0, 1.0)
        self._invalidate(page)
        self._push(("addn", page, items))
        self.toolRequested.emit("lasso")
        self.update()

    def _clip_is_ours(self, mime) -> bool:
        return (Canvas.clipboard is not None and mime is not None and mime.hasFormat(OWN_MIME)
                and bytes(mime.data(OWN_MIME)) == Canvas._clip_token)

    def can_paste(self) -> bool:
        mime = QGuiApplication.clipboard().mimeData()
        return Canvas.clipboard is not None or (
            mime is not None and (mime.hasImage() or mime.hasUrls() or bool(mime.text().strip())))

    def paste(self, pos: QPointF = None):
        """粘贴。看系统剪贴板里是什么：
        我们自己复制的笔迹 -> 原样粘贴成可编辑的对象；图片（截图、从别处复制的图、图片文件）-> 插入图片。
        粘贴的内容自动成为选区。"""
        if not self.doc or self._mode:
            return
        self.commit_text_edit()
        mime = QGuiApplication.clipboard().mimeData()
        if self._clip_is_ours(mime):
            return self._paste_items(pos)
        if mime is not None:
            files = [u.toLocalFile() for u in mime.urls() if u.toLocalFile().lower().endswith(IMAGE_EXTS)]
            if files:
                for path in files:
                    self.insert_image(path, pos)
                return
            if mime.text().strip():  # 文字优先于图片：从网页复制一段回答时，剪贴板里常常两样都有
                return self.paste_rich(mime.text(), mime.html() if mime.hasHtml() else "", pos)
            if mime.hasImage():
                return self.insert_image(QGuiApplication.clipboard().image(), pos)
        if Canvas.clipboard is not None:  # 系统剪贴板里没有能贴的：退回上次在程序里复制的笔迹
            self._paste_items(pos)

    def paste_rich(self, text: str, source_html: str = "", pos: QPointF = None):
        """把一段文字（AI 的回答：Markdown、LaTeX 公式、表格、代码）排版好贴到页面上。

        排版在浏览器引擎里进行，要等一下（第一次几秒，之后一秒左右），排好后自动出现并被选中。
        宽度、字体、字号见 Canvas.paste_width / paste_font / paste_size（设置里可改）。
        """
        if not self.doc or not text.strip():
            return
        self.commit_text_edit()
        from . import richpaste  # 用到时才加载
        page, x, y = self._paste_spot(pos)
        pw, _ph = self.doc.sizes[page]
        width = max(120.0, min(pw - 16, pw * Canvas.paste_width / 100))
        size = Canvas.paste_size or max(9.0, min(16.0, pw / 55))  # 自动：A4 竖版约 10.8 pt，宽屏幻灯片 16 pt
        doc, font = self.doc, Canvas.paste_font
        src = richpaste.to_source(text, source_html)
        self.notice.emit(T("正在排版要粘贴的内容…"))
        richpaste.render(richpaste.markdown_to_body(src), width, font, size,
                         lambda pdf: self._rich_ready(pdf, src, font, size, doc, page, x, y))

    def _rich_ready(self, pdf, src: str, font: str, size: float, doc, page: int, x: float, y: float):
        if doc is not self.doc or page >= len(self.tops):
            return  # 等排版的这会儿文档已经换了 / 页没了
        if pdf is None:
            self.notice.emit(T("排版失败，没有粘贴。"))
            return
        if self._mode or self._edit is not None:  # 正在写字 / 输入：等这一下结束再放，免得打断
            QTimer.singleShot(250, lambda: self._rich_ready(pdf, src, font, size, doc, page, x, y))
            return
        item = RichItem(pdf, 0, 0, 1, 1, src, font, size)
        nw, nh = item.natural_size()
        pw, ph = self.doc.sizes[page]
        k = min(1.0, (pw - 8) / nw)  # 有很宽的公式或表格时内容会比设定的宽：缩到页面内
        k = min(k, max(0.7, (ph - 8) / (nh * k)) * k) if nh * k > ph - 8 else k  # 太长：最多缩到七成
        item.w, item.h = nw * k, nh * k
        item.x = max(4.0, min(x - item.w / 2, pw - item.w - 4))
        item.y = max(4.0, min(y - item.h / 2, max(4.0, ph - item.h - 4)))
        self._adopt(page, [item])
        if item.h > ph - 8:
            self.notice.emit(T("内容比这一页长，超出页面的部分看不到：可以拉右下角缩小，或先用“页面 → 底部加留白”。"))
        else:
            self.notice.emit(T("已粘贴。拖动移动，拖四角缩放，拖左右两边改宽度，双击改内容。"))

    def _rerender(self, item, page: int, src: str, width: float, keep_right: bool = False):
        """用原文重新排版一个片段（改了内容，或者改了宽度），排好后换掉它的数据。

        width 是它在页面上的新宽度（pt）。片段可能被整体缩放过：缩放比例保持不变，
        所以拿去排版的宽度要先除以这个比例，字看起来还是原来那么大。
        keep_right：右边不动（拖的是左边的手柄）；否则左边不动。排版是异步的，等一下才会变。
        """
        from . import richpaste
        nw, _nh = item.natural_size()
        k = item.w / nw if nw > 0 else 1.0
        pw, _ph = self.doc.sizes[page]
        # 早先粘贴的片段没有记下字体字号：按现在的设置来
        size = item.size or (Canvas.paste_size or max(9.0, min(16.0, pw / 55)))
        font = item.font if item.size else Canvas.paste_font
        doc = self.doc
        self.notice.emit(T("正在重新排版…"))

        def ready(pdf):
            if doc is not self.doc or not any(it is item for it in self.strokes.get(page, [])):
                return  # 等排版的这会儿文档换了，或者这个片段已经被删掉了
            if pdf is None:
                self.notice.emit(T("重新排版失败，内容没有变。"))
                return
            if self._mode or self._edit is not None:
                QTimer.singleShot(250, lambda: ready(pdf))
                return
            old = item.get_state()
            right = item.x + item.w
            n2w, n2h = RichItem(pdf, 0, 0, 1, 1).natural_size()
            w, h = n2w * k, n2h * k
            item.set_state((right - w if keep_right else item.x, item.y, w, h, pdf, src))
            item.font, item.size = font, size
            self._push(("mod", page, [(item, old, item.get_state())]))
            self._invalidate(page)
            self.update()
            self.notice.emit(T("已重新排版。"))

        richpaste.render(richpaste.markdown_to_body(src), max(60.0, width / k), font, size, ready)

    def _paste_items(self, pos: QPointF = None):
        data, (ox, oy, bw, bh) = Canvas.clipboard
        page, x, y = self._paste_spot(pos)
        w, h = self.doc.sizes[page]
        tx = max(4.0, min(x - bw / 2, w - bw - 4))  # 尽量留在页面内
        ty = max(4.0, min(y - bh / 2, h - bh - 4))
        dx, dy = tx - ox, ty - oy
        items = [item_from_json(d) for d in data]
        for it in items:
            it.transform(lambda px, py: (px + dx, py + dy), 1.0)
        self._adopt(page, items)

    def place_box(self, item, pos: QPointF = None):
        """把一个图片 / 片段对象放到页面上（位置见 _paste_spot），尽量整个留在页面内。"""
        page, x, y = self._paste_spot(pos)
        w, h = self.doc.sizes[page]
        item.x = max(4.0, min(x - item.w / 2, w - item.w - 4))
        item.y = max(4.0, min(y - item.h / 2, h - item.h - 4))
        self._adopt(page, [item])

    def insert_image(self, source, pos: QPointF = None) -> bool:
        """插入图片。source 是 QImage 或图片文件路径。默认按 96 dpi 的自然大小，
        但不超过页面宽度的 60%、高度的 50%，之后可以用套索拖动、拉右下角缩放。"""
        if not self.doc or self._mode:
            return False
        self.commit_text_edit()
        if isinstance(source, QImage):
            img, data, jpeg = source, None, False
        else:
            try:
                with open(source, "rb") as f:
                    data = f.read()
            except OSError:
                data = b""
            img = QImage.fromData(data)
            jpeg = str(source).lower().endswith((".jpg", ".jpeg"))
        if img.isNull():
            self.notice.emit(T("这不是能识别的图片。"))
            return False
        if max(img.width(), img.height()) > IMAGE_MAX_PX:  # 太大的图先缩小，免得 PDF 和自动备份跟着变得很大
            img = img.scaled(IMAGE_MAX_PX, IMAGE_MAX_PX, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            data = None
        if data is None:
            buf = QBuffer()
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "JPG" if jpeg else "PNG", 90 if jpeg else -1)
            data = bytes(buf.data())
        page = self.current_page() if pos is None or self._page_at(pos) < 0 else self._page_at(pos)
        pw, ph = self.doc.sizes[page]
        w, h = img.width() * 0.75, img.height() * 0.75
        k = min(1.0, pw * 0.6 / w, ph * 0.5 / h)
        item = ImageItem(data, 0, 0, w * k, h * k)
        item._img = img
        self.place_box(item, pos)
        return True

    def delete_selection(self):
        if not self._sel or self._mode:
            return
        items = self.strokes.get(self._sel_page, [])
        ids = {id(s) for s in self._sel}
        removed = []
        for idx in range(len(items) - 1, -1, -1):
            if id(items[idx]) in ids:
                removed.append((idx, items[idx]))
                del items[idx]
        page = self._sel_page
        self._sel = []
        self._invalidate(page)
        if removed:
            self._push(("del", page, removed))

    # ------------------------------------------------------------------ 书写
    def _to_pt(self, pos: QPointF, page: int):
        pr = self.page_rect(page)
        return (pos.x() - pr.x()) / self.zoom, (pos.y() - pr.y()) / self.zoom

    def _pt_rect_to_widget(self, r: QRectF, page: int) -> QRect:
        pr = self.page_rect(page)
        z = self.zoom
        return QRect(math.floor(pr.x() + r.x() * z) - 1, math.floor(pr.y() + r.y() * z) - 1,
                     math.ceil(r.width() * z) + 3, math.ceil(r.height() * z) + 3)

    def _end_painter(self):
        if self._painter:
            self._painter.end()
            self._painter = None

    def _down(self, pos: QPointF, pressure: float, erase: bool):
        if not self.doc or self._mode:
            return
        self.flush_zoom()
        if self._edit is not None or (self._edit_clock.isValid() and self._edit_clock.elapsed() < 200):
            self.commit_text_edit()  # 正在输入文字时点别处：只确认输入，这一下不再做别的
            self._edit_clock.invalidate()
            return
        # 是不是双击：和上一次按下隔得够近、位置也够近（笔没有系统的双击事件，自己判断）
        double = (self._tap_clock.isValid() and self._tap_clock.elapsed() < 450 and self._tap_pos is not None
                  and abs(pos.x() - self._tap_pos.x()) + abs(pos.y() - self._tap_pos.y()) < 12)
        self._tap_clock.restart()
        self._tap_pos = QPointF(pos)
        if double:
            self._tap_clock.invalidate()  # 三连击不算两次双击
        if erase and self.tool == "select" and self._tsel is not None:  # 选中文字后右键 / 笔侧键：弹菜单
            self._mode, self._menu_pos = "menu", pos
            return
        # 套索工具下的右键（或按住笔侧键点）：在选区上 = 弹菜单；有可粘贴的内容 = 弹"粘贴"
        if erase and self.tool == "lasso":
            on_sel = bool(self._sel) and self._sel_widget_rect().adjusted(-4, -4, 4, 4).contains(pos)
            if self._region is not None:
                box = self._pt_rect_to_widget(self._region[1], self._region[0]).adjusted(-4, -4, 4, 4)
                on_sel = on_sel or box.contains(pos.toPoint())
            if on_sel or (self.can_paste() and self._page_at(pos) >= 0):
                if not on_sel:
                    self.clear_selection()
                self._mode, self._menu_pos = "menu", pos  # 松开后再弹，避免菜单吞掉抬笔事件
                return
        # 套索：先看是不是点在已有选区上（移动 / 缩放）
        if self._sel and self.tool == "lasso" and not erase:
            self._page = self._sel_page
            self._start = self._to_pt(pos, self._page)
            corner = self._handle_at(pos)
            if corner is not None:
                self._mode, self._scale_corner = "scale", corner
                return
            side = self._width_handle_at(pos)
            if side:
                self._mode, self._rw = "rewidth", [side, None]
                return
            if self._sel_widget_rect().contains(pos):
                # 双击选中的文本框 / 粘贴的片段 = 改它的内容（松开后再进入编辑）
                editable = len(self._sel) == 1 and self._sel[0].kind in ("text", "rich")
                self._mode = "dblclick" if double and editable else "move"
                return
        # 套索圈出的区域：抓住边 / 角 = 改大小，抓住中间 = 移动
        if self.tool == "lasso" and not erase:
            grip = self._region_grip(pos)
            if grip is not None:
                self._page = self._region[0]
                self._start = self._to_pt(pos, self._page)
                self._grip, self._rgn0 = grip, QRectF(self._region[1])
                self._mode = "region"
                return
        self.clear_selection()
        page = self._page_at(pos)
        if page < 0:
            return
        self._page = page
        x, y = self._to_pt(pos, page)
        self._start = (x, y)
        tool = self.tool
        if erase or tool == "eraser":
            self._mode, self._erased, self._last = "erase", [], (x, y)
            self._update_cursor(True)
            self._erase(x, y)
        elif tool == "lasso":
            self._mode, self._lasso = "lasso", [(x, y)]
        elif self._mask_at(page, x, y, any_state=(tool == "mask")):
            # 点在遮住的块上 = 揭开（任何工具都行）；用遮挡工具点已揭开的块 = 重新遮住
            self._mode, self._target = "masktap", self._mask_at(page, x, y, any_state=(tool == "mask"))
        elif tool == "mask":
            self._mode = "live"
            self._cur = MaskItem(x, y, x, y)
        elif tool == "select":
            self._tanchor = self._char_at(page, x, y)
            if self._tanchor < 0:
                self.notice.emit(T("这一页没有可以选的文字（扫描件或图片），请用套索截图"))
            else:
                self._mode = "tsel"
        elif tool == "text":
            self._mode = "text"  # 抬笔后再弹输入框，避免弹窗吞掉抬笔事件
        elif tool == "hl":
            self._mode = "live"
            self._cur = Stroke(self.hl_color, self._w(self.hl_width), "hl")
            self._cur.add(x, y, 0.5)
        elif tool in SHAPES:
            self._mode = "live"
            self._cur = make_shape(tool, x, y, x, y, self.color, self._w(self.pen_width))
        else:
            self._mode = "pen"
            self._pressure = pressure
            self._cur = Stroke(self.color, self._w(self.pen_width), "pen", self.pen_style)
            self._cur.add(x, y, pressure)
            self._sm = self._raw = (x, y)
            self._painter = self._page_painter(self._composite(page))

    def _move(self, pos: QPointF, pressure: float):
        mode = self._mode
        if mode is None or mode in ("text", "menu"):
            return
        x, y = self._to_pt(pos, self._page)
        if mode == "masktap":
            if math.hypot(x - self._start[0], y - self._start[1]) * self.zoom > 8:
                self._target = None  # 拖远了就不算点击
            return
        if mode == "erase":
            self._erase(x, y)
        elif mode == "region":
            self._drag_region(x, y)
        elif mode == "rewidth":
            it = self._sel[0]
            w = x - it.x if self._rw[0] > 0 else it.x + it.w - x
            self._rw[1] = max(60.0, min(w, self.doc.sizes[self._sel_page][0]))
            self.update()
        elif mode == "dblclick":
            if math.hypot(x - self._start[0], y - self._start[1]) * self.zoom > 6:
                self._mode = "move"  # 第二下按住拖开了：还是当移动
        elif mode == "tsel":
            if self._tsel is None and math.hypot(x - self._start[0], y - self._start[1]) * self.zoom < 3:
                return  # 还没拖开：不算选
            i = self._char_at(self._page, x, y)
            sel = (self._page, min(i, self._tanchor), max(i, self._tanchor))
            if sel != self._tsel:
                self._set_text_sel(sel)
        elif mode == "lasso":
            self._lasso.append((x, y))
            self.update()
        elif mode == "move":
            self._xf = (x - self._start[0], y - self._start[1], 1.0)
            self.update()
        elif mode == "scale":
            r = self._sel_bbox()
            sx, sy = self._scale_corner
            # 固定点 = 被拖的那个角的对角；笔离固定点越远（沿拖动方向量）放得越大
            fx = r.left() if sx > 0 else r.right()
            fy = r.top() if sy > 0 else r.bottom()
            base = r.width() + r.height()
            s = (sx * (x - fx) + sy * (y - fy)) / base if base > 0 else 1.0
            s = max(0.1, min(10.0, s))
            # 临时变换是"绕左上角缩放再平移"：绕别的点缩放 = 绕左上角缩放 + 把那个点挪回原位
            self._xf = ((fx - r.left()) * (1 - s), (fy - r.top()) * (1 - s), s)
            self.update()
        elif mode == "live":
            old = self._cur.bbox()
            if self._cur.kind == "mask":
                self._cur = MaskItem(*self._start, x, y)
            elif self._cur.kind == "hl":
                lx, ly, _ = self._cur.pts[-1]
                if math.hypot(x - lx, y - ly) * self.zoom < 1.0:
                    return
                self._cur.add(x, y, 0.5)
            else:
                self._cur = make_shape(self.tool, *self._start, x, y, self.color, self._w(self.pen_width))
            self.update(self._pt_rect_to_widget(old.united(self._cur.bbox()), self._page))
        elif mode == "pen":
            self._raw = (x, y)
            if self.smoothing > 0:  # 位置低通滤波：削掉手抖和采样造成的小折线
                a = 1.0 - self.smoothing
                x = self._sm[0] + (x - self._sm[0]) * a
                y = self._sm[1] + (y - self._sm[1]) * a
                self._sm = (x, y)
            lx, ly, _ = self._cur.pts[-1]
            if math.hypot(x - lx, y - ly) * self.zoom < 0.4:  # 小于 0.4px 的抖动忽略
                return
            self._pressure = 0.6 * self._pressure + 0.4 * pressure  # 压感低通滤波
            self._cur.add(x, y, self._pressure)
            dirty = draw_piece(self._painter, self._cur, len(self._cur.pts) - 1)
            self._sync_display(self._page, dirty)
            self.update(self._pt_rect_to_widget(dirty, self._page))

    def _up(self):
        mode, self._mode = self._mode, None
        if mode == "pen":
            if self.smoothing > 0 and self._raw is not None:  # 补上平滑造成的滞后，笔画终点落在真实位置
                lx, ly, lp = self._cur.pts[-1]
                if math.hypot(self._raw[0] - lx, self._raw[1] - ly) * self.zoom >= 0.4:
                    self._cur.add(self._raw[0], self._raw[1], lp)
                    d0 = draw_piece(self._painter, self._cur, len(self._cur.pts) - 1)
                    self._sync_display(self._page, d0)
                    self.update(self._pt_rect_to_widget(d0, self._page))
            dirty = draw_tail(self._painter, self._cur)
            self._end_painter()
            self._sync_display(self._page, dirty)
            self.update(self._pt_rect_to_widget(dirty, self._page))
            self._commit(self._cur, draw=False)
            self._cur = None
        elif mode == "live":
            cur, self._cur = self._cur, None
            self.update(self._pt_rect_to_widget(cur.bbox(), self._page))
            r = cur.bbox()
            if cur.kind == "mask":
                ok = min(cur.x1 - cur.x0, cur.y1 - cur.y0) * self.zoom > 5
            else:
                ok = len(cur.pts) > 1 and (r.width() + r.height() - 8 * cur.width) * self.zoom > 4
            if ok:
                self._commit(cur)
        elif mode == "masktap":
            if self._target is not None:
                self._target.shown = not self._target.shown
                self._invalidate(self._page)
            self._target = None
        elif mode == "erase":
            if self._erased:
                self._push(("del", self._page, self._erased))
            self._erased = []
            self._update_cursor()
        elif mode == "lasso":
            self._finish_lasso()
        elif mode in ("move", "scale"):
            self._apply_sel_transform()
        elif mode == "rewidth":
            side, w = self._rw
            self._rw = [0, None]
            self.update()
            if self._sel and w and abs(w - self._sel[0].w) > 1.5:
                self._rerender(self._sel[0], self._sel_page, self._sel[0].src, w, keep_right=side < 0)
        elif mode == "dblclick":
            item, page = self._sel[0], self._sel_page
            self._sel = []  # 直接放下选区（不走 clear_selection，免得动别的状态）
            self._invalidate(page)
            self.edit_item(item, page)
        elif mode == "text":
            self._text_at(self._page, *self._start)
        elif mode == "menu":
            self._show_menu(self._menu_pos)

    def _commit(self, item, draw: bool = True):
        """把一个新对象加入当前页。"""
        if draw:
            p = self._page_painter(self._composite(self._page))
            draw_item(p, item)
            p.end()
            self._sync_display(self._page, item.bbox())
            self.update(self._pt_rect_to_widget(item.bbox(), self._page))
        self.strokes.setdefault(self._page, []).append(item)
        self._push(("add", self._page, item))

    def _mask_at(self, page: int, x: float, y: float, any_state: bool = False):
        for it in reversed(self.strokes.get(page, [])):
            if it.kind == "mask" and (any_state or not it.shown) and it.rect().contains(x, y):
                return it
        return None

    def set_masks_shown(self, shown: bool):
        """全部揭开 / 全部遮住。"""
        for items in self.strokes.values():
            for it in items:
                if it.kind == "mask":
                    it.shown = shown
        self._drop_images()
        self.update()

    def go_to_point(self, page: int, y_pt: float):
        """滚动到某一页的某个位置，让它出现在窗口上方三分之一处。"""
        if self.tops and 0 <= page < len(self.tops):
            self.scroll_to(self.tops[page] + round(y_pt * self.zoom) - self.height() // 3)

    def set_hits(self, hits: dict, current=None):
        """设置搜索结果高亮；current = (页号, QRectF) 时滚动到它。"""
        self.hits, self.hit_cur = hits, current
        if current:
            self.go_to_point(current[0], current[1].top())
        self.update()

    def _text_at(self, page: int, x: float, y: float):
        """文本工具：点在已有文本上 = 修改；点在空白处 = 新建。直接在页面上那个位置打字（见 _TextEditor）。"""
        self._tablet_down = False
        self.commit_text_edit()
        for it in reversed(self.strokes.get(page, [])):
            if (it.kind == "text" and it.bbox(2).contains(x, y)) or (it.kind == "rich" and it.src
                                                                     and it.rect().contains(x, y)):
                return self.edit_item(it, page)  # 点在已有的文本框 / 粘贴的片段上：改它
        # 点击位置作为第一行的左侧中线
        self._open_editor({"page": page, "x": x, "y": y - self.text_size * 0.6, "size": self.text_size,
                           "color": self.color, "target": None, "idx": -1}, "")

    def edit_item(self, item, page: int):
        """原地修改一个文本框，或者一个粘贴的片段的原文（Markdown，公式是 LaTeX；改完重新排版）。
        编辑期间先把它从页面上拿掉，由编辑框显示；结束时放回原来的叠放位置。"""
        self._tablet_down = False
        self.commit_text_edit()
        items = self.strokes.get(page, [])
        idx = next((n for n, it in enumerate(items) if it is item), -1)
        if idx < 0 or item.kind not in ("text", "rich") or (item.kind == "rich" and not item.src):
            return
        del items[idx]
        self._invalidate(page)
        ed = {"page": page, "x": item.x, "y": item.y, "target": item, "idx": idx}
        if item.kind == "text":
            ed.update(size=item.size, color=item.color)
            self._open_editor(ed, item.text, runs=item.runs)
        else:
            # 原文用适合阅读的固定大小显示（不跟着片段的缩放走），按片段的宽度折行
            ed.update(size=max(13.0, min(20.0, (item.size or 11.0) * self.zoom)) / self.zoom, color="#111111")
            self._open_editor(ed, item.src, wrap_px=max(360, round(item.w * self.zoom)))
            self.notice.emit(T("正在改这段内容的原文（公式是 LaTeX）。点别处或 Ctrl+回车确认并重新排版，Esc 放弃。"))

    def _open_editor(self, ed: dict, text: str, wrap_px: int = 0, runs=None):
        self._edit = ed
        if self._editor is None:
            self._editor = TextEditor(self)
        pr = self.page_rect(ed["page"])
        m = self._editor.MARGIN
        left, top = round(pr.x() + ed["x"] * self.zoom) - m, round(pr.y() + ed["y"] * self.zoom) - m
        if wrap_px:  # 长内容：别让编辑框的上边跑到窗口外面，下面至少留出几行的高度
            top = max(4, min(top, self.height() - 160))
            left = max(4, min(left, self.width() - wrap_px - 8))
        self._editor.begin(text, ed["size"], self.zoom, ed["color"], runs, wrap_px, self.height() - top - 8)
        self._editor.move(left, top)
        self._editor.show()
        self._editor.setFocus()

    def editing_text(self) -> bool:
        return self._edit is not None

    def commit_text_edit(self):
        """结束页面上的文字输入并把结果落到页面上（没在输入时什么都不做）。"""
        self._end_text_edit(True)

    def cancel_text_edit(self):
        """放弃这次输入：新建的不留，修改的恢复原样。"""
        self._end_text_edit(False)

    def _end_text_edit(self, keep: bool):
        ed, self._edit = self._edit, None
        if ed is None:
            return
        if self._editor.source:
            text, runs = self._editor.toPlainText().strip("\n"), None
        else:
            text, runs = self._editor.runs()  # 文本框：文字 + 分段格式（没有任何格式时 runs 为 None）
        self._editor.hide()
        page, target = ed["page"], ed["target"]
        if page >= len(self.tops):
            return
        if target is None:
            if keep and text.strip():
                self._page = page
                self._commit(TextItem(text, ed["x"], ed["y"], ed["size"], ed["color"], runs))
        elif target.kind == "rich":
            items = self.strokes.setdefault(page, [])
            idx = min(ed["idx"], len(items))
            if keep and not text.strip():  # 删空了 = 删除这个片段
                self._push(("del", page, [(idx, target)]))
            else:
                items.insert(idx, target)  # 先原样放回；内容改了的话，重新排好之后再换（可撤销）
                if keep and text.strip() != target.src.strip():
                    self._rerender(target, page, text.strip("\n"), target.w)
            self._invalidate(page)
        else:
            items = self.strokes.setdefault(page, [])
            idx = min(ed["idx"], len(items))
            if not keep or (text == target.text and runs == target.runs):
                items.insert(idx, target)  # 原样放回
            elif not text.strip():  # 删空了 = 删除这个文本框
                self._push(("del", page, [(idx, target)]))
            else:
                old = target.get_state()
                target.set_state((target.color, target.size, target.x, target.y, text, runs))
                items.insert(idx, target)
                self._push(("mod", page, [(target, old, target.get_state())]))
            self._invalidate(page)
        if self.isVisible():
            self.setFocus()

    def _erase(self, x: float, y: float):
        """对象橡皮：橡皮路径碰到的笔画 / 文本整个删除。"""
        strokes = self.strokes.get(self._page)
        lx, ly = self._last
        self._last = (x, y)
        if not strokes:
            return
        r = ERASER_PX / self.zoom
        path = QRectF(min(x, lx) - r, min(y, ly) - r, abs(x - lx) + 2 * r, abs(y - ly) + 2 * r)
        hit = False
        for idx in range(len(strokes) - 1, -1, -1):
            s = strokes[idx]
            if s.bbox().intersects(path) and s.hit(lx, ly, x, y, r):
                self._erased.append((idx, s))
                del strokes[idx]
                hit = True
        if hit:
            self._invalidate(self._page)

    # ------------------------------------------------------------------ 撤销 / 重做
    def _push(self, action):
        self.undo_stack.append(action)
        self.redo_stack.clear()
        self.historyChanged.emit(True, False)
        self.changed.emit()

    def _apply(self, action, undo: bool):
        kind, page, data = action
        strokes = self.strokes.setdefault(page, [])
        if kind == "mod":  # 移动 / 缩放 / 改色 / 改文字
            for item, old, new in data:
                item.set_state(old if undo else new)
        elif kind == "addn":  # 粘贴：一次加入多个对象
            if undo:
                ids = {id(s) for s in data}
                strokes[:] = [s for s in strokes if id(s) not in ids]
            else:
                strokes.extend(data)
        elif (kind == "add") == undo:  # 需要移除对象
            for s in ([data] if kind == "add" else [s for _, s in data]):
                for i in range(len(strokes) - 1, -1, -1):
                    if strokes[i] is s:
                        del strokes[i]
                        break
        elif kind == "add":
            strokes.append(data)
        else:  # 撤销删除：按删除的逆序插回原位置
            for idx, s in reversed(data):
                strokes.insert(idx, s)
        self._invalidate(page)

    def undo(self):
        if self.undo_stack and not self._mode:
            self.clear_selection()
            a = self.undo_stack.pop()
            self._apply(a, True)
            self.redo_stack.append(a)
            self.historyChanged.emit(bool(self.undo_stack), True)
            self.changed.emit()

    def redo(self):
        if self.redo_stack and not self._mode:
            self.clear_selection()
            a = self.redo_stack.pop()
            self._apply(a, False)
            self.undo_stack.append(a)
            self.historyChanged.emit(True, bool(self.redo_stack))
            self.changed.emit()

    # ------------------------------------------------------------------ 输入事件
    def _input_stuck(self) -> bool:
        """程序以为笔 / 鼠标还按着，其实早就松开了（松开的那个事件没送到）。

        出过这样的事故：抬笔事件丢了之后 _tablet_down 和 _mode 一直不复位，滚轮、缩放、鼠标点击
        全被当成"正在书写"挡掉，整个页面像死了一样。判断办法：笔按着的时候数位板会不停地报告，
        超过 0.7 秒没有任何数位板事件就不是真的按着；鼠标则看系统里是不是真有键按着。
        """
        if self._tablet_down:
            return not self._tablet_clock.isValid() or self._tablet_clock.elapsed() > 700
        return bool(self._mode) and QGuiApplication.mouseButtons() == Qt.NoButton

    def _abort_input(self):
        """收掉卡住的输入状态：写了一半的笔画、选了一半的字照常落定，要弹东西的那几种直接取消。"""
        self._tablet_down = False
        if self._mode in ("text", "menu", "dblclick", "masktap", "pan"):
            self._mode, self._target = None, None
            self._update_cursor()
        elif self._mode:
            self._up()

    def tabletEvent(self, ev):
        t = ev.type()
        pos = ev.position()
        if not self._tablet_down and self._edit is not None and self.childAt(pos.toPoint()) is not None:
            # 笔落在文字输入框或格式工具条上：不是给画布的。不接这个事件，Qt 会把它转成鼠标事件交给那个控件
            ev.ignore()
            return
        self._tablet_clock.restart()
        self._reapply_cursor(t != QEvent.Type.TabletMove)  # 落笔、抬笔时立即重设，移动时限频
        if t == QEvent.Type.TabletPress:
            if self._tablet_down or self._mode:
                self._abort_input()  # 上一次的抬笔没收到：先把上一笔收掉，再开始这一笔
            if not self.hasFocus():
                self.setFocus()  # 笔的事件不会自动给焦点
            self._tablet_down = True
            erase = (ev.pointerType() == QPointingDevice.PointerType.Eraser
                     or bool(ev.buttons() & Qt.RightButton))  # 笔侧键 = 临时橡皮
            self._down(pos, ev.pressure(), erase)
        elif t == QEvent.Type.TabletMove:
            if self._tablet_down and ev.pressure() <= 0 and ev.buttons() == Qt.NoButton:
                self._abort_input()  # 没有压力也没有按键 = 笔已经抬起来在悬停了：抬笔事件丢了，这里补上
            if self._tablet_down:
                self._move(pos, ev.pressure())
                self.penInfo.emit(T("数位板  压感 {:.2f}").format(ev.pressure()))
            else:
                ev.ignore()  # 悬停：交给鼠标事件去移动光标
                return
        elif t == QEvent.Type.TabletRelease:
            self._tablet_down = False
            self._up()
        ev.accept()

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self.focused.emit()

    def mousePressEvent(self, ev):
        if self._tablet_down:
            if not self._input_stuck():
                return
            self._abort_input()  # 笔其实早就抬起来了：收掉卡住的状态，这次鼠标点击照常处理
        elif self._mode and ev.buttons() == ev.button():
            self._abort_input()  # 只有刚按下的这一个键是按着的，却还处在上一次拖动里：上一次的松开丢了
        if ev.button() == Qt.LeftButton:
            self._down(ev.position(), 0.5, False)
            self.penInfo.emit(T("鼠标（无压感）"))
        elif ev.button() == Qt.RightButton:
            self._down(ev.position(), 0.5, True)
        elif ev.button() == Qt.MiddleButton and not self._mode:
            self._mode, self._last = "pan", ev.position()
            self._set_cursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, ev):
        self._reapply_cursor()
        if self._tablet_down:
            return
        if self._mode == "pan":
            d = self._last - ev.position()
            self._last = ev.position()
            self.scroll_by(round(d.x()), round(d.y()))
        elif self._mode:
            self._move(ev.position(), 0.5)

    def mouseReleaseEvent(self, ev):
        if self._tablet_down:
            return
        if self._mode == "pan":
            self._mode = None
            self._update_cursor()
        else:
            self._up()

    def wheelEvent(self, ev):
        if self._mode:
            if not self._input_stuck():
                return
            self._abort_input()
        d = ev.angleDelta()
        if ev.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.1 ** (d.y() / 120)), round(ev.position().y()))
        elif ev.modifiers() & Qt.ShiftModifier:
            self.scroll_by(-(d.y() or d.x()), 0)
        else:
            self.scroll_by(-d.x(), -d.y())

    def keyPressEvent(self, ev):
        k, h = ev.key(), self.height()
        if ev.matches(QKeySequence.Copy):
            self.copy_selection()
        elif ev.matches(QKeySequence.Cut):
            self.cut_selection()
        elif ev.matches(QKeySequence.Paste):
            self.paste()
        elif k in (Qt.Key_Delete, Qt.Key_Backspace) and self._sel:
            self.delete_selection()
        elif k == Qt.Key_Escape and (self._sel or self._tsel is not None):
            self.clear_selection()
        elif k in (Qt.Key_PageDown, Qt.Key_Space):
            self.scroll_by(0, int(h * 0.9))
        elif k == Qt.Key_PageUp:
            self.scroll_by(0, -int(h * 0.9))
        elif k == Qt.Key_Down:
            self.scroll_by(0, 60)
        elif k == Qt.Key_Up:
            self.scroll_by(0, -60)
        elif k == Qt.Key_Home:
            self.scroll_to(0)
        elif k == Qt.Key_End:
            self.scroll_to(self.total_h)
        else:
            super().keyPressEvent(ev)
