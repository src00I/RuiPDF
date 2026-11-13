"""「新建笔记」对话框：选模板、纸张方向、页数。"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QListView,
                               QListWidget, QListWidgetItem, QSpinBox, QVBoxLayout)

from .i18n import T
from .templates import TEMPLATES, preview


class NewNoteDialog(QDialog):
    def __init__(self, parent=None, last_template="lined"):
        super().__init__(parent)
        self.setWindowTitle(T("新建笔记"))
        self.resize(720, 560)
        lay = QVBoxLayout(self)

        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setMovement(QListView.Static)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setSpacing(10)
        self.list.setIconSize(QSize(140, 198))
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        lay.addWidget(self.list, 1)

        form = QFormLayout()
        self.cb_orient = QComboBox()
        self.cb_orient.addItem(T("竖向 A4"), False)
        self.cb_orient.addItem(T("横向 A4"), True)
        self.cb_orient.currentIndexChanged.connect(self._fill)
        self.sp_pages = QSpinBox()
        self.sp_pages.setRange(1, 300)
        self.sp_pages.setValue(5)
        self.sp_pages.setToolTip(T("之后随时可以用 Ctrl+Shift+N 在当前页后面加一页同样的纸"))
        form.addRow(T("纸张"), self.cb_orient)
        form.addRow(T("页数"), self.sp_pages)
        lay.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(T("创建"))
        box.button(QDialogButtonBox.Cancel).setText(T("取消"))
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

        self._want = last_template
        self._fill()

    def _fill(self):
        """按当前纸张方向重画预览图。"""
        cur = self.template() or self._want
        landscape = self.landscape()
        self.list.clear()
        self.list.setIconSize(QSize(198, 140) if landscape else QSize(140, 198))
        for key, name in TEMPLATES:
            pm = QPixmap()
            pm.loadFromData(preview(key, landscape, 396 if landscape else 280))
            pm.setDevicePixelRatio(2)
            it = QListWidgetItem(_framed(pm), name)
            it.setData(Qt.UserRole, key)
            it.setTextAlignment(Qt.AlignHCenter)
            self.list.addItem(it)
            if key == cur:
                self.list.setCurrentItem(it)
        if self.list.currentItem() is None:
            self.list.setCurrentRow(0)

    def template(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def landscape(self) -> bool:
        return bool(self.cb_orient.currentData())

    def pages(self) -> int:
        return self.sp_pages.value()


def _framed(pm: QPixmap) -> QIcon:
    """给预览图加一圈细边，白纸在白底上才看得出边界。"""
    from PySide6.QtGui import QColor, QPainter
    out = QPixmap(pm)
    p = QPainter(out)
    p.setPen(QColor("#B8B8C0"))
    p.drawRect(0, 0, round(out.width() / out.devicePixelRatio()) - 1,
               round(out.height() / out.devicePixelRatio()) - 1)
    p.end()
    icon = QIcon(out)
    icon.addPixmap(out, QIcon.Selected)  # 选中时不要整体染色
    return icon
