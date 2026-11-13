"""直接盖在页面上的文字输入框，和它上方的格式工具条。

两种用法共用一个输入框：
  * 文本框（文本工具）：所见即所得。选中一部分文字可以加粗、加下划线、改颜色 / 字号 / 字体，
    结果用 stroke.TextItem 的 runs 表示。
  * 粘贴片段的原文（Markdown + LaTeX）：显示的是源码。同样的按钮在这里是给选中的内容包上对应的
    标记（**加粗**、<u>下划线</u>、<span style="…">），确认后重新排版才看得到效果。

用真的输入控件而不是自己处理按键，这样中文输入法、选中、复制粘贴、撤销都是现成的。
回车换行；Ctrl+回车、点别处或切换工具 = 确认；Esc = 放弃。
"""
import re

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPixmap, QTextCharFormat, QTextCursor,
                           QTextFormat)
from PySide6.QtWidgets import (QColorDialog, QDoubleSpinBox, QFontComboBox, QFrame, QHBoxLayout,
                               QMenu, QTextEdit, QToolButton)

from . import theme
from .i18n import T
from .stroke import run_font, text_font, tidy_runs

PT_PROP = QTextFormat.UserProperty + 1  # 一段文字的字号（pt，精确值）；屏幕上用的像素大小是它乘缩放后取整
SWATCHES = ["#111111", "#D32F2F", "#F57C00", "#2E7D32", "#1565C0", "#6A1B9A", "#757575", "#FFFFFF"]
_LINE_PREFIX = re.compile(r"^(\s*(?:[*+-]|\d{1,3}[.)]|#{1,6}|>)\s+)?(.*)$", re.S)


def _swatch(color: str, size: int = 14) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setPen(QColor("#8E8E93"))
    p.setBrush(QColor(color))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return QIcon(pm)


class FormatBar(QFrame):
    """输入框上方的一小条：加粗、下划线、颜色、字体、字号。作用于输入框里选中的文字
    （没有选中时，作用于接下来要输入的文字）。"""

    def __init__(self, canvas, editor):
        super().__init__(canvas)
        self.editor = editor
        # 按钮都不接收焦点。但点一个不接收焦点的控件时，Qt 会顺着父控件往上找一个肯接收的 ——
        # 不拦住的话会找到画布，输入框丢了焦点就被当成"点别处 = 确认"。所以工具条自己接下来，再转交给输入框。
        self.setFocusPolicy(Qt.ClickFocus)
        self.setFocusProxy(editor)
        self.setStyleSheet(theme.format_bar_style())
        lay = QHBoxLayout(self)
        lay.setContentsMargins(5, 3, 5, 3)
        lay.setSpacing(3)

        def button(text, tip, slot, checkable=False, style=""):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(checkable)
            b.setFocusPolicy(Qt.NoFocus)  # 点按钮不抢输入框的焦点，否则会被当成"点别处 = 确认"
            if style:
                b.setStyleSheet(style)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        self.b_bold = button("B", T("加粗（Ctrl+B）"), lambda: editor.toggle_bold(), True, "font-weight: bold;")
        self.b_under = button("U", T("下划线（Ctrl+U）"), lambda: editor.toggle_underline(), True,
                              "text-decoration: underline;")
        self.b_color = button("A", T("文字颜色"), lambda: None, style="font-weight: bold; color: #D32F2F;")
        menu = QMenu(self.b_color)
        for col in SWATCHES:
            menu.addAction(_swatch(col), col).triggered.connect(lambda _=False, c=col: editor.set_color(c))
        menu.addSeparator()
        menu.addAction(T("其他颜色…")).triggered.connect(self._pick_other_color)
        self.b_color.setMenu(menu)
        self.b_color.setPopupMode(QToolButton.InstantPopup)
        self.font = QFontComboBox()
        self.font.setFocusPolicy(Qt.NoFocus)
        self.font.setEditable(False)
        self.font.setMaximumWidth(150)
        self.font.setToolTip(T("字体"))
        self.font.textActivated.connect(lambda name: editor.set_font_family(name))
        lay.addWidget(self.font)
        self.size = QDoubleSpinBox()
        self.size.setRange(4.0, 96.0)
        self.size.setDecimals(1)
        self.size.setSingleStep(1.0)
        self.size.setSuffix(" pt")
        self.size.setToolTip(T("字号"))
        self.size.setKeyboardTracking(False)
        self.size.valueChanged.connect(lambda v: editor.set_size(v))
        self.size.editingFinished.connect(lambda: editor.setFocus() if editor.isVisible() else None)
        lay.addWidget(self.size)
        self.hide()

    # 落在工具条上、但没被哪个按钮接住的点击（比如点在字号框的数字上）到这里为止，
    # 不要再传给底下的画布 —— 画布会把它当成"点别处 = 确认输入"
    def mousePressEvent(self, ev):
        ev.accept()

    def mouseReleaseEvent(self, ev):
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        ev.accept()

    def mouseMoveEvent(self, ev):
        ev.accept()

    def _pick_other_color(self):
        self.editor.hold = True  # 对话框会拿走焦点：这期间不算"点别处"
        try:
            col = QColorDialog.getColor(QColor("#D32F2F"), self.window(), T("文字颜色"))
        finally:
            self.editor.hold = False
            self.editor.setFocus()
        if col.isValid():
            self.editor.set_color(col.name())

    def sync(self, attrs: dict, base_size: float, base_font: str):
        """把按钮的状态对到光标所在位置的格式上。"""
        for w, value in ((self.b_bold, bool(attrs.get("b"))), (self.b_under, bool(attrs.get("u")))):
            w.blockSignals(True)
            w.setChecked(value)
            w.blockSignals(False)
        self.size.blockSignals(True)
        self.size.setValue(attrs.get("s", base_size))
        self.size.blockSignals(False)
        self.font.blockSignals(True)
        self.font.setCurrentFont(QFont(attrs.get("f") or base_font))
        self.font.blockSignals(False)

    def place(self):
        """贴在输入框上方（上面放不下就放下面），不超出画布。"""
        self.adjustSize()
        ed, cv = self.editor, self.parentWidget()
        y = ed.y() - self.height() - 4
        if y < 2:
            y = min(ed.y() + ed.height() + 4, cv.height() - self.height() - 2)
        self.move(max(2, min(ed.x(), cv.width() - self.width() - 2)), max(2, y))
        self.raise_()


