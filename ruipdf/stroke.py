"""页面上的对象：笔画（压感笔 / 荧光笔 / 形状）、文本框、遮挡块、图片、排版好的片段。
坐标单位为 PDF pt，页面左上角为原点。

所有对象提供同一组方法，画布和保存逻辑不用区分类型：
  bbox / sample_points / hit / get_state / set_state / transform / to_json
"""
import base64
import hashlib
import math

import pymupdf

from .i18n import T
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen,
                           QTransform)


# 笔触风格：代号, 名称
PEN_STYLES = [("f", T("钢笔（压感）")), ("b", T("圆珠笔（等粗）")), ("c", T("毛笔（压感强烈）"))]


def seg_width(base: float, pressure: float, style: str = "f") -> float:
    """压感 -> 线宽。pressure 0..1。

    钢笔：粗细随压力温和变化，0.5 时约等于基准宽度；
    圆珠笔：不看压力，始终是基准宽度；
    毛笔：轻压很细、重压很粗，起笔收笔自然出锋。
    """
    if style == "b":
        return base
    if style == "c":
        return base * (0.12 + 2.6 * pressure ** 1.4)
    return base * (0.35 + 1.3 * pressure)


class Stroke:
    """kind: "pen" 压感笔；"hl" 荧光笔（固定宽度，正片叠底）；"poly" 折线形状（固定宽度）。"""
    __slots__ = ("color", "width", "kind", "style", "pts", "x0", "y0", "x1", "y1")

    def __init__(self, color: str, width: float, kind: str = "pen", style: str = "f"):
        self.color = color
        self.width = width
        self.kind = kind
        self.style = style  # 笔触风格，只对 kind == "pen" 有意义
        self.pts = []  # [(x, y, pressure)]
        self.x0 = self.y0 = float("inf")
        self.x1 = self.y1 = float("-inf")

    def add(self, x: float, y: float, p: float):
        self.pts.append((x, y, p))
        self.x0, self.y0 = min(self.x0, x), min(self.y0, y)
        self.x1, self.y1 = max(self.x1, x), max(self.y1, y)

    def _rebox(self):
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        self.x0, self.x1, self.y0, self.y1 = min(xs), max(xs), min(ys), max(ys)

    def bbox(self, margin: float = 0.0) -> QRectF:
        m = margin + self.width * (3 if self.style == "c" else 2)
        return QRectF(self.x0 - m, self.y0 - m, self.x1 - self.x0 + 2 * m, self.y1 - self.y0 + 2 * m)

    def sample_points(self):
        """用于套索判断的采样点；形状只有几个顶点，所以沿边插值。"""
        if self.kind != "poly":
            return [(x, y) for x, y, _ in self.pts]
        out = []
        for a, b in zip(self.pts, self.pts[1:]):
            out += [(a[0] + (b[0] - a[0]) * k / 8, a[1] + (b[1] - a[1]) * k / 8) for k in range(8)]
        out.append(self.pts[-1][:2])
        return out

    def hit(self, ax, ay, bx, by, r) -> bool:
        """橡皮线段 a-b（半径 r）是否碰到这条笔画。"""
        r += self.width / 2
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        r2 = r * r

        def near(px, py):
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
            ex, ey = px - (ax + t * dx), py - (ay + t * dy)
            return ex * ex + ey * ey <= r2

        prev = None
        for x, y, _ in self.pts:
            if near(x, y):
                return True
            if prev is not None:  # 对长线段做插值采样
                n = int(math.hypot(x - prev[0], y - prev[1]) / r)
                for k in range(1, n + 1):
                    t = k / (n + 1)
                    if near(prev[0] + (x - prev[0]) * t, prev[1] + (y - prev[1]) * t):
                        return True
            prev = (x, y)
        return False

    def get_state(self):
        return self.color, self.width, list(self.pts)

    def set_state(self, state):
        self.color, self.width, pts = state
        self.pts = list(pts)
        self._rebox()

    def transform(self, f, scale: float):
        """f(x, y) -> (x, y)；scale 用于同步缩放线宽。"""
        self.pts = [(*f(x, y), p) for x, y, p in self.pts]
        self.width *= scale
        self._rebox()

    def to_json(self) -> dict:
        flat = []
        for x, y, p in self.pts:
            flat += [round(x, 2), round(y, 2), round(p, 3)]
        d = {"c": self.color, "w": round(self.width, 3), "p": flat}
        if self.kind != "pen":
            d["k"] = self.kind
        if self.style != "f":
            d["st"] = self.style
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Stroke":
        s = cls(d["c"], float(d["w"]), d.get("k", "pen"), d.get("st", "f"))
        f = d["p"]
        for i in range(0, len(f) - 2, 3):
            s.add(f[i], f[i + 1], f[i + 2])
        if not s.pts:
            raise ValueError("empty stroke")
        return s


