"""冒烟测试：不需要屏幕和数位板，用模拟的鼠标输入把主要流程跑一遍。

用法（在项目根目录）：  python tests/smoke.py
全部通过会打印 ALL OK；任何一步失败会抛出 AssertionError。
它只验证逻辑（数据、保存、重开），不验证手感、清晰度、光标这类只能在真机上看的东西。
"""
import math
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf  # noqa: E402
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

tmp = tempfile.mkdtemp(prefix="ruipdf_smoke_")
# 用独立的设置文件，不动你平时的设置（必须在导入 ruipdf 之前设好，见 ruipdf/appsettings.py）
os.environ["RUIPDF_SETTINGS"] = os.path.join(tmp, "settings.ini")

app = QApplication([])
import ruipdf.canvas as cv  # noqa: E402
from ruipdf.appsettings import app_settings  # noqa: E402
from ruipdf.document import Document  # noqa: E402
from ruipdf.mainwindow import MainWindow  # noqa: E402
from ruipdf.templates import TEMPLATES, create_notebook  # noqa: E402

assert os.path.normcase(app_settings().fileName()) == os.path.normcase(os.environ["RUIPDF_SETTINGS"]), \
    "测试必须用自己的设置文件，否则会改掉平时用的设置"

# ---- 准备一份 3 页的测试 PDF（第 3 页旋转 90°）
src = os.path.join(tmp, "lecture.pdf")
d = pymupdf.open()
for i in range(3):
    p = d.new_page()
    p.insert_text((72, 100), f"Lecture page {i}", fontsize=24)
    p.insert_text((72, 200), "Ohm's law: U = R * I", fontsize=14)
d[2].set_rotation(90)
d.save(src)
d.close()

w = MainWindow()
w.show()
app.processEvents()
w.open_file(src)
c = w.canvas
c.set_zoom(1.0)
c.go_to_page(0)
app.processEvents()


def drag(points, button=Qt.LeftButton):
    QTest.mousePress(c, button, Qt.NoModifier, QPoint(*points[0]))
    for pt in points[1:]:
        QTest.mouseMove(c, QPoint(*pt))
    QTest.mouseRelease(c, button, Qt.NoModifier, QPoint(*points[-1]))


def line(x0, y0, x1, y1, n=12):
    return [(int(x0 + (x1 - x0) * k / n), int(y0 + (y1 - y0) * k / n)) for k in range(n + 1)]


def P(page, x, y):
    r = c.page_rect(page)
    return r.x() + x, r.y() + y


def loop(page, x0, y0, x1, y1):
    corners = [P(page, x0, y0), P(page, x1, y0), P(page, x1, y1), P(page, x0, y1), P(page, x0, y0)]
    out = []
    for a, b in zip(corners, corners[1:]):
        out += line(*a, *b, 8)
    return out


# ---- 1. 笔、荧光笔、形状、文本、遮挡块
w.act_pen.trigger()
drag([(P(0, 100, 300)[0] + k * 4, int(P(0, 100, 300)[1] + 10 * math.sin(k / 4))) for k in range(40)])
w.act_hl.trigger()
drag(line(*P(0, 72, 196), *P(0, 260, 196)))
for kind, a, b in (("line", (80, 400), (250, 402)), ("arrow", (80, 430), (250, 470)),
                   ("rect", (300, 400), (380, 460)), ("ellipse", (400, 400), (480, 460))):
    w._pick_shape(kind)
    drag(line(*P(0, *a), *P(0, *b)))
w.act_text.trigger()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, 100, 520)))
assert c.editing_text() and c._editor.isVisible(), "点一下页面应该原地出现输入框"
QTest.keyClicks(c._editor, "smoke")
c._editor.insertPlainText(" 测试")
QTest.keyClick(c._editor, Qt.Key_Return, Qt.ControlModifier)  # Ctrl+回车确认
assert not c.editing_text() and not c._editor.isVisible()
w.act_mask.trigger()
drag(line(*P(0, 60, 560), *P(0, 200, 600)))
kinds = [s.kind for s in c.strokes[0]]
assert kinds == ["pen", "hl", "poly", "poly", "poly", "poly", "text", "mask"], kinds

# ---- 1b. 文本：改已有的、Esc 放弃、删空、换工具时自动确认
text_item = c.strokes[0][6]
assert text_item.text == "smoke 测试", text_item.text
w.act_text.trigger()
tx, ty = text_item.x + 5, text_item.y + text_item.size * 0.6
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, tx, ty)))
assert c.editing_text() and c._editor.toPlainText() == "smoke 测试" and text_item not in c.strokes[0]
QTest.keyClicks(c._editor, "!")
QTest.keyClick(c._editor, Qt.Key_Escape)  # 放弃：恢复原样，叠放位置不变
assert c.strokes[0][6] is text_item and text_item.text == "smoke 测试"
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, tx, ty)))
QTest.keyClicks(c._editor, "!")
w.act_pen.trigger()  # 换工具 = 确认
assert not c.editing_text() and c.strokes[0][6] is text_item and text_item.text == "smoke 测试!"
c.undo()
assert text_item.text == "smoke 测试"
w.act_text.trigger()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, tx, ty)))
c._editor.setPlainText("")
c.commit_text_edit()  # 删空 = 删除这个文本框
assert text_item not in c.strokes[0] and len(c.strokes[0]) == 7
c.undo()
assert c.strokes[0][6] is text_item and len(c.strokes[0]) == 8
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, 300, 640)))  # 空白处新建但什么都不输：不留东西
c.commit_text_edit()
assert len(c.strokes[0]) == 8
w.act_pen.trigger()

# ---- 1c. 文本框里选中一部分改格式：加粗、下划线、颜色、字号、字体
from PySide6.QtGui import QTextCursor  # noqa: E402

w.act_text.trigger()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, 300, 640)))
ed = c._editor
assert ed.bar.isVisible() and not ed.source, "输入时上方应该有格式工具条"
QTest.keyClicks(ed, "abc def")
ed.insertPlainText("\n第二行")


def select(a, b):
    cur = ed.textCursor()
    cur.setPosition(a)
    cur.setPosition(b, QTextCursor.KeepAnchor)
    ed.setTextCursor(cur)


