"""把一块矩形区域（页面区、侧栏）的四个角切圆，和工具栏的圆角胶囊统一风格。

这些区域里的东西（画布、列表）自己画的是方的，没法靠样式表变圆。做法：在四个角上各盖一个很小的
透明控件（_Corner），它在所有东西画完之后把角外面那一小块处理掉：
  * 开着液态玻璃：把那一小块擦成透明，露出窗口后面的毛玻璃；
  * 没开：涂成窗口的底色。
只占四个角各 RADIUS 见方的地方，不接鼠标事件；书写时画布只刷新笔尖附近的一小块，碰不到它们。
"""
from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from . import theme

RADIUS = 12


class _Corner(QWidget):
    def __init__(self, parent, which: int):
        super().__init__(parent)
        self.which = which  # 0 左上，1 右上，2 左下，3 右下
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.NoFocus)
        self.resize(RADIUS, RADIUS)

    def paintEvent(self, _ev):
        r = RADIUS
        # 这个小方块里，圆角以外的部分 = 方块 − 以对角为圆心的那个圆
        cx = r if self.which in (0, 2) else 0
        cy = r if self.which in (0, 1) else 0
        outside = QPainterPath()
        outside.addRect(QRectF(0, 0, r, r))
        circle = QPainterPath()
        circle.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if theme.glass_enabled:
            p.setCompositionMode(QPainter.CompositionMode_DestinationOut)  # 擦掉：只留下面已有内容的"圆角以内"
            p.fillPath(outside.subtracted(circle), QColor(0, 0, 0, 255))
        else:
            p.fillPath(outside.subtracted(circle), QColor(theme.window_color()))
        p.end()


class _Keeper(QObject):
    """跟着宿主控件的大小把四个角摆好，并保持在最上面。"""

    def __init__(self, host, which):
        super().__init__(host)
        self.host = host
        self.corners = [_Corner(host, k) for k in which]
        host.installEventFilter(self)
        self.place()

    def place(self):
        w, h = self.host.width(), self.host.height()
        for c in self.corners:
            c.move(0 if c.which in (0, 2) else w - RADIUS, 0 if c.which in (0, 1) else h - RADIUS)
            c.show()
            c.raise_()

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.ChildAdded):
            self.place()
        return False


def round_corners(widget, which=(0, 1, 2, 3)):
    """给 widget 的指定几个角切圆。返回的对象挂在 widget 上，不用另外保存。"""
    return _Keeper(widget, which)