_FONT_PX = 100
_font_cache = None


def _font():
    global _font_cache
    if _font_cache is None:
        f = QFont()
        f.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "Noto Sans CJK SC", "sans-serif"])
        f.setPixelSize(_FONT_PX)
        _font_cache = (f, QFontMetricsF(f))
    return _font_cache


def text_font(pixel_size: float) -> QFont:
    """文本框用的字体，按指定的像素高度（页面上直接输入文字的编辑框用它，和画出来的字对得上）。"""
    f = QFont(_font()[0])
    f.setPixelSize(max(1, round(pixel_size)))
    return f


def run_font(attrs: dict, pixel_size: float) -> QFont:
    """一段文字用的字体：attrs 里的 "f"（字体）、"b"（加粗）加上给定的像素高度。"""
    f = QFont(_font()[0])
    if attrs.get("f"):
        f.setFamilies([attrs["f"]] + f.families())
    f.setBold(bool(attrs.get("b")))
    f.setPixelSize(max(1, round(pixel_size)))
    return f


def plain_runs(text: str):
    """纯文本 -> 没有任何格式的分段表示。"""
    return [[[line, {}]] if line else [] for line in text.split("\n")]


def runs_text(runs) -> str:
    return "\n".join("".join(t for t, _a in line) for line in runs)


def tidy_runs(runs, size: float, color: str):
    """整理分段：去掉空段、和默认值相同的属性，合并相邻的同格式段。全部没有格式时返回 None（就是纯文本）。"""
    out, any_fmt = [], False
    for line in runs:
        new = []
        for text, attrs in line:
            if not text:
                continue
            a = {k: v for k, v in attrs.items() if v}
            if a.get("c", "").lower() == color.lower():
                a.pop("c")
            if "s" in a and abs(a["s"] - size) < 0.01:
                a.pop("s")
            if new and new[-1][1] == a:
                new[-1][0] += text
            else:
                new.append([text, a])
            any_fmt = any_fmt or bool(a)
        out.append(new)
    return out if any_fmt else None