select(0, 3)
QTest.keyClick(ed, Qt.Key_B, Qt.ControlModifier)        # abc 加粗
assert ed.bar.b_bold.isChecked()
select(4, 7)
ed.bar.b_under.click()                                   # def 下划线
ed.set_color("#D32F2F")                                  # 并且改成红色
select(8, 11)
ed.bar.size.setValue(20.0)                               # 第二行改成 20 pt
ed.set_font_family("SimSun")
assert c.editing_text(), "点格式按钮不应该结束输入"
# 用真实的鼠标点击点格式按钮（出过事故：按钮不接焦点，焦点被 Qt 交给了画布，输入被当成"点别处"结束了）
select(8, 11)
QTest.mouseClick(ed.bar.b_bold, Qt.LeftButton)
app.processEvents()
assert c.editing_text() and ed.hasFocus() and ed.bar.b_bold.isChecked(), "真实点击加粗按钮后应该还在输入"
QTest.mouseClick(ed.bar.b_bold, Qt.LeftButton)  # 再点一次取消加粗
QTest.mouseClick(ed.bar.size, Qt.LeftButton)     # 点进字号框（它会拿到焦点）也不算离开
app.processEvents()
assert c.editing_text() and not ed.bar.b_bold.isChecked()
ed.setFocus()
QTest.keyClick(ed, Qt.Key_Return, Qt.ControlModifier)
fmt_item = c.strokes[0][-1]
base = fmt_item.size
assert fmt_item.text == "abc def\n第二行" and fmt_item.runs == [
    [["abc", {"b": 1}], [" ", {}], ["def", {"u": 1, "c": "#d32f2f"}]],
    [["第二行", {"s": 20.0, "f": "SimSun"}]]], fmt_item.runs
pieces, tw, th = fmt_item.layout()
assert sorted(col for col, _p in pieces) == sorted([fmt_item.color, "#d32f2f"]), [col for col, _p in pieces]
plain_h = cv.TextItem("abc def\n第二行", 0, 0, base, "#111111").layout()[2]
assert th > plain_h + 3, "第二行字号大了，整框应该更高"
# 再点进去：格式原样回到输入框；什么都不改就确认，不产生撤销记录
n_undo = len(c.undo_stack)
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, fmt_item.x + 3, fmt_item.y + base * 0.6)))
assert c.editing_text() and ed.runs() == (fmt_item.text, fmt_item.runs)
select(1, 2)
assert ed.bar.b_bold.isChecked() and abs(ed.bar.size.value() - base) < 0.06
select(9, 10)
assert not ed.bar.b_bold.isChecked() and ed.bar.size.value() == 20.0
QTest.keyClick(ed, Qt.Key_Return, Qt.ControlModifier)
assert len(c.undo_stack) == n_undo and c.strokes[0][-1] is fmt_item
# 整体缩放时单独设过的字号跟着变；撤销能恢复；JSON 往返不丢格式；全部取消格式后变回纯文本
st = fmt_item.get_state()
fmt_item.transform(lambda x, y: (x, y), 0.5)
assert fmt_item.runs[1][0][1]["s"] == 10.0 and abs(fmt_item.size - base / 2) < 1e-6
fmt_item.set_state(st)
again_item = cv.item_from_json(fmt_item.to_json())
assert again_item.runs == fmt_item.runs and again_item.layout()[1:] == fmt_item.layout()[1:]
assert cv.item_from_json({"k": "text", "c": "#111111", "s": 10, "x": 0, "y": 0, "t": "a",
                          "runs": [[["a", {"c": "#111111", "s": 10}]]]}).runs is None
c.undo()  # 撤销新建（后面的用例按原来的 8 个对象写的，这个带格式的文本框不留在页面上）
assert fmt_item not in c.strokes[0] and len(c.strokes[0]) == 8
c.redo_stack.clear()
w.act_pen.trigger()

# ---- 1c2. 改粘贴片段的原文时，格式按钮是开关：再点一次是去掉标记，不是再套一层
ed.begin("甲乙丙丁\n\n- 列表项\n\n$$\nx\n$$\n尾巴", 11, 1.0, "#111111", None, 400, 300)
assert ed.source
select(1, 3)
ed.toggle_bold()
assert ed.toPlainText().startswith("甲**乙丙**丁"), ed.toPlainText()
ed.toggle_bold()                                  # 选区现在包着标记：取消
assert ed.toPlainText().startswith("甲乙丙丁"), ed.toPlainText()
select(1, 3)
ed.toggle_bold()
select(3, 5)                                      # 只选中里面的字（标记紧贴在外面）：也是取消
ed.toggle_bold()
assert ed.toPlainText().startswith("甲乙丙丁"), ed.toPlainText()
select(0, len(ed.toPlainText()))                  # 跨行：逐行加，列表记号留在外面，公式块不动
ed.toggle_bold()
assert ed.toPlainText() == "**甲乙丙丁**\n\n- **列表项**\n\n$$\nx\n$$\n**尾巴**", ed.toPlainText()
ed.toggle_bold()
assert ed.toPlainText() == "甲乙丙丁\n\n- 列表项\n\n$$\nx\n$$\n尾巴", ed.toPlainText()
ed.setPlainText("前\n****叠了两层****\n后")       # 以前点多了叠出来的：一次去干净
select(2, 2 + len("****叠了两层****") + 1)        # 选区末尾带着换行也没关系
ed.toggle_bold()
assert ed.toPlainText() == "前\n叠了两层\n后", ed.toPlainText()
select(2, 6)
ed.toggle_underline()
assert ed.toPlainText() == "前\n<u>叠了两层</u>\n后"
ed.toggle_underline()
assert ed.toPlainText() == "前\n叠了两层\n后"
select(2, 6)
ed.set_color("#D32F2F")
ed.set_color("#1565C0")                           # 换颜色是替换，不是再套一层
assert ed.toPlainText() == '前\n<span style="color:#1565c0">叠了两层</span>\n后', ed.toPlainText()
ed.set_size(16)                                   # 另一种样式可以套在外面
ed.set_size(18)
assert ed.toPlainText() == '前\n<span style="font-size:18pt"><span style="color:#1565c0">叠了两层</span></span>\n后'

# ---- 1d. 抬笔事件丢了之后不能把页面卡死（出过事故：滚轮、缩放、鼠标点击全部失效）
from PySide6.QtCore import QEvent, QPointF  # noqa: E402
from PySide6.QtGui import QPointingDevice, QTabletEvent, QWheelEvent  # noqa: E402


