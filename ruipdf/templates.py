"""笔记模板：横线、方格、点阵、康奈尔等。模板直接画进 PDF 页面，所以任何软件打开都能看到。"""
import pymupdf

from .i18n import LANG, T

A4 = (595.0, 842.0)
MM = 72 / 25.4  # 1 毫米 = 多少 pt

# 代号, 名称
TEMPLATES = [
    ("blank", T("空白")),
    ("lined", T("横线")),
    ("grid", T("方格")),
    ("dots", T("点阵")),
    ("cornell", T("康奈尔笔记")),
    ("graph", T("坐标纸")),
    ("mistake", T("错题本")),
    ("todo", T("待办清单")),
]
NAMES = dict(TEMPLATES)

LINE = (0.78, 0.82, 0.88)      # 普通格线
STRONG = (0.60, 0.67, 0.76)    # 分区线
MARGIN = (0.93, 0.62, 0.62)    # 左侧页边线
LABEL = (0.45, 0.50, 0.58)     # 分区标题文字


def _label(page, x, y, text, size=10):
    """分区标题。中文用 PyMuPDF 自带的中文字体，英文用 Helvetica。"""
    font = "china-s" if any(ord(ch) > 0x2E7F for ch in text) else "helv"
    page.insert_text((x, y), text, fontsize=size, fontname=font, color=LABEL)


def _hlines(shape, x0, x1, y0, y1, step):
    y = y0
    while y <= y1 + 0.01:
        shape.draw_line((x0, y), (x1, y))
        y += step


def _vlines(shape, y0, y1, x0, x1, step):
    x = x0
    while x <= x1 + 0.01:
        shape.draw_line((x, y0), (x, y1))
        x += step


def draw_template(page, key: str):
    """把模板画到一张空白页上。page 是 pymupdf 的页面对象。"""
    w, h = page.rect.width, page.rect.height
    if key not in NAMES or key == "blank":
        return
    s = page.new_shape()
    if key == "lined":
        _hlines(s, 36, w - 36, 72, h - 40, 8 * MM)
        s.finish(color=LINE, width=0.5)
        s.draw_line((62, 40), (62, h - 40))
        s.finish(color=MARGIN, width=0.6)
    elif key == "grid":
        step = 5 * MM
        ox, oy = (w % step) / 2, (h % step) / 2  # 让格子在页面上居中
        _hlines(s, 0, w, oy, h, step)
        _vlines(s, 0, h, ox, w, step)
        s.finish(color=LINE, width=0.4)
    elif key == "dots":
        step = 5 * MM
        y = (h % step) / 2 + step
        while y < h - step / 2:
            x = (w % step) / 2 + step
            while x < w - step / 2:
                s.draw_circle((x, y), 0.55)
                x += step
            y += step
        s.finish(color=STRONG, fill=STRONG, width=0)
    elif key == "cornell":
        top, bottom, cue = 78, h - 130, round(w * 0.30)
        _hlines(s, cue + 10, w - 30, top + 8 * MM, bottom - 4, 8 * MM)
        _hlines(s, 36, w - 30, bottom + 8 * MM + 14, h - 36, 8 * MM)
        s.finish(color=LINE, width=0.5)
        s.draw_line((30, top), (w - 30, top))
        s.draw_line((30, bottom), (w - 30, bottom))
        s.draw_line((cue, top), (cue, bottom))
        s.finish(color=STRONG, width=0.9)
        s.draw_line((36, 58), (w * 0.62, 58))
        s.draw_line((w * 0.68, 58), (w - 36, 58))
        s.finish(color=LINE, width=0.5)
        s.commit()
        _label(page, 36, 44, T("主题"))
        _label(page, w * 0.68, 44, T("日期"))
        _label(page, 36, top + 16, T("线索 / 问题"))
        _label(page, cue + 10, top + 16, T("笔记"))
        _label(page, 36, bottom + 16, T("总结"))
        return
    elif key == "graph":
        ox, oy = (w % (10 * MM)) / 2, (h % (10 * MM)) / 2
        for step, width, color in ((MM, 0.15, (0.86, 0.90, 0.95)), (5 * MM, 0.3, (0.74, 0.81, 0.90)),
                                   (10 * MM, 0.55, (0.60, 0.70, 0.83))):
            _hlines(s, ox, w - ox, oy, h - oy, step)
            _vlines(s, oy, h - oy, ox, w - ox, step)
            s.finish(color=color, width=width)
    elif key == "mistake":
        # 四个分区：题目 / 我的解答与错因 / 正确解法 / 总结
        x0, x1 = 30, w - 30
        cuts = [70, 70 + (h - 110) * 0.26, 70 + (h - 110) * 0.52, 70 + (h - 110) * 0.86, h - 40]
        for y in cuts:
            s.draw_line((x0, y), (x1, y))
        s.draw_line((x0, cuts[0]), (x0, cuts[-1]))
        s.draw_line((x1, cuts[0]), (x1, cuts[-1]))
        s.finish(color=STRONG, width=0.9)
        s.draw_line((36, 54), (w * 0.5, 54))
        s.draw_line((w * 0.56, 54), (w * 0.76, 54))
        s.draw_line((w * 0.82, 54), (x1 - 6, 54))
        s.finish(color=LINE, width=0.5)
        s.commit()
        _label(page, 36, 40, T("科目 / 章节"))
        _label(page, w * 0.56, 40, T("来源"))
        _label(page, w * 0.82, 40, T("日期"))
        for y, text in zip(cuts, (T("题目"), T("我的解答 / 错因"), T("正确解法"), T("总结 / 易错点"))):
            _label(page, x0 + 8, y + 16, text)
        return
    elif key == "todo":
        y, step = 96, 10 * MM
        while y < h - 40:
            s.draw_rect(pymupdf.Rect(44, y - 12, 56, y))
            s.draw_line((68, y), (w - 40, y))
            y += step
        s.finish(color=STRONG, width=0.7)
        s.draw_line((36, 62), (w - 36, 62))
        s.finish(color=STRONG, width=0.9)
        s.commit()
        _label(page, 36, 50, T("待办清单"), 14)
        _label(page, w - 150, 50, T("日期"))
        return
    s.commit()


def create_notebook(path: str, key: str, landscape: bool = False, pages: int = 1):
    """新建一本笔记（一个 PDF 文件）。"""
    w, h = (A4[1], A4[0]) if landscape else A4
    doc = pymupdf.open()
    for _ in range(max(1, pages)):
        page = doc.new_page(width=w, height=h)
        draw_template(page, key)
        doc.xref_set_key(page.xref, "RuiPDF_Blank", "true")
        doc.xref_set_key(page.xref, "RuiPDF_Tpl", f"/{key}")
    doc.set_metadata({"creator": "RuiPDF", "title": NAMES.get(key, "")})
    doc.save(path, garbage=3, deflate=True)
    doc.close()


def preview(key: str, landscape: bool = False, width_px: int = 150) -> bytes:
    """模板预览图（PNG 字节）。"""
    w, h = (A4[1], A4[0]) if landscape else A4
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    draw_template(page, key)
    data = page.get_pixmap(matrix=pymupdf.Matrix(width_px / w, width_px / w), alpha=False).tobytes("png")
    doc.close()
    return data


__all__ = ["TEMPLATES", "NAMES", "draw_template", "create_notebook", "preview", "LANG"]