class TextItem:
    """文本框。画的时候把文字转成轮廓路径，所以保存进 PDF 不需要嵌入字体，中文也没问题。

    text 是纯文字。runs 为 None 表示整框一种格式（默认的字体、size、color）；
    否则是分段的格式：[每行 [[文字, 属性], …]]，属性里只写和默认不同的项 ——
    "b" 加粗、"u" 下划线、"c" 颜色、"s" 字号（pt）、"f" 字体。runs 当作不可变的值用，改就换一份新的。
    """
    __slots__ = ("text", "x", "y", "size", "color", "runs", "_layout")
    kind = "text"

    def __init__(self, text: str, x: float, y: float, size: float, color: str, runs=None):
        self.text, self.x, self.y, self.size, self.color, self.runs = text, x, y, size, color, runs
        self._layout = None

    @property
    def width(self):  # 与 Stroke 接口保持一致
        return 0.0

    def layout(self):
        """排好的结果：([(颜色, 轮廓路径), …], 宽, 高)，页面坐标。

        先按 _FONT_PX 的大字号排（字号不同的段按比例），再整体缩到实际字号，这样小字的轮廓也精确。
        一行里各段基线对齐，行高取这一行里最高的那段。整框一种格式时结果和以前完全一样。
        """
        if self._layout is None:
            base_font, base_fm = _font()
            paths, y, width = {}, 0.0, 0.0
            for line in (self.runs if self.runs is not None else plain_runs(self.text)):
                parts = []
                for text, attrs in line:
                    plain = not attrs.get("b") and not attrs.get("f") and "s" not in attrs
                    font = base_font if plain else run_font(attrs, _FONT_PX * attrs.get("s", self.size) / self.size)
                    parts.append((text, attrs, font, base_fm if plain else QFontMetricsF(font)))
                ascent = max([fm.ascent() for *_r, fm in parts] or [base_fm.ascent()])
                height = max([fm.lineSpacing() for *_r, fm in parts] or [base_fm.lineSpacing()])
                x = 0.0
                for text, attrs, font, fm in parts:
                    p = paths.setdefault(attrs.get("c", self.color), QPainterPath())
                    p.addText(x, y + ascent, font, text)
                    adv = fm.horizontalAdvance(text)
                    if attrs.get("u"):
                        p.addRect(x, y + ascent + fm.underlinePos(), adv, max(fm.lineWidth(), fm.height() * 0.05))
                    x += adv
                width = max(width, x)
                y += height
            s = self.size / _FONT_PX
            xf = QTransform().translate(self.x, self.y).scale(s, s)
            pieces = []
            for color, p in paths.items():
                p = xf.map(p)
                p.setFillRule(Qt.WindingFill)
                pieces.append((color, p))
            self._layout = (pieces, width * s, y * s)
        return self._layout

    def bbox(self, margin: float = 0.0) -> QRectF:
        # 用行高算外框，比字形轮廓的外框稳定（空格、标点也占位）
        _pieces, w, h = self.layout()
        m = margin + 1
        return QRectF(self.x - m, self.y - m, w + 2 * m, h + 2 * m)

    def sample_points(self):
        r = self.bbox()
        c = r.center()
        return [(r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()),
                (r.right(), r.bottom()), (c.x(), c.y())]

    def hit(self, ax, ay, bx, by, r) -> bool:
        seg = QRectF(min(ax, bx), min(ay, by), abs(ax - bx), abs(ay - by)).adjusted(-r, -r, r, r)
        return self.bbox().intersects(seg)

    def get_state(self):
        return self.color, self.size, self.x, self.y, self.text, self.runs

    def set_state(self, state):
        self.color, self.size, self.x, self.y, self.text, self.runs = state
        self._layout = None

    def transform(self, f, scale: float):
        self.x, self.y = f(self.x, self.y)
        self.size *= scale
        if self.runs is not None and scale != 1.0:  # 单独设过字号的段跟着一起缩放
            self.runs = [[[t, dict(a, s=a["s"] * scale) if "s" in a else a] for t, a in line] for line in self.runs]
        self._layout = None

    def to_json(self) -> dict:
        d = {"k": "text", "c": self.color, "s": round(self.size, 2),
             "x": round(self.x, 2), "y": round(self.y, 2), "t": self.text}
        if self.runs is not None:
            d["runs"] = self.runs
        return d


class MaskItem:
    """遮挡块：复习时盖住答案 / 公式，点一下揭开。只在 RuiPDF 里显示，不会画进 PDF 页面。"""
    __slots__ = ("x0", "y0", "x1", "y1", "shown")
    kind = "mask"
    color = "#B0BEC5"
    width = 0.0

    def __init__(self, x0, y0, x1, y1):
        self.x0, self.x1 = min(x0, x1), max(x0, x1)
        self.y0, self.y1 = min(y0, y1), max(y0, y1)
        self.shown = False  # True = 已揭开（不保存，每次打开都重新遮住）

    def rect(self) -> QRectF:
        return QRectF(self.x0, self.y0, self.x1 - self.x0, self.y1 - self.y0)

    def bbox(self, margin: float = 0.0) -> QRectF:
        m = margin + 1
        return self.rect().adjusted(-m, -m, m, m)

    def sample_points(self):
        cx, cy = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        return [(self.x0, self.y0), (self.x1, self.y0), (self.x0, self.y1), (self.x1, self.y1), (cx, cy)]

    def hit(self, ax, ay, bx, by, r) -> bool:
        seg = QRectF(min(ax, bx), min(ay, by), abs(ax - bx), abs(ay - by)).adjusted(-r, -r, r, r)
        return self.rect().intersects(seg)

    def get_state(self):
        return self.x0, self.y0, self.x1, self.y1

    def set_state(self, state):
        self.x0, self.y0, self.x1, self.y1 = state

    def transform(self, f, scale: float):
        self.x0, self.y0 = f(self.x0, self.y0)
        self.x1, self.y1 = f(self.x1, self.y1)

    def to_json(self) -> dict:
        return {"k": "mask", "r": [round(v, 2) for v in self.get_state()]}