def pen(kind, x, y, pressure=0.5, buttons=Qt.LeftButton):
    pos = QPointF(x, y)
    ev = QTabletEvent(kind, QPointingDevice.primaryPointingDevice(), pos, QPointF(c.mapToGlobal(pos.toPoint())),
                      pressure, 0, 0, 0, 0, 0, Qt.NoModifier, Qt.LeftButton, buttons)
    app.sendEvent(c, ev)
    return ev


def wheel(dy):
    pos = QPointF(c.width() / 2, c.height() / 2)
    app.sendEvent(c, QWheelEvent(pos, QPointF(c.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, dy),
                                 Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False))


n0 = len(c.strokes[0])
px, py = P(0, 320, 700)
pen(QEvent.Type.TabletPress, px, py)
pen(QEvent.Type.TabletMove, px + 20, py + 5)
assert c._tablet_down and c._mode == "pen"
sy0 = c.sy
wheel(-240)
assert c.sy == sy0, "笔正按着写字的时候，滚轮不应该滚动页面"
c._tablet_clock.invalidate()   # 相当于"已经很久没有数位板事件了"：抬笔事件丢了
wheel(-240)
assert c.sy != sy0 and not c._tablet_down and c._mode is None, "抬笔丢了之后滚轮应该恢复可用"
assert len(c.strokes[0]) == n0 + 1, "卡住的那一笔应该照常落下"
c.scroll_to(sy0)
pen(QEvent.Type.TabletPress, px, py + 30)
c._tablet_clock.invalidate()
z0 = c.zoom
c.set_zoom(z0 * 1.2)
assert abs(c.zoom - z0 * 1.2) < 1e-6 and c._mode is None, "抬笔丢了之后缩放应该恢复可用"
c.set_zoom(z0)
c.go_to_page(0)
app.processEvents()
px, py = P(0, 320, 700)
pen(QEvent.Type.TabletPress, px, py + 60)
c._tablet_clock.invalidate()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(int(px) + 60, int(py)))
assert not c._tablet_down and c._mode is None, "抬笔丢了之后鼠标点击应该恢复可用"
pen(QEvent.Type.TabletPress, px, py + 90)
pen(QEvent.Type.TabletPress, px, py + 120)    # 上一次没抬笔就又落笔：先收掉上一笔
pen(QEvent.Type.TabletRelease, px, py + 120, 0.0, Qt.NoButton)
assert not c._tablet_down and c._mode is None
pen(QEvent.Type.TabletPress, px, py + 150)
c.tabletEvent(QTabletEvent(QEvent.Type.TabletMove, QPointingDevice.primaryPointingDevice(), QPointF(px, py),
                           QPointF(px, py), 0.0, 0, 0, 0, 0, 0, Qt.NoModifier, Qt.NoButton, Qt.NoButton))
assert not c._tablet_down and c._mode is None, "没有压力也没有按键的移动 = 已经抬笔，应该补上"
while len(c.strokes[0]) > n0:   # 清掉这一节画的点，后面的用例按原来的 8 个对象写的
    c.undo()
c.redo_stack.clear()
assert len(c.strokes[0]) == 8

# ---- 1e. 滚动 / 缩放时的"先草稿、后精细"：停下来之后的画面必须和直接精细渲染的逐像素一样
from PySide6.QtGui import QImage  # noqa: E402

assert c.quality > 1, "这一节按书写分辨率 > 1 写的"


def fine(i):
    """第 i 页该有的精细显示图：合成图用面积平均缩到屏幕大小。"""
    dw, dh = c._device_size(i)
    return c._composite(i).scaled(dw, dh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def settle():
    for _ in range(40):  # 空闲时的活一次做一件：做到没有草稿、前后页都备好为止
        c._idle.stop()
        c._idle_work()
        if not c._idle.isActive():
            break


c._drop_images()
c.go_to_page(1)            # 刚滚动过：新进来的页先出草稿
c.repaint()
vis = list(c._visible_pages(0, c.height()))
assert vis and set(vis) <= c._draft and all(i in c.disp for i in vis), (vis, c._draft)
assert all(c.disp[i].width() == c._device_size(i)[0] for i in vis), "草稿也必须正好是屏幕像素大小（1:1 上屏）"
settle()
assert not (set(vis) & c._draft), "停下来之后草稿应该都换成精细的"
for i in vis:
    assert c.disp[i].convertToFormat(QImage.Format_RGB32) == fine(i).convertToFormat(QImage.Format_RGB32), \
        f"第 {i} 页换成精细图之后应该和直接精细渲染的完全一样"
nxt = vis[-1] + 1
assert nxt >= len(c.doc) or nxt in c.disp, "空闲时应该把下一页预先渲染好"
c._moving.invalidate()
c._invalidate(vis[0])      # 没在滚动时（比如改了笔迹）：直接出精细的，不经过草稿
c.repaint()
assert vis[0] not in c._draft and c.disp[vis[0]].convertToFormat(QImage.Format_RGB32) == \
    fine(vis[0]).convertToFormat(QImage.Format_RGB32)
# 连续缩放：每一格不重新渲染，用缩放前的图顶着；停下来才重画；落笔会立刻结束这个状态
z0 = c.zoom
c.set_zoom(z0 * 1.1)
c.set_zoom(z0 * 1.21)
assert c._zoom_timer.isActive() and c._zoom_stale and not c.disp and not c.cache
c.repaint()
assert not c.disp and not c.cache, "缩放过程中不应该渲染页面"
c._zoom_timer.stop()
c._zoom_settled()
c.repaint()
settle()
vis = list(c._visible_pages(0, c.height()))
assert not c._zoom_stale and all(i in c.disp and i not in c._draft for i in vis)
c.set_zoom(z0)
assert c._zoom_timer.isActive()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))   # 点在页面外：不画东西，但要结束缩放状态
assert not c._zoom_timer.isActive() and not c._zoom_stale
c.go_to_page(0)
c.repaint()
settle()

# ---- 2. 撤销 / 重做
c.undo()
assert len(c.strokes[0]) == 7
c.redo()
assert len(c.strokes[0]) == 8

