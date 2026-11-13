"""生成界面上用的小图标（下拉箭头等）。用法（项目根目录）：  python tools/make_ui_assets.py

输出到 ruipdf/assets/ui/。样式表里的下拉框、数字框一旦自定义外观，Qt 就不再画自带的小箭头，
得给它一张图。标签页的关闭按钮也在这里画。每张图出两份：普通的和 @2x 的（高分屏上 Qt 会自动挑 @2x 那张）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen, QPolygonF  # noqa: E402

COLOR = "#48484A"
DARK = False  # 生成深色风格用的那一套（浅色线条，放在 assets/ui_dark/）


def chevron(size: int, up: bool, scale: int) -> QImage:
    img = QImage(size * scale, size * scale, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    p.setPen(QPen(QColor(COLOR), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    m, mid = size * 0.22, size / 2
    y0, y1 = (size * 0.64, size * 0.36) if up else (size * 0.36, size * 0.64)
    p.drawPolyline(QPolygonF([QPointF(m, y0), QPointF(mid, y1), QPointF(size - m, y0)]))
    p.end()
    return img


def close_mark(size: int, state: str, scale: int) -> QImage:
    """标签页上的关闭按钮：细的灰色叉；鼠标移上去 / 按下时垫一个半透明的圆。"""
    img = QImage(size * scale, size * scale, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(scale, scale)
    if state != "normal":
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(235, 235, 245, 40 if state == "hover" else 70) if DARK
                   else QColor(60, 60, 67, 34 if state == "hover" else 62))
        p.drawEllipse(QPointF(size / 2, size / 2), size / 2 - 0.5, size / 2 - 0.5)
    cross = ("#9A9AA2" if state == "normal" else "#F2F2F7") if DARK else ("#8E8E93" if state == "normal" else "#3A3A3C")
    p.setPen(QPen(QColor(cross), 1.5, Qt.SolidLine, Qt.RoundCap))
    a, b = size * 0.30, size * 0.70
    p.drawLine(QPointF(a, a), QPointF(b, b))
    p.drawLine(QPointF(a, b), QPointF(b, a))
    p.end()
    return img


def main():
    global COLOR, DARK
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    for DARK, COLOR, folder in ((False, "#48484A", "ui"), (True, "#D2D2D8", "ui_dark")):
        write(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ruipdf", "assets", folder))


def write(out):
    os.makedirs(out, exist_ok=True)
    for name, size, up in (("arrow_down", 12, False), ("arrow_up", 12, True),
                           ("spin_down", 9, False), ("spin_up", 9, True)):
        chevron(size, up, 1).save(os.path.join(out, name + ".png"))
        chevron(size, up, 2).save(os.path.join(out, name + "@2x.png"))
    for state in ("normal", "hover", "pressed"):
        name = "tab_close" + ("" if state == "normal" else "_" + state)
        close_mark(16, state, 1).save(os.path.join(out, name + ".png"))
        close_mark(16, state, 2).save(os.path.join(out, name + "@2x.png"))
    print("written:", out, sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