BOX_KINDS = ("img", "rich")  # 有固定外框、内容是一份二进制数据的对象


class BoxItem:
    """图片（ImageItem）和排版好的片段（RichItem）的共同部分：一个外框 + 一份原始数据。

    移动缩放只改外框。图片的数据不变，撤销用的状态只有 (x, y, w, h)；片段见 RichItem。
    保存进 PDF 时，数据做成一个 XObject（按内容的哈希命名，相同内容只存一份），笔迹内容流里引用它。
    """
    __slots__ = ("x", "y", "w", "h", "data", "hash")
    color = "#607D8B"  # 只用于侧栏"标注汇总"的图标；这类对象不能改色
    width = 0.0

    def __init__(self, data: bytes, x: float, y: float, w: float, h: float):
        self.data = bytes(data)
        self.hash = hashlib.sha1(self.data).hexdigest()[:20]
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)

    def rect(self) -> QRectF:
        return QRectF(self.x, self.y, self.w, self.h)

    def bbox(self, margin: float = 0.0) -> QRectF:
        return self.rect().adjusted(-margin, -margin, margin, margin)

    def sample_points(self):
        r = self.rect()
        c = r.center()
        return [(r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()),
                (r.right(), r.bottom()), (c.x(), c.y())]

    def hit(self, ax, ay, bx, by, r) -> bool:
        seg = QRectF(min(ax, bx), min(ay, by), abs(ax - bx), abs(ay - by)).adjusted(-r, -r, r, r)
        return self.rect().intersects(seg)

    def get_state(self):
        return self.x, self.y, self.w, self.h

    def set_state(self, state):
        self.x, self.y, self.w, self.h = state

    def transform(self, f, scale: float):
        self.x, self.y = f(self.x, self.y)
        self.w *= scale
        self.h *= scale

    def to_json(self) -> dict:
        return {"k": self.kind, "r": [round(v, 2) for v in (self.x, self.y, self.w, self.h)],
                "d": base64.b64encode(self.data).decode("ascii")}


class ImageItem(BoxItem):
    """插入的图片。data 是图片文件的原始内容（PNG / JPEG 等）。"""
    __slots__ = ("_img",)
    kind = "img"

    def __init__(self, data: bytes, x, y, w, h):
        super().__init__(data, x, y, w, h)
        self._img = None

    def image(self) -> QImage:
        if self._img is None:
            self._img = QImage.fromData(self.data)
        return self._img


class RichItem(BoxItem):
    """排版好的一段内容（粘贴的 AI 回答：文字、公式、表格）。data 是只有一页的 PDF，矢量的，放大不糊。

    src 是排版前的原文（Markdown，公式是 LaTeX）；font / size 是排版时用的字体和字号（pt，
    指片段原始大小下的字号，整体缩放过也不变）。改内容、改宽度都是拿这三样重新排版，换掉 data。
    所以它的状态除了外框还包括 data 和 src，撤销时一起换回去。
    """
    __slots__ = ("src", "font", "size", "_size", "_raster")
    kind = "rich"

    def __init__(self, data: bytes, x, y, w, h, src: str = "", font: str = "", size: float = 0.0):
        super().__init__(data, x, y, w, h)
        self.src, self.font, self.size = src, font, float(size)
        self._size = None    # 片段那一页的原始大小（pt）
        self._raster = None  # (横向像素/pt, 纵向像素/pt, QImage)：最近一次渲染的结果

    def get_state(self):
        return self.x, self.y, self.w, self.h, self.data, self.src

    def set_state(self, state):
        self.x, self.y, self.w, self.h, data, self.src = state
        if data is not self.data:
            self.data = bytes(data)
            self.hash = hashlib.sha1(self.data).hexdigest()[:20]
            self._size = self._raster = None

    def natural_size(self):
        if self._size is None:
            doc = pymupdf.open(stream=self.data, filetype="pdf")
            r = doc[0].rect
            self._size = (r.width, r.height)
            doc.close()
        return self._size

    def raster(self, px_per_pt: float) -> QImage:
        """按给定的分辨率把片段渲染成带透明底的图（下面的页面内容能透出来）。同一分辨率只渲染一次。"""
        pw, ph = self.natural_size()
        sx, sy = px_per_pt * self.w / pw, px_per_pt * self.h / ph
        limit = 6000.0 / max(pw * sx, ph * sy, 1.0)  # 防止高倍放大时渲染出巨大的图
        if limit < 1:
            sx, sy = sx * limit, sy * limit
        key = (round(sx, 3), round(sy, 3))
        if self._raster is None or self._raster[:2] != key:
            doc = pymupdf.open(stream=self.data, filetype="pdf")
            pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(sx, sy), alpha=True)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGBA8888_Premultiplied).copy()
            doc.close()
            self._raster = (key[0], key[1], img)
        return self._raster[2]

    def to_json(self) -> dict:
        d = super().to_json()
        if self.src:
            d["src"] = self.src
        if self.size:
            d["f"] = [self.font, round(self.size, 2)]
        return d