# ---- 3. 套索：选中、移动、复制、粘贴
w.act_lasso.trigger()
drag(loop(0, 80, 280, 280, 320))
assert len(c._sel) == 1 and c._sel[0].kind == "pen", [s.kind for s in c._sel]
x_before = c._sel[0].pts[0][0]
center = c._sel_widget_rect().center()
drag(line(int(center.x()), int(center.y()), int(center.x()) + 40, int(center.y()) + 20, 4))
assert abs(c._sel[0].pts[0][0] - x_before - 40) < 1.5
QTest.keyClick(c, Qt.Key_C, Qt.ControlModifier)
assert not app.clipboard().image().isNull(), "复制后系统剪贴板里应该有图片"
QTest.keyClick(c, Qt.Key_V, Qt.ControlModifier)
assert len(c.strokes[0]) == 9
c.undo()
assert len(c.strokes[0]) == 8

# ---- 4. 区域选择（圈住没有笔迹的地方）与截图
c.clear_selection()
drag(loop(0, 60, 80, 330, 130))
assert c._region is not None and not c._sel
assert c.grab_image(*c.ask_target()).width() > 200

# ---- 5. 页面操作：空白页、留白、书签
c.clear_selection()
c.go_to_page(0)
app.processEvents()
c.insert_blank_after()
assert len(c.doc) == 4 and c.doc.is_blank(1)
c.go_to_page(0)
app.processEvents()
w0 = c.doc.sizes[0][0]
c.add_margin("right")
assert c.doc.sizes[0][0] > w0
# ---- 5b. 留白：自定义宽度、改小、去掉；记在页面里（保存后还能撤销）；自动备份能重放；旋转页也对
h0 = c.doc.sizes[0][1]
mr0, mb0 = c.doc.page_margin(0)
assert abs(mr0 - (c.doc.sizes[0][0] - w0)) < 0.01 and mb0 == 0, "加了多少留白要记在页面里"
c.set_margins(100, 50, 0)                       # 自己定宽度：右 100 pt，下 50 pt
assert abs(c.doc.sizes[0][0] - (w0 + 100)) < 0.01 and abs(c.doc.sizes[0][1] - (h0 + 50)) < 0.01
assert c.doc.page_margin(0) == (100.0, 50.0)
from ruipdf.stroke import Stroke  # noqa: E402


def _line(x0, y0, x1, y1):
    st = Stroke("#000000", 1.5)
    st.add(x0, y0, 1.0)
    st.add(x1, y1, 1.0)
    return st


inside = _line(50, 60, 80, 90)
in_margin = _line(w0 + 60, 60, w0 + 90, 90)   # 画在右侧留白里
c.strokes.setdefault(0, []).extend([inside, in_margin])
assert c.margin_loss(100, 50, 0) == [] and c.margin_loss(20, 50, 0) == [in_margin]
c.set_margins(20, 50, 0)                        # 改小：留白里被裁掉的那部分上的对象一起删掉
assert abs(c.doc.sizes[0][0] - (w0 + 20)) < 0.01 and in_margin not in c.strokes[0] and inside in c.strokes[0]
assert c.undo_stack == [], "改留白是页面结构改动，撤销记录要清空"
c.set_margins(0, 0, 0)                          # 去掉
assert abs(c.doc.sizes[0][0] - w0) < 0.01 and abs(c.doc.sizes[0][1] - h0) < 0.01 and c.doc.page_margin(0) == (0.0, 0.0)
assert inside in c.strokes[0]
c.strokes[0].remove(inside)
rot = len(c.doc) - 1                            # 最后一页是旋转 90° 的
rw, rh = c.doc.sizes[rot]
c.set_margins(40, 30, rot)
assert abs(c.doc.sizes[rot][0] - (rw + 40)) < 0.01 and abs(c.doc.sizes[rot][1] - (rh + 30)) < 0.01
c.set_margins(0, 0, rot)
assert abs(c.doc.sizes[rot][0] - rw) < 0.01 and abs(c.doc.sizes[rot][1] - rh) < 0.01
c.set_margins(70, 0, 0)                         # 留一块，下面验证：写进文件后重开还记得，备份里的改动能重放出一样的页面
blob = os.path.join(tmp, "margin_check.pdf")
c.doc.doc.save(blob)
chk = Document(blob)
assert chk.page_margin(0) == (70.0, 0.0) and abs(chk.sizes[0][0] - (w0 + 70)) < 0.01
chk.set_margin(0, "right", 0)
assert abs(chk.sizes[0][0] - w0) < 0.01, "保存后重开也要能去掉留白"
chk.close()
replay = Document(src)
replay.apply_ops(c.doc.ops)
assert len(replay) == len(c.doc) and all(abs(a - b) < 0.01 for x, y in zip(replay.sizes, c.doc.sizes) for a, b in zip(x, y)),     "自动备份里记的页面改动重放出来要和现在一样"
assert replay.page_margin(0) == c.doc.page_margin(0)
replay.close()
c.go_to_page(0)
app.processEvents()
c.doc.set_bookmark(1, "书签 test")

# ---- 6. 搜索（含旋转页）
hits = c.doc.search("Ohm")
assert len(hits) == 3 and sorted({h[0] for h in hits}) == [0, 2, 3], hits

# ---- 7. 保存 -> 用别的方式打开能看到笔迹 -> 重新载入可编辑
assert w.save()
ext = pymupdf.open(src)
assert len(ext) == 4
assert len(ext[0].get_drawings()) > 0, "保存后的 PDF 页面里应该画有笔迹"
ext.close()
again = Document(src)
loaded = again.load_strokes()
assert [s.kind for s in loaded[0]] == kinds, [s.kind for s in loaded[0]]
assert again.bookmarks() == [(1, "书签 test")]
again.close()

# ---- 7b. 选字：拖过 PDF 自带的文字，复制成文本
c.go_to_page(0)
c.set_zoom(1.0)
app.processEvents()
w.act_select.trigger()
drag(line(*P(0, 74, 195), *P(0, 190, 195)))  # 第 0 页 "Ohm's law: U = R * I" 这一行的前半段
picked = c.selected_text()
assert picked.startswith("Ohm's law") and "\n" not in picked, repr(picked)
QTest.keyClick(c, Qt.Key_C, Qt.ControlModifier)
assert app.clipboard().text() == picked, (app.clipboard().text(), picked)
drag(line(*P(0, 74, 92), *P(0, 190, 195)))  # 跨两行：两段之间应该换行
assert c.selected_text().split("\n")[0].startswith("Lecture page 0"), repr(c.selected_text())
assert "Ohm" in c.selected_text().split("\n")[1], repr(c.selected_text())
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*P(0, 300, 300)))  # 点一下不拖：取消选中
assert c.selected_text() == ""
# 旋转 90° 的那一页（前面插过空白页，页号变了）：字符框要落在显示出来的页面范围内，也能选中
rot = next(i for i in range(len(c.doc)) if "Lecture page 2" in c.doc.page_text(i))
pw, ph = c.doc.sizes[rot]
assert pw > ph, "这一页显示出来应该是横的"
chars = c.doc.page_chars(rot)
assert chars and all(-1 <= ch[0] and ch[2] <= pw + 1 and -1 <= ch[1] and ch[3] <= ph + 1 for ch in chars)
c._set_text_sel((rot, 0, len(chars) - 1))
assert "Lecture page 2" in c.selected_text() and c.text_sel_target()[0] == rot, repr(c.selected_text())
w.act_pen.trigger()
assert c.selected_text() == "", "换工具后选中的文字应该取消"

