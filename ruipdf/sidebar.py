"""侧栏：缩略图、PDF 目录、书签。显示的是当前标签页的文档。"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QPushButton, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .aipanel import AIPanel
from .corners import round_corners
from .i18n import T
from .stroke import BOX_KINDS

THUMB_W = 150


SEARCH_LIST_MAX = 500  # 搜索结果列表最多列这么多条（"的"这种词一搜几千处，全列出来会卡）


class Sidebar(QTabWidget):
    searchRequested = Signal(str)  # 在搜索页的输入框里按了回车
    hitActivated = Signal(int)     # 点了结果列表里的第几条

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = None
        self.setMinimumWidth(THUMB_W + 50)

        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.IconMode)
        self.thumbs.setFlow(QListView.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListView.Static)
        self.thumbs.setResizeMode(QListView.Adjust)
        self.thumbs.setSpacing(6)
        self.thumbs.setIconSize(QSize(THUMB_W, int(THUMB_W * 1.5)))
        self.thumbs.itemClicked.connect(lambda it: self._jump(self.thumbs.row(it)))
        self.addTab(self.thumbs, T("缩略图"))

        self.toc = QTreeWidget()
        self.toc.setHeaderHidden(True)
        self.toc.itemClicked.connect(lambda it, _: self._jump(it.data(0, Qt.UserRole)))
        self.addTab(self.toc, T("目录"))

        marks = QWidget()
        lay = QVBoxLayout(marks)
        lay.setContentsMargins(4, 4, 4, 4)
        row = QHBoxLayout()
        b_add, b_del = QPushButton(T("＋ 当前页")), QPushButton(T("删除"))
        b_add.clicked.connect(self.add_bookmark)
        b_del.clicked.connect(self._del_bookmark)
        row.addWidget(b_add)
        row.addWidget(b_del)
        lay.addLayout(row)
        self.marks = QListWidget()
        self.marks.itemClicked.connect(lambda it: self._jump(it.data(Qt.UserRole)))
        lay.addWidget(self.marks)
        self.addTab(marks, T("书签"))

        self.notes = QTreeWidget()
        self.notes.setHeaderHidden(True)
        self.notes.itemClicked.connect(self._note_clicked)
        self.addTab(self.notes, T("标注"))
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(400)
        self._notes_timer.timeout.connect(self._fill_notes)

        # 搜索：输入框 + 全部结果的列表（每条是页码和那一行的文字），点一条跳过去。
        # 真正的搜索和高亮在主窗口那边（和底部的查找栏共用一份结果），这里只管显示和发信号。
        find = QWidget()
        lay = QVBoxLayout(find)
        lay.setContentsMargins(4, 4, 4, 4)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(T("搜索全文，按回车"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.returnPressed.connect(lambda: self.searchRequested.emit(self.search_edit.text().strip()))
        lay.addWidget(self.search_edit)
        self.search_info = QLabel("")
        lay.addWidget(self.search_info)
        self.search_list = QListWidget()
        self.search_list.setWordWrap(True)
        self.search_list.itemClicked.connect(lambda it: self.hitActivated.emit(it.data(Qt.UserRole)))
        lay.addWidget(self.search_list)
        self.search_tab = self.addTab(find, T("搜索"))

        self.ai = AIPanel()
        self.addTab(self.ai, "Claude")
        for i in range(self.count()):  # 每一页内容的上面两个角切圆（下面两个角由整个侧栏的圆角管）
            round_corners(self.widget(i), (0, 1))

        self._queue = []
        self._timer = QTimer(self)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self._render_some)

    # ------------------------------------------------------------------
    def show_search(self):
        """切到搜索那一页，光标放进输入框。"""
        self.setCurrentIndex(self.search_tab)
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def set_search_results(self, text: str, hits):
        """显示一次搜索的全部结果。hits = [(页号, 那一行的文字)]；text 为空表示清掉。"""
        self.search_list.clear()
        if text and self.search_edit.text().strip() != text:
            self.search_edit.setText(text)
        self.search_info.setText("" if not text else T("共 {} 处").format(len(hits)) if hits else T("没有找到"))
        for i, (page, line) in enumerate(hits[:SEARCH_LIST_MAX]):
            item = QListWidgetItem(T("第 {} 页").format(page + 1) + "　" + line)
            item.setData(Qt.UserRole, i)
            self.search_list.addItem(item)
        if len(hits) > SEARCH_LIST_MAX:
            self.search_info.setText(T("共 {} 处（列表只显示前 {} 处）").format(len(hits), SEARCH_LIST_MAX))

    def select_hit(self, i: int):
        """把列表里第 i 条标成当前这一处（用"上一个 / 下一个"走的时候跟着动）。"""
        if 0 <= i < self.search_list.count():
            self.search_list.setCurrentRow(i)
            self.search_list.scrollToItem(self.search_list.item(i))

    def set_canvas(self, canvas):
        """切换到另一个标签页的文档（canvas 为 None 表示没有打开的文档）。"""
        self.canvas = canvas
        self.rebuild()

    def rebuild(self):
        self.thumbs.clear()
        self.toc.clear()
        self.marks.clear()
        self.notes.clear()
        self._queue = []
        doc = self.canvas.doc if self.canvas else None
        if not doc:
            self._timer.stop()
            return
        for i, (w, h) in enumerate(doc.sizes):
            it = QListWidgetItem(str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            tw = THUMB_W
            th = max(20, min(int(THUMB_W * 2), round(THUMB_W * h / w)))
            ph = QPixmap(tw, th)
            ph.fill(QColor("#e8e8e8"))
            it.setIcon(QIcon(ph))
            it.setSizeHint(QSize(THUMB_W + 16, th + 26))
            self.thumbs.addItem(it)
        self._queue = list(range(len(doc.sizes)))
        if self.isVisible():
            self._timer.start()
        self.set_current(self.canvas.current_page())

        stack = []  # 目录按层级建树
        for lvl, title, page in doc.toc():
            node = QTreeWidgetItem([title])
            node.setData(0, Qt.UserRole, page)
            while len(stack) >= lvl and stack:
                stack.pop()
            (stack[-1].addChild if stack else self.toc.addTopLevelItem)(node)
            stack.append(node)
        self.toc.expandToDepth(0)
        self._fill_marks()
        self._fill_notes()

    def _render_some(self):
        """空闲时每次渲染几张缩略图，不卡界面。优先渲染当前页附近。"""
        doc = self.canvas.doc if self.canvas else None
        if not doc or not self._queue or not self.isVisible():
            self._timer.stop()  # 侧栏收起时不渲染，展开时再继续
            return
        if self.canvas.busy():
            return
        cur = self.canvas.current_page()
        self._queue.sort(key=lambda i: abs(i - cur))
        for i in self._queue[:3]:
            if i < len(doc.sizes) and i < self.thumbs.count():
                w, h = doc.sizes[i]
                dpr = self.devicePixelRatioF()
                img = doc.render(i, THUMB_W * dpr / w)
                pm = QPixmap.fromImage(img)
                painter = QPainter(pm)
                painter.setPen(QColor("#b0b0b0"))
                painter.drawRect(0, 0, pm.width() - 1, pm.height() - 1)
                painter.end()
                pm.setDevicePixelRatio(dpr)
                icon = QIcon(pm)
                icon.addPixmap(pm, QIcon.Selected)  # 选中时不要给缩略图整体染色
                self.thumbs.item(i).setIcon(icon)
        del self._queue[:3]

    def showEvent(self, ev):
        super().showEvent(ev)
        self._fill_marks()
        self._fill_notes()
        if self._queue:
            self._timer.start()

    def set_current(self, page: int):
        if 0 <= page < self.thumbs.count() and self.thumbs.currentRow() != page:
            self.thumbs.setCurrentRow(page)
            self.thumbs.scrollToItem(self.thumbs.item(page))

    def _jump(self, page):
        if self.canvas and page is not None:
            self.canvas.go_to_page(int(page))
            self.canvas.setFocus()

    # ------------------------------------------------------------------ 标注汇总
    def notes_changed(self):
        """笔迹有改动：稍后刷新汇总（连续写字时不会每一笔都刷新）。"""
        if self.isVisible():
            self._notes_timer.start()

    def _fill_notes(self):
        """按颜色分组列出所有标注，每组下面是有这种颜色的页，点击跳转。"""
        self.notes.clear()
        if not (self.canvas and self.canvas.doc):
            return
        groups = {}  # (排序, 名称, 颜色, 方形图标) -> {页号: [数量, 最靠上的位置]}
        for page, items in self.canvas.strokes.items():
            for it in items:
                if it.kind == "mask":
                    key = (2, T("遮挡块"), it.color, True)
                elif it.kind == "hl":
                    key = (1, T("荧光笔"), it.color, True)
                elif it.kind in BOX_KINDS:
                    key = (3, T("图片 / 粘贴的内容"), it.color, True)
                else:
                    key = (0, T("笔迹"), it.color, False)
                entry = groups.setdefault(key, {}).setdefault(page, [0, float("inf")])
                entry[0] += 1
                entry[1] = min(entry[1], it.bbox().top())
        order = sorted(groups, key=lambda k: (k[0], -sum(v[0] for v in groups[k].values())))
        for key in order:
            _, name, color, square = key
            pages = groups[key]
            top = QTreeWidgetItem([T("{}  {} 处 · {} 页").format(name, sum(v[0] for v in pages.values()), len(pages))])
            top.setIcon(0, _swatch(color, square))
            for page in sorted(pages):
                n, y = pages[page]
                child = QTreeWidgetItem([T("第 {} 页（{} 处）").format(page + 1, n)])
                child.setData(0, Qt.UserRole, (page, y))
                top.addChild(child)
            self.notes.addTopLevelItem(top)
        self.notes.expandAll()

    def _note_clicked(self, item, _col):
        data = item.data(0, Qt.UserRole)
        if data is None and item.childCount():
            data = item.child(0).data(0, Qt.UserRole)  # 点分组 = 跳到第一处
        if data and self.canvas:
            self.canvas.go_to_point(int(data[0]), float(data[1]))
            self.canvas.setFocus()

    # ------------------------------------------------------------------ 书签
    def _fill_marks(self):
        self.marks.clear()
        doc = self.canvas.doc if self.canvas else None
        if not doc:
            return
        for page, title in doc.bookmarks():
            it = QListWidgetItem(T("{}  （第 {} 页）").format(title, page + 1))
            it.setData(Qt.UserRole, page)
            self.marks.addItem(it)

    def add_bookmark(self):
        doc = self.canvas.doc if self.canvas else None
        if not doc:
            return
        page = self.canvas.current_page()
        old = dict(doc.bookmarks()).get(page, T("第 {} 页").format(page + 1))
        title, ok = QInputDialog.getText(self, T("书签"), T("书签名称："), text=old)
        if ok and title.strip():
            doc.set_bookmark(page, title.strip())
            self.canvas.changed.emit()
            self._fill_marks()
            self.setCurrentIndex(2)

    def _del_bookmark(self):
        it = self.marks.currentItem()
        if it and self.canvas and self.canvas.doc:
            self.canvas.doc.set_bookmark(it.data(Qt.UserRole), None)
            self.canvas.changed.emit()
            self._fill_marks()


def _swatch(color: str, square: bool) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor("#888888"))
    p.setBrush(QColor(color))
    if square:
        p.drawRoundedRect(1, 3, 14, 10, 2, 2)
    else:
        p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QIcon(pm)