def item_from_json(d: dict):
    if d.get("k") in BOX_KINDS:
        data = base64.b64decode(d["d"])
        x, y, w, h = (float(v) for v in d["r"])
        if d["k"] == "img":
            item = ImageItem(data, x, y, w, h)
            if item.image().isNull():
                raise ValueError("bad image")
            return item
        font, size = d.get("f") or ("", 0.0)
        return RichItem(data, x, y, w, h, d.get("src", ""), font, size)
    if d.get("k") == "mask":
        return MaskItem(*[float(v) for v in d["r"]])
    if d.get("k") == "text":
        if not d["t"].strip():
            raise ValueError("empty text")
        runs = d.get("runs")
        if runs is not None:
            runs = tidy_runs([[[str(t), dict(a)] for t, a in line] for line in runs], float(d["s"]), d["c"])
        return TextItem(d["t"], float(d["x"]), float(d["y"]), float(d["s"]), d["c"], runs)
    return Stroke.from_json(d)


# ---------------------------------------------------------------------- 形状
SHAPES = ("line", "arrow", "rect", "ellipse")


def make_shape(shape: str, x0, y0, x1, y1, color: str, width: float) -> Stroke:
    """由拖动的起点和终点生成形状（折线）。"""
    s = Stroke(color, width, "poly")
    if shape in ("line", "arrow"):
        dx, dy = x1 - x0, y1 - y0
        ang = math.degrees(math.atan2(dy, dx))
        for target in (0, 90, 180, -90, -180):  # 接近水平 / 竖直时自动吸附
            if abs(ang - target) < 4:
                if target in (0, 180, -180):
                    y1 = y0
                else:
                    x1 = x0
        pts = [(x0, y0), (x1, y1)]
        L = math.hypot(x1 - x0, y1 - y0)
        if shape == "arrow" and L > 1:
            head = min(L * 0.5, max(8.0, width * 5))
            a = math.atan2(y1 - y0, x1 - x0)
            for da in (math.radians(155), math.radians(-155)):
                pts += [(x1 + head * math.cos(a + da), y1 + head * math.sin(a + da)), (x1, y1)]
    elif shape == "rect":
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    else:  # ellipse
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0) / 2, abs(y1 - y0) / 2
        pts = [(cx + rx * math.cos(2 * math.pi * k / 64), cy + ry * math.sin(2 * math.pi * k / 64))
               for k in range(65)]
    for x, y in pts:
        s.add(x, y, 0.5)
    return s