# ---- 7c. 套索圈出的区域：拖角改大小、拖中间移动、限制在页面内
c.go_to_page(0)
app.processEvents()
w.act_lasso.trigger()
drag(loop(0, 300, 620, 400, 700))  # 这一块没有笔迹：成为"区域"
assert c._region is not None and not c._sel
r0 = c._region[1]
drag(line(*P(0, r0.right(), r0.bottom()), *P(0, r0.right() + 60, r0.bottom() + 30), 5))  # 右下角往外拖
r1 = c._region[1]
assert abs(r1.width() - r0.width() - 60) < 2 and abs(r1.height() - r0.height() - 30) < 2, (r0, r1)
assert abs(r1.left() - r0.left()) < 0.01 and abs(r1.top() - r0.top()) < 0.01
drag(line(*P(0, r1.left(), r1.center().y()), *P(0, r1.left() - 40, r1.center().y() + 50), 5))  # 左边：只改左边
r2 = c._region[1]
assert abs(r2.left() - r1.left() + 40) < 2 and abs(r2.right() - r1.right()) < 0.01 and abs(r2.height() - r1.height()) < 0.01
drag(line(*P(0, r2.center().x(), r2.center().y()), *P(0, r2.center().x() - 30, r2.center().y() - 20), 5))  # 中间：移动
r3 = c._region[1]
assert abs(r3.left() - r2.left() + 30) < 2 and abs(r3.width() - r2.width()) < 0.01 and abs(r3.height() - r2.height()) < 0.01
drag(line(*P(0, r3.right(), r3.top()), *P(0, r3.left() - 200, r3.bottom() + 200), 5))  # 右上角拖过头：不翻转，停在最小尺寸
r4 = c._region[1]
assert r4.width() >= cv.REGION_MIN_PT - 0.01 and r4.height() >= cv.REGION_MIN_PT - 0.01, r4
drag(line(*P(0, r4.center().x(), r4.center().y()), *P(0, 5000, 5000), 5))  # 拖出页面：留在页面内
r5 = c._region[1]
assert r5.right() <= c.doc.sizes[0][0] + 0.01 and r5.bottom() <= c.doc.sizes[0][1] + 0.01, r5
assert c.ask_target() == (0, r5)
w.act_pen.trigger()
assert c._region is None

# ---- 7d. 图片和排版片段：插入、点选、缩放、保存进 PDF、重开、反复保存不变大、删除后清掉
from PySide6.QtGui import QColor, QImage  # noqa: E402
from ruipdf.stroke import ImageItem, RichItem  # noqa: E402

c.go_to_page(1)  # 前面插入的空白页
app.processEvents()
pic = QImage(200, 100, QImage.Format_RGB32)
pic.fill(QColor("#E53935"))
pic_path = os.path.join(tmp, "red.png")
pic.save(pic_path)
page1 = c.current_page()
before = len(c.strokes.get(page1, []))
assert c.insert_image(pic_path)
img_item = c.strokes[page1][-1]
assert isinstance(img_item, ImageItem) and c._sel == [img_item] and w.tool == "lasso"
assert abs(img_item.w - 150) < 0.01 and abs(img_item.h - 75) < 0.01, (img_item.w, img_item.h)  # 96 dpi 的自然大小
# 一份只有一页的小 PDF 当作"排版好的片段"（真正的片段由 richpaste 用浏览器引擎排出来，这里只测对象和保存）
sn = pymupdf.open()
sp = sn.new_page(width=120, height=40)
sp.draw_rect((2, 2, 118, 38), color=(0, 0, 1), fill=(0, 0, 1))
snippet = sn.tobytes()
sn.close()
rich_item = RichItem(snippet, 0, 0, 120, 40, src="$x^2$")
c.place_box(rich_item)
assert c._sel == [rich_item] and len(c.strokes[page1]) == before + 2
rich_item.x, rich_item.y = img_item.x, img_item.y + img_item.h + 20  # 挪到图片下面，两个不重叠
w.act_pen.trigger()
w.act_lasso.trigger()
cx, cy = img_item.rect().center().x(), img_item.rect().center().y()
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*(int(v) for v in P(page1, cx, cy))))  # 点一下就选中
assert c._sel == [img_item], c._sel
hr = c._handle_rect().center()
drag(line(int(hr.x()), int(hr.y()), int(hr.x()) + 30, int(hr.y()) + 15, 4))  # 拉右下角放大
assert img_item.w > 150 and abs(img_item.w / img_item.h - 2) < 0.01
c.undo()
assert abs(img_item.w - 150) < 0.01
# 四个角都能拖：拖哪个角，对角不动，整体等比缩放
for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
    QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*(int(v) for v in P(page1, cx, cy))))
    assert c._sel == [img_item]
    r0 = img_item.rect()
    hc = dict(c._handle_rects())[(sx, sy)].center()
    drag(line(int(hc.x()), int(hc.y()), int(hc.x()) + 24 * sx, int(hc.y()) + 12 * sy, 4))  # 往外拖 = 放大
    r1 = img_item.rect()
    assert r1.width() > r0.width() + 10 and abs(r1.width() / r1.height() - 2) < 0.01, (sx, sy, r0, r1)
    fixed0 = (r0.left() if sx > 0 else r0.right(), r0.top() if sy > 0 else r0.bottom())
    fixed1 = (r1.left() if sx > 0 else r1.right(), r1.top() if sy > 0 else r1.bottom())
    assert abs(fixed0[0] - fixed1[0]) < 0.01 and abs(fixed0[1] - fixed1[1]) < 0.01, (sx, sy, fixed0, fixed1)
    c.undo()
    assert abs(img_item.w - 150) < 0.01 and abs(img_item.x - r0.x()) < 0.01
