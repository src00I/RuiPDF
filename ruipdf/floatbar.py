"""浮在页面上的工具条：把"工具"和"笔设置"两条工具栏装进一个带阴影的圆角玻璃条里，
可以停在画布的上、下、左、右四边。

  * 上 / 下：横着放。两条并排放得下就排成一行，放不下就上下两行。
  * 左 / 右：工具竖着排成一列；笔设置横着收在旁边一块可以展开 / 收起的小面板里（竖着排太宽了）。

它是画布所在区域的一个普通子控件，盖在画布上面，位置自己算（arrange）。
画布那边用 Canvas.set_insets 给它让出位置，所以滚到头时页面不会被它挡住。

用鼠标 / 笔直接摆弄它：
  * 按住条上的空白处或开头那几个小点拖动 → 松手时停到离得最近的那一边；
  * 拖条的两头 → 改它的长度（横条是宽度，竖条是高度）；比内容短时先变成两行，再短就把放不下的收进"…"；
    双击两头恢复成自动长度。
  * 竖条朝画布的那条长边 → 改它的宽度（按钮仍然是居中的一列）；双击恢复自动。
"""
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QBoxLayout, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QToolButton, QWidget

from . import theme

POSITIONS = ("top", "bottom", "left", "right")
EDGE = 12       # 工具条离画布边缘的距离（px）
GAP = 8         # 工具条和旁边的笔设置面板之间的距离
END_ZONE = 8    # 条的两头这么宽的一段用来拖动改长度
MIN_LEN = 150   # 拖得再短也留这么长
SIDE_ZONE = 6   # 竖条朝画布那一侧这么宽的一条用来拖动改宽度
THICK_MAX = 260  # 竖条最宽能拖到多少；最窄是按钮正好放得下的宽度（见 _min_thick）
DRAG_START = 6  # 按住后移动超过这么远才算拖动