class TextEditor(QTextEdit):
    MARGIN = 3  # 文字到边框的距离（px）

    def __init__(self, canvas):
        super().__init__(canvas)
        self._canvas = canvas
        self.setAcceptRichText(False)  # 从别处粘贴进来的只要文字，格式用我们自己的按钮加
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.document().setDocumentMargin(self.MARGIN)
        self._wrap, self._max_h = 0, 0
        self.source = False       # True：编辑的是粘贴片段的原文（按钮插标记）；False：文本框（所见即所得）
        self.hold = False         # True：焦点暂时被我们自己的对话框拿走，不算离开
        self._zoom, self._size, self._color = 1.0, 12.0, "#111111"
        self.bar = FormatBar(canvas, self)
        self.textChanged.connect(self._fit)
        self.cursorPositionChanged.connect(self._sync_bar)
        self.hide()

    # ------------------------------------------------------------------ 开始 / 取结果
    def begin(self, text: str, size_pt: float, zoom: float, color: str, runs=None, wrap_px: int = 0,
              max_height: int = 0):
        """开始编辑。size_pt / color 是默认的字号和颜色，zoom 是画布的缩放（屏幕像素 = pt × zoom）。
        runs：文本框已有的分段格式（见 stroke.TextItem），没有就用 text。
        wrap_px > 0：编辑粘贴片段的原文 —— 固定这么宽、自动折行，高度不超过 max_height，超出就滚动；
        否则是文本框：不折行，宽高都跟着内容走。"""
        self._wrap, self._max_h, self.source = int(wrap_px), int(max_height), bool(wrap_px)
        self._zoom, self._size, self._color = zoom, size_pt, color
        self.setLineWrapMode(QTextEdit.WidgetWidth if wrap_px else QTextEdit.NoWrap)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if wrap_px else Qt.ScrollBarAlwaysOff)
        if wrap_px:
            self.setFixedWidth(wrap_px)
        else:
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
        self.setFont(text_font(size_pt * zoom))
        self.setStyleSheet(
            f"QTextEdit {{ background: rgba(255, 255, 255, 215); color: {color};"
            f" border: 1px dashed #0A84FF; padding: 0; selection-background-color: #B3D7FF; }}")
        self.blockSignals(True)
        self.clear()
        self.setCurrentCharFormat(QTextCharFormat())
        if runs is None or self.source:
            self.setPlainText(text)
        else:
            cur = self.textCursor()
            for n, line in enumerate(runs):
                if n:
                    cur.insertBlock()
                for part, attrs in line:
                    cur.insertText(part, self._fmt(attrs))
        self.blockSignals(False)
        self.document().clearUndoRedoStacks()
        self.moveCursor(QTextCursor.End)
        self._fit()
        self._sync_bar()

    def _fmt(self, attrs: dict) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if attrs.get("b"):
            fmt.setFontWeight(QFont.Bold)
        if attrs.get("u"):
            fmt.setFontUnderline(True)
        if attrs.get("c"):
            fmt.setForeground(QColor(attrs["c"]))
        if attrs.get("f"):
            fmt.setFontFamilies(run_font(attrs, 10).families())
        if attrs.get("s"):
            fmt.setProperty(PT_PROP, float(attrs["s"]))
            fmt.setProperty(QTextFormat.FontPixelSize, max(1, round(attrs["s"] * self._zoom)))
        return fmt

    @staticmethod
    def _attrs(fmt: QTextCharFormat) -> dict:
        a = {}
        if fmt.fontWeight() >= QFont.DemiBold:
            a["b"] = 1
        if fmt.fontUnderline():
            a["u"] = 1
        if fmt.hasProperty(QTextFormat.ForegroundBrush):
            a["c"] = fmt.foreground().color().name()
        if fmt.hasProperty(QTextFormat.FontFamilies) and fmt.fontFamilies():
            a["f"] = fmt.fontFamilies()[0]
        if fmt.hasProperty(PT_PROP):
            a["s"] = float(fmt.property(PT_PROP))
        return a

    def runs(self):
        """文本框的内容：(纯文字, 分段格式或 None)。开头结尾的空行去掉。"""
        lines = []
        block = self.document().begin()
        while block.isValid():
            line = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    line.append([frag.text().replace(chr(0x2028), " "), self._attrs(frag.charFormat())])
                it += 1
            lines.append(line)
            block = block.next()
        while lines and not any(t for t, _a in lines[0]):
            lines.pop(0)
        while lines and not any(t for t, _a in lines[-1]):
            lines.pop()
        text = "\n".join("".join(t for t, _a in line) for line in lines)
        return text, tidy_runs(lines, self._size, self._color)

    # ------------------------------------------------------------------ 格式
    def _merge(self, fmt: QTextCharFormat):
        cur = self.textCursor()
        if cur.hasSelection():
            cur.mergeCharFormat(fmt)
        self.mergeCurrentCharFormat(fmt)  # 没有选中时：接下来输入的文字用这个格式
        self._fit()
        self._sync_bar()

    def _wrap_selection(self, before: str, after: str, prop: str = ""):
        """（原文模式）给选中的内容加上 / 去掉标记。

        加粗、下划线是开关：选中的内容已经带着这种标记（标记在选区里面或者紧贴在外面都算）就去掉，
        叠了好几层的一次去干净；没有才加上。颜色 / 字号 / 字体（prop 是对应的样式名）不是开关：
        已经有同一种样式的就换成新的值，不再套一层。
        跨行时逐行处理，列表 / 标题的记号留在外面，独立成行的公式（$$…$$）不动。
        """
        cur = self.textCursor()
        if not cur.hasSelection():
            self._canvas.notice.emit(T("先选中要改格式的文字。"))
            return
        doc = self.toPlainText()  # 位置和光标的位置一一对应（段落之间算一个字符）
        a, b = cur.selectionStart(), cur.selectionEnd()
        while b > a and doc[b - 1] == "\n":  # 选区末尾带上的换行不算
            b -= 1
        span = re.compile(r'<span style="%s:[^"<>]*">' % re.escape(prop)) if prop else None
        # 标记紧贴在选区外面：把它们也算进选区
        if span is None:
            while a >= len(before) and doc[a - len(before):a] == before and doc[b:b + len(after)] == after:
                a, b = a - len(before), b + len(after)
        else:
            m = re.search(span.pattern + "$", doc[:a])
            if m and doc[b:b + len(after)] == after:
                a, b = m.start(), b + len(after)

        def unwrap(body: str):
            """去掉 body 两头的这种标记（可能叠了几层）。返回 (去掉后的内容, 原来有没有)。"""
            had = False
            if span is None:
                while len(body) >= len(before) + len(after) and body.startswith(before) and body.endswith(after):
                    body, had = body[len(before):len(body) - len(after)], True
            else:
                m = span.match(body)
                while m and body.endswith(after):
                    body, had = body[m.end():len(body) - len(after)], True
                    m = span.match(body)
            return body, had

        parts, in_math = [], False  # [(行首记号, 内容, 能不能加标记)]
        for line in doc[a:b].split("\n"):
            fence = line.strip().startswith("$$")
            closed = fence and line.strip().endswith("$$") and len(line.strip()) > 4
            if in_math or fence or not line.strip():
                parts.append(("", line, False))
            else:
                prefix, body = _LINE_PREFIX.match(line).groups()
                parts.append((prefix or "", body, True))
            if fence and not closed:
                in_math = not in_math
        bodies = [unwrap(body) if ok else (body, False) for _p, body, ok in parts]
        # 开关：能加标记的行里只要有一行已经带着，这次就是"取消"
        remove = span is None and any(had for (_b, had), (_p, _body, ok) in zip(bodies, parts) if ok)
        out = []
        for (prefix, _body, ok), (inner, _had) in zip(parts, bodies):
            out.append(prefix + (inner if remove or not ok else before + inner + after))
        text = "\n".join(out)
        cur.setPosition(a)
        cur.setPosition(b, QTextCursor.KeepAnchor)
        cur.insertText(text)
        cur.setPosition(a)
        cur.setPosition(a + len(text), QTextCursor.KeepAnchor)
        self.setTextCursor(cur)

    def toggle_bold(self):
        if self.source:
            return self._wrap_selection("**", "**")
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Normal if self._attrs_here().get("b") else QFont.Bold)
        self._merge(fmt)

    def toggle_underline(self):
        if self.source:
            return self._wrap_selection("<u>", "</u>")
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self._attrs_here().get("u"))
        self._merge(fmt)

    def set_color(self, color: str):
        if self.source:
            return self._wrap_selection('<span style="color:%s">' % QColor(color).name(), "</span>", "color")
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        self._merge(fmt)

    def set_size(self, pt: float):
        if self.source:
            return self._wrap_selection('<span style="font-size:%gpt">' % round(pt, 1), "</span>", "font-size")
        fmt = QTextCharFormat()
        fmt.setProperty(PT_PROP, float(pt))
        fmt.setProperty(QTextFormat.FontPixelSize, max(1, round(pt * self._zoom)))
        self._merge(fmt)

    def set_font_family(self, family: str):
        if self.source:
            return self._wrap_selection("<span style=\"font-family:'%s'\">" % family.replace("'", ""), "</span>",
                                        "font-family")
        fmt = QTextCharFormat()
        fmt.setFontFamilies(run_font({"f": family}, 10).families())
        self._merge(fmt)

    def _attrs_here(self) -> dict:
        """光标处（有选区时是选区开头那个字）的格式。"""
        cur = self.textCursor()
        if cur.hasSelection():
            probe = QTextCursor(self.document())
            probe.setPosition(cur.selectionStart() + 1)
            return self._attrs(probe.charFormat())
        return self._attrs(self.currentCharFormat())

    def _sync_bar(self):
        if not self.source:
            self.bar.sync(self._attrs_here(), self._size, text_font(10).families()[0])

    # ------------------------------------------------------------------ 大小 / 按键 / 焦点
    def _fit(self):
        doc = self.document()
        if self._wrap:
            h = round(doc.size().height()) + 6
            self.setFixedHeight(max(self.fontMetrics().lineSpacing() * 2, min(h, self._max_h or h)))
        else:
            w = round(doc.idealWidth()) + self.fontMetrics().averageCharWidth() * 2 + 6
            self.resize(max(w, 40), round(doc.size().height()) + 4)
        if self.isVisible():
            self.bar.place()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self._wrap and ev.size().width() != ev.oldSize().width():
            self._fit()  # 宽度定下来之后折行才是对的，这时再按实际高度定大小

    def sizeHint(self):
        return QSize(40, 20)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.bar.show()
        self.bar.place()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self.bar.hide()

    def moveEvent(self, ev):
        super().moveEvent(ev)
        if self.isVisible():
            self.bar.place()

    def keyPressEvent(self, ev):
        ctrl = bool(ev.modifiers() & Qt.ControlModifier)
        if ev.key() == Qt.Key_Escape:
            self._canvas.cancel_text_edit()
        elif ev.key() in (Qt.Key_Return, Qt.Key_Enter) and ctrl:
            self._canvas.commit_text_edit()
        elif ctrl and ev.key() == Qt.Key_B:
            self.toggle_bold()
        elif ctrl and ev.key() == Qt.Key_U:
            self.toggle_underline()
        else:
            super().keyPressEvent(ev)

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        if self.hold or ev.reason() == Qt.PopupFocusReason:
            return  # 菜单、我们自己的对话框：不算离开
        # 这时候还不知道焦点去了哪（新的焦点控件要等这个事件处理完才定下来），所以稍后再判断
        QTimer.singleShot(0, self._focus_left)

    def _focus_left(self):
        # 看本窗口里焦点落在谁身上（切到别的程序时它不变，所以切出去再回来不会丢掉正在输入的内容）
        now = self.window().focusWidget()
        if self.hold or not self.isVisible() or now is self or (now is not None and self.bar.isAncestorOf(now)):
            return  # 焦点在格式工具条的控件上（比如正在填字号），或者还在输入框：继续编辑
        self._canvas.commit_text_edit()