QTest.mouseClick(c, Qt.LeftButton, Qt.NoModifier, QPoint(*(int(v) for v in P(page1, cx, cy))))  # 撤销会取消选中，再点一下
assert c._sel == [img_item]
QTest.keyClick(c, Qt.Key_C, Qt.ControlModifier)
QTest.keyClick(c, Qt.Key_V, Qt.ControlModifier)  # 我们自己复制的：粘贴成同样的对象
assert c.strokes[page1][-1].kind == "img" and c.strokes[page1][-1] is not img_item
c.undo()
app.clipboard().setImage(pic)  # 别处来的图片（截图等）：粘贴成图片对象
QTest.keyClick(c, Qt.Key_V, Qt.ControlModifier)
assert c.strokes[page1][-1].kind == "img" and len(c.strokes[page1]) == before + 3
c.undo()
w.act_pen.trigger()


def box_pixels(path, page_no, item):
    """用 PyMuPDF（相当于别的 PDF 软件）渲染保存后的文件，取对象中心那个像素。"""
    dd = pymupdf.open(path)
    px = dd[page_no].get_pixmap()
    ctr = item.rect().center()
    rgb = px.pixel(int(ctr.x()), int(ctr.y()))
    xobjs = sum(1 for x in range(1, dd.xref_length()) if "/Subtype/Image" in dd.xref_object(x, compressed=True)
                or "/Subtype/Form" in dd.xref_object(x, compressed=True))
    dd.close()
    return rgb, xobjs


assert w.save()
size1 = os.path.getsize(src)
rgb, n1 = box_pixels(src, page1, img_item)
assert rgb[0] > 200 and rgb[1] < 90, rgb  # 图片画进了页面，别的软件也看得到
rgb, _ = box_pixels(src, page1, rich_item)
assert rgb[2] > 200 and rgb[0] < 60, rgb  # 片段也是
c = w.canvas
kinds1 = [s.kind for s in c.strokes[page1]]
assert kinds1[-2:] == ["img", "rich"] and c.strokes[page1][-1].src == "$x^2$"
shot = c.grab_image(page1)  # 重开后画布自己画出来的也对（内存里的笔迹内容流是清空的）
ctr = c.strokes[page1][-2].rect().center()
k = shot.width() / c.doc.sizes[page1][0]
col = QColor(shot.pixel(int(ctr.x() * k), int(ctr.y() * k)))
assert col.red() > 200 and col.green() < 90, col.name()
again = c.doc.render(page1, 1.0)
assert QColor(again.pixel(int(ctr.x()), int(ctr.y()))).green() > 200, "内存里的页面不应该带着图片（由画布画）"
c.changed.emit()
assert w.save()
_, n2 = box_pixels(src, page1, c.strokes[page1][-2])
assert n2 == n1 and os.path.getsize(src) < size1 * 1.05, (n1, n2, size1, os.path.getsize(src))  # 再存一次不变大
del c.strokes[page1][-2:]  # 删掉图片和片段
c._invalidate(page1)
c.changed.emit()
assert w.save()
c = w.canvas
dd = pymupdf.open(src)
assert "RuiPDFx" not in dd.xref_object(dd.page_xref(page1), compressed=True) + str(dd.xref_get_key(dd.page_xref(page1), "Resources"))
assert dd[page1].get_pixmap().pixel(int(ctr.x()), int(ctr.y()))[1] > 200
dd.close()
assert os.path.getsize(src) < size1, "删掉图片后文件应该变小"

# ---- 7e. 粘贴 AI 回答：认出各种写法的公式（只测文本处理；真正排版要浏览器引擎，见 tests/rich.py）
from ruipdf import richpaste  # noqa: E402


def maths(body):
    return [(html_mod.unescape(t), d == "1") for d, t in re_mod.findall(r'data-d="(\d)" data-tex="([^"]*)"', body)]


import html as html_mod  # noqa: E402
import re as re_mod  # noqa: E402

body = richpaste.to_body("行内 $a_1+b$ 和 \\(c^2\\)，价格 $5 和 $10。\n\n$$\n\\frac{1}{2}\n$$\n\n\\[ x<y \\]\n\n"
                         "\\begin{align}\nE &= mc^2\n\\end{align}\n\n转义 \\$3，代码 `$no$`。\n\n```\n$$not$$\n```\n\n"
                         "```math\n\\int f\n```\n")
assert maths(body) == [("a_1+b", False), ("c^2", False), ("\\frac{1}{2}", True), ("x<y", True),
                       ("\\begin{align}\nE &= mc^2\n\\end{align}", True), ("\\int f", True)], maths(body)
assert "$5 和 $10" in body and "$3" in body and "<code>$no$</code>" in body and "$$not$$" in body
assert "<em>" not in body, "公式里的下划线不能被当成 Markdown 的斜体"
table = richpaste.to_body("| a | b |\n|---|---|\n| $x$ | **粗** |\n\n1. 一\n2. 二")
assert "<table>" in table and "<strong>粗</strong>" in table and "<ol>" in table and maths(table) == [("x", False)]
web = ('<div><p>选中复制的 <span class="katex"><span class="katex-mathml"><math><semantics><mrow><mi>x</mi></mrow>'
       '<annotation encoding="application/x-tex">x^2 &lt; 1</annotation></semantics></math></span>'
       '<span class="katex-html" aria-hidden="true">x2&lt;1</span></span> 完。</p>'
       '<span class="katex-display"><span class="katex"><math display="block"><semantics><mrow></mrow>'
       '<annotation encoding="application/x-tex">\\sum_i i</annotation></semantics></math></span></span>'
       '<button>Copy code</button><script>alert(1)</script><p onclick="x()">尾</p></div>')
wb = richpaste.to_body("x2<1 乱的纯文本", web)
assert maths(wb) == [("x^2 < 1", False), ("\\sum_i i", True)], maths(wb)
assert "alert" not in wb and "Copy code" not in wb and "onclick" not in wb and "<p>尾</p>" in wb and "x2&lt;1" not in wb
assert richpaste.to_body("纯文本 $y$", "<p>没有公式标记的网页</p>") == richpaste.markdown_to_body("纯文本 $y$")
# 网页 HTML 先还原成 Markdown 原文（存进对象，改内容 / 改宽度时拿它重新排版）
md = richpaste.to_source("乱的", '<h2>题</h2><p>价 $5 <b>粗</b></p><ul><li>一</li><li>二<ul><li>内</li></ul></li></ul>' + web
                         + '<table><tr><th>a</th><th>b</th></tr><tr><td>1</td><td>2</td></tr></table>')
