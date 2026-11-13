"""生成 RuiPDF 的应用图标。用法（项目根目录）：  python tools/make_icon.py [a|b|c]

图标是用代码画的矢量图形，所以任何尺寸都清晰。输出到 ruipdf/assets/：
  icon.png（256×256）、icon.ico（16–256 多尺寸，Windows 用）、icon_preview.png（三套方案对比）
三套方案：a 蓝色（默认）、b 暖橙、c 深色。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPen, QPolygonF)

THEMES = {
    #        背景渐变（上, 下）        纸      折角      文字线    荧光     笔迹      笔身      笔尖
    "a": ("#3D8BFF", "#0A56D0", "#FFFFFF", "#CFE0FF", "#C3D2EA", "#FFE066", "#FF5A4D", "#16233F", "#FFB02E"),
    "b": ("#FFA64D", "#F26B1D", "#FFFDF8", "#FFDDBD", "#E3D2C2", "#FFE873", "#2F6BFF", "#3A2A1E", "#FFE9A8"),
    "c": ("#2B3445", "#151B26", "#F4F6FA", "#C9D1DE", "#BFC8D6", "#FFE066", "#FF5A4D", "#0A84FF", "#FFD27A"),
}


def draw(p: QPainter, s: float, theme: str):
    """在 s×s 的方块里画图标。所有坐标按 256 的设计稿写，再整体缩放。"""
    bg0, bg1, paper, fold, lines, hl, ink, body, nib = THEMES[theme]
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(s / 256, s / 256)

    # 圆角方形底
    grad = QLinearGradient(0, 0, 0, 256)
    grad.setColorAt(0, QColor(bg0))
    grad.setColorAt(1, QColor(bg1))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 54, 54)

    # 一页纸（右上角折角），略微向左倾斜
    p.save()
    p.translate(118, 128)
    p.rotate(-7)
    x0, y0, w, h, c = -62, -86, 124, 172, 34
    shadow = QPainterPath()
    shadow.addRoundedRect(QRectF(x0 + 3, y0 + 7, w, h), 12, 12)
    p.fillPath(shadow, QColor(0, 0, 0, 46))
    page = QPainterPath()
    page.moveTo(x0 + 12, y0)
    page.lineTo(x0 + w - c, y0)
    page.lineTo(x0 + w, y0 + c)
    page.lineTo(x0 + w, y0 + h - 12)
    page.quadTo(x0 + w, y0 + h, x0 + w - 12, y0 + h)
    page.lineTo(x0 + 12, y0 + h)
    page.quadTo(x0, y0 + h, x0, y0 + h - 12)
    page.lineTo(x0, y0 + 12)
    page.quadTo(x0, y0, x0 + 12, y0)
    p.fillPath(page, QColor(paper))
    p.setBrush(QColor(fold))
    p.drawPolygon(QPolygonF([QPointF(x0 + w - c, y0), QPointF(x0 + w, y0 + c), QPointF(x0 + w - c, y0 + c)]))
    # 荧光笔划过的一行 + 两行文字
    p.setPen(QPen(QColor(hl), 20, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x0 + 24, y0 + 62), QPointF(x0 + 86, y0 + 62))
    p.setPen(QPen(QColor(lines), 9, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(x0 + 22, y0 + 30), QPointF(x0 + 70, y0 + 30))
    p.drawLine(QPointF(x0 + 22, y0 + 62), QPointF(x0 + 88, y0 + 62))
    p.drawLine(QPointF(x0 + 22, y0 + 92), QPointF(x0 + 98, y0 + 92))
    p.restore()

    # 手写的一笔：从纸上甩出来的波浪线，终点接笔尖
    stroke = QPainterPath()
    stroke.moveTo(66, 176)
    stroke.cubicTo(84, 150, 98, 196, 116, 172)
    stroke.cubicTo(128, 156, 138, 186, 152, 176)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(ink), 11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(stroke)

    # 笔：从右上斜插下来，笔尖落在笔迹末端
    p.save()
    p.translate(152, 176)
    p.rotate(-47)
    outline = QPen(QColor(255, 255, 255, 235), 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    tip = QPolygonF([QPointF(0, 0), QPointF(30, -13), QPointF(30, 13)])
    for pen, with_fill in ((outline, False), (Qt.NoPen, True)):
        p.setPen(pen)
        p.setBrush(QColor(nib) if with_fill else Qt.NoBrush)
        p.drawPolygon(tip)
        p.setBrush(QColor(body) if with_fill else Qt.NoBrush)
        p.drawRoundedRect(QRectF(30, -13, 92, 26), 6, 6)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(body))
    p.drawPolygon(QPolygonF([QPointF(0, 0), QPointF(11, -4.8), QPointF(11, 4.8)]))  # 笔尖的深色尖端
    p.setBrush(QColor(255, 255, 255, 60))
    p.drawRoundedRect(QRectF(36, -9, 80, 6), 3, 3)  # 笔身高光
    p.restore()


def render(size: int, theme: str) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw(p, size, theme)
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(data)


def write_ico(path: str, theme: str, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)):
    """写多尺寸 .ico（每个尺寸内嵌一张 PNG，Windows Vista 及以上都支持）。"""
    blobs = [png_bytes(render(s, theme)) for s in sizes]
    header = (0).to_bytes(2, "little") + (1).to_bytes(2, "little") + len(sizes).to_bytes(2, "little")
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, blob in zip(sizes, blobs):
        entries += bytes([s % 256, s % 256, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
        entries += len(blob).to_bytes(4, "little") + offset.to_bytes(4, "little")
        offset += len(blob)
    with open(path, "wb") as f:
        f.write(header + entries + b"".join(blobs))


def main():
    theme = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in THEMES else "a"
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ruipdf", "assets")
    os.makedirs(out, exist_ok=True)
    render(256, theme).save(os.path.join(out, "icon.png"))
    write_ico(os.path.join(out, "icon.ico"), theme)

    # 对比图：三套方案的大图 + 任务栏 / 标题栏常见的小尺寸
    sheet = QImage(3 * 300 + 20, 430, QImage.Format_RGB32)
    sheet.fill(QColor("#F2F2F4"))
    p = QPainter(sheet)
    for i, key in enumerate(THEMES):
        x = 20 + i * 300
        p.drawImage(x + 12, 20, render(256, key))
        cx = x + 12
        for s in (64, 48, 32, 24, 16):
            p.drawImage(cx, 300 + (64 - s) // 2, render(s, key))
            cx += s + 12
        p.setPen(QColor("#6E6E73"))
        p.drawText(x + 12, 400, f"{key}" + ("  (default)" if key == "a" else ""))
    p.end()
    sheet.save(os.path.join(out, "icon_preview.png"))
    print("written:", out, "theme", theme)


if __name__ == "__main__":
    main()