# ---------------------------------------------------------------------- 绘制
def _mid(a, b):
    return QPointF((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _pen(stroke: Stroke, pressure: float) -> QPen:
    return QPen(QColor(stroke.color), seg_width(stroke.width, pressure, stroke.style),
                Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def draw_piece(painter: QPainter, s: Stroke, i: int) -> QRectF:
    """（压感笔）绘制第 i 个点到来后新增的一小段（i >= 1），返回脏区（pt）。

    用相邻点的中点做二次贝塞尔平滑：每段从 mid(i-2,i-1) 到 mid(i-1,i)，控制点为 i-1。
    """
    pts = s.pts
    b, c = pts[i - 1], pts[i]
    path = QPainterPath()
    if i == 1:
        path.moveTo(b[0], b[1])
        path.lineTo(_mid(b, c))
        xs, ys = (b[0], c[0]), (b[1], c[1])
    else:
        a = pts[i - 2]
        path.moveTo(_mid(a, b))
        path.quadTo(QPointF(b[0], b[1]), _mid(b, c))
        xs, ys = (a[0], b[0], c[0]), (a[1], b[1], c[1])
    painter.setPen(_pen(s, b[2]))
    painter.drawPath(path)
    m = s.width * 3 + 1
    return QRectF(min(xs) - m, min(ys) - m, max(xs) - min(xs) + 2 * m, max(ys) - min(ys) + 2 * m)


def draw_tail(painter: QPainter, s: Stroke) -> QRectF:
    """（压感笔）抬笔时补上最后半段；单点笔画画成一个圆点。"""
    pts = s.pts
    c = pts[-1]
    painter.setPen(_pen(s, c[2]))
    if len(pts) == 1:
        painter.drawPoint(QPointF(c[0], c[1]))
        b = c
    else:
        b = pts[-2]
        painter.drawLine(_mid(b, c), QPointF(c[0], c[1]))
    m = s.width * 3 + 1
    return QRectF(min(b[0], c[0]) - m, min(b[1], c[1]) - m,
                  abs(b[0] - c[0]) + 2 * m, abs(b[1] - c[1]) + 2 * m)


def draw_item(painter: QPainter, s):
    """完整绘制一个对象（压感笔的结果与增量绘制一致）。"""
    if s.kind == "mask":
        painter.save()
        if s.shown:  # 已揭开：只留一个淡淡的虚线框，提示这里有遮挡块
            painter.setPen(QPen(QColor("#78909C"), 0.8, Qt.DashLine))
            painter.setBrush(QColor(144, 164, 174, 26))
            painter.drawRect(s.rect())
        else:
            painter.setPen(QPen(QColor("#78909C"), 0.8))
            painter.setBrush(QColor(s.color))
            painter.drawRoundedRect(s.rect(), 2, 2)
        painter.restore()
    elif s.kind == "text":
        for color, path in s.layout()[0]:
            painter.fillPath(path, QColor(color))
    elif s.kind in BOX_KINDS:
        painter.save()
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if s.kind == "img":
            painter.drawImage(s.rect(), s.image())
        else:
            # 按画到设备上的实际分辨率渲染片段，贴上去时接近 1:1，文字和公式才清楚
            t = painter.deviceTransform()
            painter.drawImage(s.rect(), s.raster(math.hypot(t.m11(), t.m12())))
        painter.restore()
    elif s.kind in ("hl", "poly"):
        # 整条一次画完：荧光笔若分段画，段与段重叠处会被叠深成一串珠子
        painter.save()
        if s.kind == "hl":
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(s.color), s.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(stroke_path(s))
        painter.restore()
    else:
        for i in range(1, len(s.pts)):
            draw_piece(painter, s, i)
        draw_tail(painter, s)


def stroke_path(s: Stroke) -> QPainterPath:
    """整条笔画的路径（荧光笔、形状用）。"""
    path = QPainterPath()
    first = True
    for _, p0, ctrl, p1 in iter_pieces(s):
        if first:
            path.moveTo(p0[0], p0[1])
            first = False
        if ctrl is None:
            path.lineTo(p1[0], p1[1])
        else:
            path.quadTo(ctrl[0], ctrl[1], p1[0], p1[1])
    return path


def iter_pieces(s: Stroke):
    """笔画的几何分段，绘制和导出 PDF 共用。

    依次给出 (线宽, 起点, 控制点或 None, 终点)，点为 (x, y)，相邻两段首尾相接。
    """
    pts = s.pts
    if s.kind == "poly":
        for a, b in zip(pts, pts[1:]):
            yield s.width, (a[0], a[1]), None, (b[0], b[1])
        return
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    for i in range(1, len(pts)):
        b, c = pts[i - 1], pts[i]
        if i == 1:
            yield seg_width(s.width, b[2], s.style), (b[0], b[1]), None, mid(b, c)
        else:
            a = pts[i - 2]
            yield seg_width(s.width, b[2], s.style), mid(a, b), (b[0], b[1]), mid(b, c)
    c = pts[-1]
    start = mid(pts[-2], c) if len(pts) > 1 else (c[0], c[1])
    yield seg_width(s.width, c[2], s.style), start, None, (c[0], c[1])