assert md.startswith("## 题") and "\\$5 **粗**" in md and "- 一\n- 二\n    - 内" in md, md
assert "$x^2 < 1$" in md and "$$\n\\sum_i i\n$$" in md and "| a | b |\n|---|---|\n| 1 | 2 |" in md, md
# KaTeX 在 \text{} 里不认的字符（单位里常见的间隔号等）换成它认的写法；数学模式里的不动
fix = richpaste._fix_text_mode
assert fix(r"\tfrac{\text{kg·K}}{\text{s}}·x") == r"\tfrac{\text{kg$\cdot$K}}{\text{s}}·x"
assert fix(r"\text{a{b·c}} \textbf{x≠y} \mathrm{a·b} \\text{·}") == \
    r"\text{a{b$\cdot$c}} \textbf{x$\neq$y} \mathrm{a·b} \\text{·}"
body = richpaste.markdown_to_body("前\n$$a$$\n后\n\n* 项一\n* 项二\n顶格的下一段\n\n```\n* 代码里的\n不动\n```")
assert "<br" not in body.split("后")[0], "独立成行的公式前后不应该再有换行"
assert "</ul>\n<p>顶格的下一段</p>" in body and "* 代码里的\n不动" in body, body
# 原文里可以写格式标记（格式工具条插的就是这些）；但脚本、事件属性、外部资源一律进不去
safe = richpaste.markdown_to_body('**粗** <u>线</u> <span style="color:#d32f2f;font-size:14pt;position:fixed">红</span> '
                                  '<span style="background:url(http://x/y)" onclick="evil()">x</span>'
                                  '<script>alert(1)</script><img src="http://x/a.png"><iframe src="file:///c:/"></iframe>'
                                  '<a href="javascript:alert(2)">链</a> $a<b$')
assert "<strong>粗</strong>" in safe and "<u>线</u>" in safe, safe
assert '<span style="color:#d32f2f;font-size:14pt">红</span>' in safe, safe
for bad in ("script", "alert", "onclick", "evil", "url(", "http://", "iframe", "file:", "javascript", "<img", "<a",
            "position"):
    assert bad not in safe, (bad, safe)
assert "链" in safe and maths(safe) == [("a<b", False)]
# 片段的状态包含数据和原文：重新排版后能撤销回去
r2 = RichItem(snippet, 1, 2, 120, 40, "旧", "SimSun", 12)
st = r2.get_state()
r2.set_state((5, 6, 60, 20, snippet + b"\n%x", "新"))
assert r2.src == "新" and r2.hash != rich_item.hash and r2.w == 60
r2.set_state(st)
assert r2.src == "旧" and r2.hash == rich_item.hash and r2.get_state() == st
back = cv.item_from_json(r2.to_json())
assert (back.src, back.font, back.size, back.get_state()[:4]) == ("旧", "SimSun", 12.0, (1.0, 2.0, 120.0, 40.0))

# ---- 8. 自动备份与恢复
w.act_pen.trigger()
c.go_to_page(2)
app.processEvents()
drag(line(*P(2, 100, 300), *P(2, 200, 320)))
c.insert_blank_after(2)
w._autosave()
assert os.path.exists(w._backup_path(src))
fresh = Document(src)
import json  # noqa: E402
with open(w._backup_path(src), encoding="utf-8") as f:
    backup = json.load(f)
fresh.apply_ops(backup["ops"])
assert len(fresh) == 5 and "2" in backup["strokes"]
fresh.close()

# ---- 9. 模板与新建笔记
for key, _name in TEMPLATES:
    path = os.path.join(tmp, f"note_{key}.pdf")
    create_notebook(path, key, landscape=(key == "grid"), pages=2)
    nb = Document(path)
    assert len(nb) == 2 and nb.page_template(0) == key
    nb.insert_blank(0)
    assert nb.page_template(1) == key, "笔记本里加页应该沿用同一种模板"
    nb.close()

# ---- 搜索结果列表：侧栏里列出全部结果（页码 + 那一行的文字），点一条跳过去，和查找栏共用结果
w.find_edit.setText("Ohm")
w._find_text = ""
w.find_step(1)
n_hits = len(w._find_hits)
assert n_hits >= 2 and w.sidebar.search_list.count() == n_hits, (n_hits, w.sidebar.search_list.count())
assert "Ohm" in w.sidebar.search_list.item(0).text() and "law" in w.sidebar.search_list.item(0).text()
assert w.sidebar.search_list.currentRow() == w._find_i
last = n_hits - 1
w.sidebar.hitActivated.emit(last)
assert w._find_i == last and w.sidebar.search_list.currentRow() == last
assert w.canvas.current_page() == w._find_hits[last][0], "点结果列表里的一条应该跳到那一页"
w.sidebar.searchRequested.emit("no-such-text-xyz")
assert w._find_hits == [] and w.sidebar.search_list.count() == 0 and w.sidebar.search_info.text()
w.hide_find()
assert w.sidebar.search_list.count() == 0 and not w.canvas.hits
w.canvas.go_to_page(0)

# ---- 悬浮工具条：四种位置 + 固定；画布要给它让出对应的那一边，切回固定后不留空
fc = w.canvas
for pos, side in (("top", 1), ("bottom", 3), ("left", 0), ("right", 2)):
    w._pick_toolbar_pos(pos)
    QTest.qWait(30)
    assert w.floatbar.isVisible() and w.tb_tools.isVisible() and w.tb_settings.parent() is not w
    assert fc.insets[side] > 0 and sum(fc.insets) == fc.insets[side], (pos, fc.insets)
    assert w.floatbar.fly_btn.isVisible() == (pos in ("left", "right"))
    if pos in ("left", "right"):
        assert not w.floatbar.flyout.isVisible()
        w.act_flyout.setChecked(True)
        QTest.qWait(30)
        assert w.floatbar.flyout.isVisible() and w.tb_settings.isVisible()
        w.act_flyout.setChecked(False)