class _Grip(QWidget):
    """条开头的几个小点：提示"这里可以抓住拖动"。鼠标事件不接，交给外面的 FloatBar 处理。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setCursor(Qt.SizeAllCursor)
        self.vertical = False

    def sizeHint(self):
        return QSize(26, 12) if self.vertical else QSize(12, 26)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 235, 245, 110) if theme.is_dark() else QColor(60, 60, 67, 90))
        cx, cy = self.width() / 2, self.height() / 2
        for i in (-1, 0, 1):
            for j in (-0.5, 0.5):
                dx, dy = (i * 5, j * 5) if self.vertical else (j * 5, i * 5)
                p.drawEllipse(QPoint(round(cx + dx), round(cy + dy)), 1, 1)
        p.end()

    def mousePressEvent(self, ev):
        ev.ignore()


class FloatBar(QFrame):
    def __init__(self, parent, tools, settings, flyout_action, host):
        """host 是主窗口，要提供：place_floatbar()（稍后重摆）、_place_floatbar_now()（马上重摆）、
        _pick_toolbar_pos(位置)（换到某一边并记住）、_save_toolbar_len()（把 self.length 记进设置）。"""
        super().__init__(parent)
        self.tools, self.settings, self.flyout_action, self.host = tools, settings, flyout_action, host
        self.pos = "top"
        # 用户拖出来的尺寸（px）：h = 横着放时的宽，v = 竖着放时的高，t = 竖着放时的宽；0 = 自动
        self.length = {"h": 0, "v": 0, "t": 0}
        self.opacity = 100              # 不透明度（百分比）
        self._ref = QRect()             # 上一次 arrange 的参考区域
        self._drag = None               # 正在拖：[“move” 或 “len”, 按下时的全局位置, 按下时自己的位置, 真的动了没有]
        self.setMouseTracking(True)
        self.box = QBoxLayout(QBoxLayout.LeftToRight, self)
        self.box.setContentsMargins(END_ZONE, 3, END_ZONE, 3)
        self.box.setSpacing(0)
        self.grip = _Grip(self)
        self.box.addWidget(self.grip, 0, Qt.AlignCenter)
        # 展开 / 收起笔设置面板的按钮。它不放在工具栏里：窗口矮、竖排放不下时工具栏会把排在后面的
        # 收进"…"里，这个按钮必须一直看得到
        self.fly_btn = QToolButton(self)
        self.fly_btn.setObjectName("flyBtn")
        self.fly_btn.setDefaultAction(flyout_action)
        self.fly_btn.setIconSize(tools.iconSize())
        self.fly_btn.setFocusPolicy(Qt.NoFocus)
        self.box.addWidget(self.fly_btn, 0, Qt.AlignHCenter)
        # 两条工具栏放在里面这一层：横条时小点在它们左边（工具栏排成两行时也不单占一行），竖条时小点在上面
        self.rows = QBoxLayout(QBoxLayout.LeftToRight)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(0)
        self.box.addLayout(self.rows, 1)
        self.fly_btn.hide()
        self.flyout = QFrame(parent)  # 左 / 右布局时装笔设置的小面板
        self.flyout.setObjectName("FloatFlyout")
        lay = QHBoxLayout(self.flyout)
        lay.setContentsMargins(6, 3, 6, 3)
        self._shadows = []
        for w in (self, self.flyout):
            fx = QGraphicsDropShadowEffect(w)
            fx.setBlurRadius(30)
            fx.setOffset(0, 6)
            w.setGraphicsEffect(fx)
            self._shadows.append(fx)
            w.hide()
        self.restyle()
        flyout_action.toggled.connect(lambda _on: host.place_floatbar())  # 展开 / 收起笔设置面板：重新摆一遍

    def restyle(self):
        """按当前的液态玻璃开关和不透明度重新上样式。"""
        style = theme.float_style(self.opacity)
        for w, fx in zip((self, self.flyout), self._shadows):
            w.setStyleSheet(style)
            fx.setColor(QColor(0, 0, 0, round(58 * self.opacity / 100)))  # 条越透，阴影也越淡，不然会从条下面透出一团灰

    def set_opacity(self, percent: int):
        self.opacity = max(theme.FLOAT_OPACITY_RANGE[0], min(theme.FLOAT_OPACITY_RANGE[1], int(percent)))
        self.restyle()

    # ------------------------------------------------------------------ 拖动
    def _vertical(self):
        return self.pos in ("left", "right")

    def _min_thick(self) -> int:
        """竖条最窄能到多少：那一列按钮正好放得下。再窄的话 Qt 会把图标压小（用户截图：图标小得看不清）。"""
        return self.tools.sizeHint().width() + 2 * SIDE_ZONE

    def _zone(self, p) -> str:
        along, total = (p.y(), self.height()) if self._vertical() else (p.x(), self.width())
        if along < END_ZONE or along >= total - END_ZONE:
            return "len"
        if self.pos == "left" and p.x() >= self.width() - SIDE_ZONE or self.pos == "right" and p.x() < SIDE_ZONE:
            return "thick"
        return "move"

    def mousePressEvent(self, ev):
        # 落在工具条空白处的点击到这里为止，不要传给下面的画布
        if ev.button() == Qt.LeftButton:
            self._drag = [self._zone(ev.position().toPoint()), ev.globalPosition().toPoint(),
                          self.geometry().topLeft(), False]
        ev.accept()

    def mouseMoveEvent(self, ev):
        if not self._drag:
            zone = self._zone(ev.position().toPoint())
            self.setCursor(Qt.SizeHorCursor if zone == "thick" or zone == "len" and not self._vertical()
                           else Qt.SizeVerCursor if zone == "len" else Qt.SizeAllCursor)
            return
        kind, start, origin, moved = self._drag
        g = ev.globalPosition().toPoint()
        if not moved and (g - start).manhattanLength() < DRAG_START:
            return
        self._drag[3] = True
        if kind == "move":
            self.flyout.hide()
            self.move(origin + g - start)
            self.raise_()
        elif kind == "thick":  # 竖条贴着画布的一边，宽度 = 落点到那一边的距离
            c = self.parentWidget().mapFromGlobal(g)
            t = c.x() - (self._ref.left() + EDGE) if self.pos == "left" else self._ref.right() - EDGE - c.x()
            self.length["t"] = max(self._min_thick(), min(THICK_MAX, t))
            self.host._place_floatbar_now()
        else:  # 条是居中的，所以长度 = 落点到中心距离的两倍
            c = self.parentWidget().mapFromGlobal(g)
            v = self._vertical()
            half = abs(c.y() - self._ref.center().y()) if v else abs(c.x() - self._ref.center().x())
            room = (self._ref.height() if v else self._ref.width()) - 2 * EDGE
            self.length["v" if v else "h"] = max(MIN_LEN, min(2 * half, room))
            self.host._place_floatbar_now()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        drag, self._drag = self._drag, None
        if drag and drag[3]:
            if drag[0] == "move":  # 停到离松手的地方最近的那一边
                c, r = self.parentWidget().mapFromGlobal(ev.globalPosition().toPoint()), self._ref
                dist = {"top": c.y() - r.top(), "bottom": r.bottom() - c.y(),
                        "left": c.x() - r.left(), "right": r.right() - c.x()}
                self.host._pick_toolbar_pos(min(dist, key=dist.get))
                self.host._place_floatbar_now()
            else:
                self.host._save_toolbar_len()
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        zone = self._zone(ev.position().toPoint())
        if zone != "move":  # 双击两头 / 侧边：恢复自动
            self.length["t" if zone == "thick" else "v" if self._vertical() else "h"] = 0
            self.host._save_toolbar_len()
            self.host._place_floatbar_now()
        ev.accept()

    # ------------------------------------------------------------------ 摆放
    def adopt(self):
        """把两条工具栏收进来（它们得先从主窗口的工具栏区里拿掉）。"""
        self.rows.addWidget(self.tools)
        self.tools.show()
        self.settings.show()

    def release(self):
        """把两条工具栏交出去（要放回主窗口顶部时用）。"""
        for lay in (self.rows, self.flyout.layout()):
            for w in (self.tools, self.settings):
                lay.removeWidget(w)
        self.tools.setOrientation(Qt.Horizontal)
        self.fly_btn.hide()
        self.hide()
        self.flyout.hide()

    def arrange(self, pos: str, ref: QRect) -> QRect:
        """按位置 pos 摆到参考区域 ref（画布区域，父控件坐标）的那一边。返回它占掉的矩形
        （含四周的间距），主窗口据此算画布要让出多少。"""
        self.pos = pos if pos in POSITIONS else "top"
        self._ref = QRect(ref)
        vertical = self._vertical()
        self.tools.setOrientation(Qt.Vertical if vertical else Qt.Horizontal)
        self.fly_btn.setVisible(vertical)
        # 竖条被拖宽时，那一列按钮留在正中间（不设的话工具栏会被拉宽，按钮都挤在左边）
        self.rows.setAlignment(self.tools, Qt.AlignHCenter if vertical else Qt.Alignment())
        self.box.setDirection(QBoxLayout.TopToBottom if vertical else QBoxLayout.LeftToRight)
        self.grip.vertical = vertical
        self.grip.updateGeometry()
        fly = self.flyout.layout()
        room_w, room_h = ref.width() - 2 * EDGE, ref.height() - 2 * EDGE
        if vertical:
            self.rows.removeWidget(self.settings)
            fly.addWidget(self.settings)
            self.rows.setDirection(QBoxLayout.TopToBottom)
            self.box.setContentsMargins(SIDE_ZONE, END_ZONE, SIDE_ZONE, END_ZONE)
        else:
            fly.removeWidget(self.settings)
            self.rows.addWidget(self.settings)
            self.box.setContentsMargins(END_ZONE, 3, END_ZONE, 3)
            limit = min(self.length["h"], room_w) if self.length["h"] else room_w
            one_row = (self.grip.sizeHint().width() + self.tools.sizeHint().width()
                       + self.settings.sizeHint().width() + 2 * END_ZONE + 4 <= limit)
            self.rows.setDirection(QBoxLayout.LeftToRight if one_row else QBoxLayout.TopToBottom)
        self.settings.show()
        self.box.activate()
        hint = self.sizeHint()
        w, h = min(hint.width(), room_w), min(hint.height(), room_h)
        if vertical and self.length["v"]:
            h = min(self.length["v"], room_h)
        elif not vertical and self.length["h"]:
            w = min(self.length["h"], room_w)
        if vertical and self.length["t"]:
            w = min(max(self.length["t"], self._min_thick()), room_w)
        w, h = max(w, 20), max(h, 20)
        if self.pos == "top":
            x, y = ref.center().x() - w // 2, ref.top() + EDGE
        elif self.pos == "bottom":
            x, y = ref.center().x() - w // 2, ref.bottom() - EDGE - h + 1
        elif self.pos == "left":
            x, y = ref.left() + EDGE, ref.center().y() - h // 2
        else:
            x, y = ref.right() - EDGE - w + 1, ref.center().y() - h // 2
        self.setGeometry(max(ref.left(), x), max(ref.top(), y), w, h)
        self.show()
        self.raise_()
        used = QRect(self.geometry())
        if vertical and self.flyout_action.isChecked():
            fly.activate()
            fh = self.flyout.sizeHint()
            fw = min(fh.width(), ref.width() - used.width() - 2 * EDGE - GAP)
            fx = used.right() + 1 + GAP if self.pos == "left" else used.left() - GAP - fw
            self.flyout.setGeometry(fx, used.top(), max(fw, 20), fh.height())
            self.flyout.show()
            self.flyout.raise_()
        else:
            self.flyout.hide()
        # 笔设置面板是临时展开的，不算进要让出的位置（否则一展开页面就跟着跳）
        return used.adjusted(-EDGE, -EDGE, EDGE, EDGE)