fc.go_to_page(0)
w._pick_toolbar_pos("top")
QTest.qWait(30)
assert fc.page_rect(0).top() >= w.floatbar.geometry().bottom() - fc.mapTo(w.stack, QPoint(0, 0)).y(), \
    "停在开头时第一页不应该被上方的工具条挡住"
# 拖动工具条：按住开头的小点拖到画布左边 → 停到左侧，菜单里的勾和设置跟着变
fb = w.floatbar


def drag_bar(a, target):
    """在悬浮条上从 a（条内坐标）按下，拖到 target（stack 坐标）松手。"""
    QTest.mousePress(fb, Qt.LeftButton, Qt.NoModifier, a)
    start = fb.mapTo(w.stack, a)
    for k in (0.4, 0.8, 1.0):
        QTest.mouseMove(fb, fb.mapFrom(w.stack, start + (target - start) * k))
    QTest.mouseRelease(fb, Qt.LeftButton, Qt.NoModifier, fb.mapFrom(w.stack, target))
    QTest.qWait(30)


drag_bar(fb.grip.geometry().center(), QPoint(fb._ref.left() + 20, fb._ref.center().y()))
assert w.toolbar_pos == "left" and app_settings().value("toolbar_pos") == "left"
assert w._pos_actions["left"].isChecked() and fc.insets[0] > 0
drag_bar(fb.grip.geometry().center(), QPoint(fb._ref.center().x(), fb._ref.top() + 20))
assert w.toolbar_pos == "top"
QTest.mouseClick(fb, Qt.LeftButton, Qt.NoModifier, fb.grip.geometry().center())
assert w.toolbar_pos == "top", "只是点一下不应该换位置"
# 拖两头改长度；双击两头恢复自动
auto_w = fb.width()
end = QPoint(fb.width() - 3, fb.height() // 2)
drag_bar(end, fb.mapTo(w.stack, end) - QPoint(120, 0))
assert fb.length["h"] > 0 and fb.width() < auto_w, (fb.length, fb.width(), auto_w)
assert int(app_settings().value("toolbar_len_h")) == fb.length["h"]
QTest.mouseDClick(fb, Qt.LeftButton, Qt.NoModifier, QPoint(3, fb.height() // 2))
QTest.qWait(30)
assert fb.length["h"] == 0 and fb.width() == auto_w
# 竖条：拖朝画布的那条边改宽度，双击恢复
w._pick_toolbar_pos("left")
QTest.qWait(30)
auto_t = fb.width()
side = QPoint(fb.width() - 2, fb.height() // 2)
drag_bar(side, fb.mapTo(w.stack, side) + QPoint(50, 0))
assert fb.length["t"] > auto_t and fb.width() == fb.length["t"], (fb.length, fb.width(), auto_t)
assert int(app_settings().value("toolbar_len_t")) == fb.length["t"] and w.toolbar_pos == "left"
QTest.mouseDClick(fb, Qt.LeftButton, Qt.NoModifier, QPoint(fb.width() - 2, fb.height() // 2))
QTest.qWait(30)
assert fb.length["t"] == 0 and fb.width() == auto_t
w._pick_toolbar_pos("top")
QTest.qWait(30)
# 窗口窄时第一行的后半段收起来，出现"更多"按钮；点它展开 / 收起；窗口变宽后恢复原样
old_size = w.size()
w.resize(2400, old_size.height())
QTest.qWait(50)
assert not w._view_wrapped and not w.tb_more.isVisible() and w.tb_view.isVisible()
w.resize(700, old_size.height())
QTest.qWait(50)
assert w._view_wrapped and w.tb_more.isVisible() and not w.tb_view.isVisible()
more_btn = w.tb_more.widgetForAction(w.act_more)
QTest.mouseClick(more_btn, Qt.LeftButton)
assert w.tb_view.isVisible()
QTest.mouseClick(more_btn, Qt.LeftButton)
assert not w.tb_view.isVisible()
w.resize(2400, old_size.height())
QTest.qWait(50)
assert not w.tb_more.isVisible() and w.tb_view.isVisible()
w.resize(old_size)
QTest.qWait(50)
# 不透明度：只改底色的样式
fb.set_opacity(40)
assert fb.opacity == 40 and "rgba(255,255,255,%d)" % round(244 * 0.4) in fb.styleSheet()
fb.set_opacity(100)
# 液态玻璃开关：运行中切换，不用重启（离屏环境里机器不支持时开关本来就是灰的，只验证不出错）
# 界面风格：六种，运行中切换，不用重启
from ruipdf import theme as th  # noqa: E402
start_theme = w.theme_key
for key in th.THEMES:
    w._pick_theme(key)
    want = key if (key != "glass" or th.glass_capable) else "light"  # 机器不支持液态玻璃时退回浅色
    assert w.theme_key == th.current == want and app_settings().value("theme") == want
    assert w.glass_on == th.glass_enabled == (want == "glass")
    assert w._theme_actions[want].isChecked() and th.canvas_bg() == th.THEMES[want][2]
    assert ("rgba(%d,%d,%d," % th.THEMES[want][3]).replace(" ", "") in w.styleSheet().replace(" ", ""), "强调色应该跟着风格换"
    assert th.is_dark() == (want == "dark")
w._pick_theme("dark")
assert "#2C2C2E" not in w.styleSheet(), "深色风格下不应该还有深色的文字颜色"
img_dark = w.act_pen.icon().pixmap(28, 28).toImage()
w._pick_theme("light")
assert img_dark != w.act_pen.icon().pixmap(28, 28).toImage(), "深色风格下工具图标的线条应该反成浅色"
w._pick_theme(start_theme)
# 全屏时按 Esc 退出
w._toggle_fullscreen()
QTest.qWait(50)
assert w.isFullScreen()
QTest.keyClick(fc, Qt.Key_Escape)
QTest.qWait(50)
assert not w.isFullScreen(), "全屏时按 Esc 应该退出全屏"

w._pick_toolbar_pos("docked")
QTest.qWait(30)
assert not w.floatbar.isVisible() and fc.insets == (0, 0, 0, 0)
assert w.tb_tools.isVisible() and w.toolBarArea(w.tb_tools) == Qt.TopToolBarArea
assert app_settings().value("toolbar_pos") == "docked"

for t in w._all_tabs():
    t.dirty = False
try:
    os.remove(w._backup_path(src))  # 清掉测试留下的自动备份
except OSError:
    pass
print("ALL OK")
