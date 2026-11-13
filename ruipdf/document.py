"""PDF 文档：页面尺寸、渲染，以及笔迹的保存与读取（PyMuPDF）。

保存方案：
  * 笔迹按压感粗细画进页面内容（单独一个内容流），任何 PDF 软件都能看到；
  * 同时把原始笔画数据（JSON）存进同一个 PDF，RuiPDF 重新打开后可以继续编辑。
  每页在页面字典里用两个自定义键记录：/RuiPDF_Ink -> 笔迹内容流，/RuiPDF_Data -> 笔画数据。
内存中的文档始终把笔迹内容流清空（笔迹由画布自己画），只有保存的瞬间才写入。
图片和排版好的片段同样画进笔迹内容流：内容本身做成 XObject 放在页面资源里（名字是 RuiPDFx + 内容哈希），
内容流里用 Do 引用；原始数据另存一份在笔画数据里，所以即使别的软件重排了对象也能恢复。
"""
import json
import os
import re

import pymupdf
from PySide6.QtGui import QColor, QImage, QPainterPath

from .stroke import BOX_KINDS, item_from_json, iter_pieces
from .templates import draw_template

BOX_PREFIX = "RuiPDFx"  # 图片 / 片段的 XObject 在页面资源里的名字前缀，后面接内容哈希
INK_KEY = "RuiPDF_Ink"
DATA_KEY = "RuiPDF_Data"
HL_GSTATE = "RuiPDFhl"  # 荧光笔用的图形状态：正片叠底
BLANK_KEY = "RuiPDF_Blank"  # 标记由 RuiPDF 插入的空白页
MARK_KEY = "RuiPDF_Mark"    # 书签标题
TPL_KEY = "RuiPDF_Tpl"      # 这一页用的笔记模板
MARGIN_KEY = "RuiPDF_Margin"  # 这一页加了多少留白：[右侧 底部]（pt，按显示出来的方向）。有它才能撤销 / 调整留白


class Document:
    def __init__(self, path: str):
        self.path = path
        self.doc = pymupdf.open(path)
        if self.doc.needs_pass:
            raise ValueError("暂不支持带密码的 PDF")
        # 每页尺寸，单位 pt（已考虑页面旋转）
        self.sizes = [(p.rect.width, p.rect.height) for p in self.doc]
        # 上次保存之后做过的页面结构改动（空白页、留白、书签），自动备份靠它在恢复时重放
        self.ops = []

    def __len__(self):
        return len(self.sizes)

    def render(self, index: int, scale: float) -> QImage:
        """把一页渲染成 QImage，scale = 像素 / pt。"""
        pix = self.doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        return img.convertToFormat(QImage.Format_RGB32)  # 同时完成深拷贝

    def close(self):
        self.doc.close()

    # ------------------------------------------------------------------ 笔迹读写
    def _ref(self, page_xref: int, key: str) -> int:
        kind, val = self.doc.xref_get_key(page_xref, key)
        return int(val.split()[0]) if kind == "xref" else 0

    def _new_stream(self, data: bytes) -> int:
        xref = self.doc.get_new_xref()
        self.doc.update_object(xref, "<<>>")
        self.doc.update_stream(xref, data)
        return xref

    def _inherited(self, pxref: int, key: str):
        """沿 Parent 链查找可继承的页面属性，返回 (类型, 值)。"""
        x = pxref
        for _ in range(50):
            kind, val = self.doc.xref_get_key(x, key)
            if kind != "null":
                return kind, val
            kind, val = self.doc.xref_get_key(x, "Parent")
            if kind != "xref":
                break
            x = int(val.split()[0])
        return "null", "null"

    # ------------------------------------------------------------------ 页面结构
    def page_template(self, i: int):
        """第 i 页的模板代号；不是模板页返回 None。"""
        kind, val = self.doc.xref_get_key(self.doc.page_xref(i), TPL_KEY)
        return val.lstrip("/") if kind == "name" else None

    def insert_blank(self, after: int, template: str = None, record: bool = True):
        """在第 after 页后面插入一张同样大小的新页。

        template 为 None 时沿用第 after 页的模板（笔记本里加页会自动是同一种纸），
        普通 PDF 页后面则是纯空白页。
        """
        w, h = self.sizes[after]
        tpl = template or self.page_template(after)
        pno = after + 1 if after + 1 < len(self.doc) else -1
        page = self.doc.new_page(pno=pno, width=w, height=h)
        if tpl:
            draw_template(page, tpl)
            self.doc.xref_set_key(page.xref, TPL_KEY, f"/{tpl}")
        self.doc.xref_set_key(page.xref, BLANK_KEY, "true")
        self.sizes.insert(after + 1, (w, h))
        if record:
            self.ops.append(["tpl", after, template] if template else ["blank", after])

    def is_blank(self, i: int) -> bool:
        return self.doc.xref_get_key(self.doc.page_xref(i), BLANK_KEY)[0] != "null"

    def delete_page(self, i: int, record: bool = True):
        self.doc.delete_page(i)
        del self.sizes[i]
        if record:
            self.ops.append(["delete", i])

    def page_margin(self, i: int):
        """第 i 页现在的留白 (右侧, 底部)，单位 pt。只知道本程序记下来的（页面字典里的 /RuiPDF_Margin）；
        这个键是后来加的，更早的版本加的留白没有记录，这里当作 0（也就没法撤销）。"""
        kind, val = self.doc.xref_get_key(self.doc.page_xref(i), MARGIN_KEY)
        if kind == "array":
            try:
                r, b = (float(v) for v in val.strip("[]").split()[:2])
                return max(0.0, r), max(0.0, b)
            except ValueError:
                pass
        return 0.0, 0.0

    def set_margin(self, i: int, side: str, total: float, record: bool = True):
        """把第 i 页右侧（side="right"）或底部（"bottom"）的留白设成一共 total pt（0 = 去掉）。
        左上角不动，所以已有笔迹的坐标不变；缩小时页面只是被裁小，落在裁掉部分的笔迹由画布那边负责删掉。"""
        page = self.doc[i]
        pxref = page.xref
        w, h = self.sizes[i]
        mr, mbottom = self.page_margin(i)
        total = max(0.0, float(total))
        if side == "right":
            nw, nh, mr = w - mr + total, h, total
        else:
            nw, nh, mbottom = w, h - mbottom + total, total
        m = page.derotation_matrix * ~page.transformation_matrix  # 画布坐标 -> PDF 坐标
        corners = [pymupdf.Point(x, y) * m for x, y in ((0, 0), (nw, 0), (0, nh), (nw, nh))]
        box = [min(p.x for p in corners), min(p.y for p in corners),
               max(p.x for p in corners), max(p.y for p in corners)]
        kind, val = self._inherited(pxref, "MediaBox")
        try:
            mb = [float(v) for v in val.strip("[]").split()]
            mb = [min(mb[0], mb[2]), min(mb[1], mb[3]), max(mb[0], mb[2]), max(mb[1], mb[3])]
        except ValueError:
            mb = box
        mb = [min(mb[0], box[0]), min(mb[1], box[1]), max(mb[2], box[2]), max(mb[3], box[3])]  # 只会变大，缩小留白时不动它
        fmt = lambda b: "[" + " ".join(f"{v:.3f}" for v in b) + "]"
        self.doc.xref_set_key(pxref, "MediaBox", fmt(mb))
        self.doc.xref_set_key(pxref, "CropBox", fmt(box))
        if mr > 0.01 or mbottom > 0.01:
            self.doc.xref_set_key(pxref, MARGIN_KEY, f"[{mr:.3f} {mbottom:.3f}]")
        else:
            self.doc.xref_set_key(pxref, MARGIN_KEY, "null")
        del page
        r = self.doc[i].rect
        self.sizes[i] = (r.width, r.height)
        if record:
            self.ops.append(["setmargin", i, side, total])

    def add_margin(self, i: int, side: str, amount: float, record: bool = True):
        """在现有留白的基础上再加 amount pt。"""
        mr, mbottom = self.page_margin(i)
        self.set_margin(i, side, (mr if side == "right" else mbottom) + amount, record=False)
        if record:
            self.ops.append(["margin", i, side, amount])

    def bookmarks(self):
        """[(页号, 标题)]"""
        out = []
        for i in range(len(self.doc)):
            kind, val = self.doc.xref_get_key(self.doc.page_xref(i), MARK_KEY)
            if kind == "string":
                out.append((i, val))
        return out

    def set_bookmark(self, i: int, title, record: bool = True):
        """title 为 None 时删除书签。"""
        val = pymupdf.get_pdf_str(title) if title else "null"
        self.doc.xref_set_key(self.doc.page_xref(i), MARK_KEY, val)
        if record:
            self.ops.append(["mark", i, title])

    def search(self, text: str):
        """全文搜索（PDF 原有的文字）。返回 [(页号, (x0, y0, x1, y1))]，坐标与画布一致。"""
        out = []
        for i in range(len(self.doc)):
            page = self.doc[i]
            for r in page.search_for(text):
                r = (r * page.rotation_matrix).normalize()  # 搜索结果是未旋转坐标，转成显示坐标
                out.append((i, (r.x0, r.y0, r.x1, r.y1)))
        return out

    def search_with_context(self, text: str, limit: int = 500):
        """和 search 一样，另外给每一处带上它所在那一行的文字（结果列表里显示用）。
        返回 [(页号, (x0, y0, x1, y1), 那一行的文字)]。只给前 limit 处找上下文，其余的（以及找不到所在行的）
        用搜索词本身。每页的文字只提取一次再按位置去对——早先每一处都单独向 PyMuPDF 要一次那一行的文字，
        几百处结果要十几秒。"""
        out = []
        for i in range(len(self.doc)):
            page = self.doc[i]
            found = page.search_for(text)
            lines = None
            for r in found:
                line = text
                if len(out) < limit:
                    if lines is None:  # 这一页有结果才提取：[(行的框, 行的文字)]
                        lines = []
                        try:
                            for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
                                for ln in block.get("lines", ()):
                                    lines.append((ln["bbox"], "".join(sp["text"] for sp in ln["spans"])))
                        except Exception:
                            pass
                    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
                    for (x0, y0, x1, y1), content in lines:
                        if x0 <= cx <= x1 and y0 <= cy <= y1:
                            content = " ".join(content.split())
                            if text.lower() in content.lower():
                                k = max(0, content.lower().index(text.lower()) - 40)  # 行太长时从搜索词前面一点开始
                                line = ("…" if k else "") + content[k:k + 90]
                            break
                r = (r * page.rotation_matrix).normalize()
                out.append((i, (r.x0, r.y0, r.x1, r.y1), line))
        return out

    def export_pages(self, strokes: dict, pages, path: str):
        """把指定的页（连同笔迹）导出成一个新 PDF，当前文档不受影响。"""
        self._write_strokes(strokes)
        try:
            data = self.doc.tobytes(deflate=True)
        finally:
            self._blank_ink()
        out = pymupdf.open(stream=data, filetype="pdf")
        out.select(list(pages))
        out.save(path, garbage=3, deflate=True)
        out.close()

    def page_chars(self, i: int):
        """第 i 页 PDF 自带文字的每个字符：[(x0, y0, x1, y1, 字符, 块号, 行号)]，按阅读顺序，
        坐标与画布一致。行号在整页内连续编号。扫描件 / 图片页返回空列表。"""
        out = []
        try:
            page = self.doc[i]
            rot = page.rotation_matrix  # 文字坐标是未旋转的，转成显示坐标（与 search 相同）
            blocks = page.get_text("rawdict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]
        except Exception:
            return out
        line_no = 0
        for b_no, block in enumerate(blocks):
            for line in block.get("lines", ()):
                for span in line["spans"]:
                    for ch in span["chars"]:
                        r = (pymupdf.Rect(ch["bbox"]) * rot).normalize()
                        out.append((r.x0, r.y0, r.x1, r.y1, ch["c"], b_no, line_no))
                line_no += 1
        return out

    def page_text(self, i: int) -> str:
        try:
            return self.doc[i].get_text()
        except Exception:
            return ""

    def toc(self):
        """PDF 自带的目录：[(层级, 标题, 页号)]"""
        try:
            return [(lvl, title, max(0, page - 1)) for lvl, title, page in self.doc.get_toc(simple=True)]
        except Exception:
            return []

    def apply_ops(self, ops):
        """重放备份里记录的页面结构改动（恢复未保存的工作时用）。"""
        for op in ops:
            kind, args = op[0], op[1:]
            if kind == "blank":
                self.insert_blank(args[0])
            elif kind == "tpl":
                self.insert_blank(args[0], template=args[1])
            elif kind == "delete":
                self.delete_page(*args)
            elif kind == "margin":
                self.add_margin(*args)
            elif kind == "setmargin":
                self.set_margin(*args)
            elif kind == "mark":
                self.set_bookmark(*args)

    def _res_loc(self, pxref: int, category: str, create: bool = True):
        """页面资源里某一类（ExtGState / XObject）字典的位置：(对象号, 键路径前缀)。

        资源字典和里面的各类字典都可能是内联的，也可能是单独的对象，这里统一成"在哪个对象的哪个路径下"。
        create=False 时只查不改，页面自己没有资源字典就返回 None。
        """
        doc = self.doc
        if doc.xref_get_key(pxref, "Resources")[0] == "null":
            if not create:
                return None
            # 资源是从父节点继承来的：先接到本页上，否则新建的空资源会把继承的字体等盖掉
            kind, val = self._inherited(pxref, "Resources")
            doc.xref_set_key(pxref, "Resources", val if kind != "null" else "<<>>")
        x, path = pxref, "Resources/"
        kind, val = doc.xref_get_key(x, "Resources")
        if kind == "xref":
            x, path = int(val.split()[0]), ""
        kind, val = doc.xref_get_key(x, path + category)
        if kind == "xref":
            x, path = int(val.split()[0]), ""
        else:
            path += category + "/"
        return x, path

    def _add_hl_gstate(self, pxref: int):
        """在页面资源里登记荧光笔的图形状态。"""
        x, path = self._res_loc(pxref, "ExtGState")
        self.doc.xref_set_key(x, path + HL_GSTATE, "<</BM/Multiply>>")

    def _box_names(self, pxref: int) -> dict:
        """这一页的资源里由本程序登记的图片 / 片段对象：{内容哈希: 对象号}。"""
        loc = self._res_loc(pxref, "XObject", create=False)
        if loc is None:
            return {}
        x, path = loc
        text = self.doc.xref_get_key(x, path.rstrip("/"))[1] if path else self.doc.xref_object(x)
        return {h: int(n) for h, n in re.findall(r"/%s([0-9a-f]+)\s+(\d+)\s+0\s+R" % BOX_PREFIX, text or "")}

    def _make_box_objects(self, items, known: dict):
        """给还没有对应 XObject 的图片 / 片段各建一个，结果记进 known（{哈希: 对象号}）。

        PyMuPDF 只能"往某一页上放图 / 放另一份 PDF 的页"，顺带建出 XObject；所以借一张临时页来放，
        拿到对象号后把临时页删掉，XObject 留在文档里，由我们自己的笔迹内容流去引用。
        """
        todo = {it.hash: it for it in items if it.hash not in known}
        if not todo:
            return
        doc = self.doc
        scratch = doc.new_page(width=100, height=100)
        try:
            for h, it in todo.items():
                if it.kind == "img":
                    known[h] = scratch.insert_image(scratch.rect, stream=it.data)
                else:
                    src = pymupdf.open(stream=it.data, filetype="pdf")
                    try:
                        known[h] = scratch.show_pdf_page(scratch.rect, src, 0)
                    finally:
                        src.close()
        finally:
            del scratch
            doc.delete_page(len(doc) - 1)

    def load_strokes(self) -> dict:
        """读取上次保存的笔画数据，并把内存里的笔迹内容流清空。"""
        result = {}
        for i in range(len(self.doc)):
            pxref = self.doc.page_xref(i)
            data = self._ref(pxref, DATA_KEY)
            if not data:
                continue
            try:
                items = json.loads(self.doc.xref_stream(data))["strokes"]
                strokes = [item_from_json(d) for d in items]
            except Exception:
                continue  # 数据损坏：保留页面上已画好的笔迹，不动它
            if strokes:
                result[i] = strokes
            ink = self._ref(pxref, INK_KEY)
            if ink:
                self.doc.update_stream(ink, b"\n")
        return result

    def _blank_ink(self):
        for i in range(len(self.doc)):
            pxref = self.doc.page_xref(i)
            ink = self._ref(pxref, INK_KEY)
            if ink and self._ref(pxref, DATA_KEY):
                self.doc.update_stream(ink, b"\n")

    def _write_strokes(self, strokes: dict):
        doc = self.doc
        n_pages = len(doc)
        # 图片 / 片段：先保证每份内容在文档里有一个 XObject（已有的沿用，所以反复保存不会越存越大）
        boxes = [s for lst in strokes.values() for s in lst or [] if s.kind in BOX_KINDS]
        known = {}
        for i in range(n_pages):
            known.update(self._box_names(doc.page_xref(i)))
        old = dict(known)
        self._make_box_objects(boxes, known)
        used = {s.hash for s in boxes}
        for i in range(n_pages):
            lst = strokes.get(i) or []
            pxref = doc.page_xref(i)
            ink, data = self._ref(pxref, INK_KEY), self._ref(pxref, DATA_KEY)
            if not lst and not ink:
                continue
            # 本页资源里登记用到的对象，去掉不再用的
            here = {s.hash for s in lst if s.kind in BOX_KINDS}
            stale = set(self._box_names(pxref)) - here
            if here or stale:
                x, path = self._res_loc(pxref, "XObject")
                for h in here:
                    doc.xref_set_key(x, path + BOX_PREFIX + h, f"{known[h]} 0 R")
                for h in stale:
                    doc.xref_set_key(x, path + BOX_PREFIX + h, "null")
            page = doc[i]
            if ink and ink not in page.get_contents():
                ink = 0  # 被别的软件改写过，重新建
            if not ink:
                if not page.is_wrapped:
                    page.wrap_contents()  # 保证我们的内容流从默认坐标系开始
                ink = self._new_stream(b"\n")
                refs = " ".join(f"{x} 0 R" for x in page.get_contents() + [ink])
                doc.xref_set_key(pxref, "Contents", f"[{refs}]")
                doc.xref_set_key(pxref, INK_KEY, f"{ink} 0 R")
            if any(s.kind == "hl" for s in lst):
                self._add_hl_gstate(pxref)
            doc.update_stream(ink, _ink_ops(page, lst))
            payload = json.dumps({"v": 1, "strokes": [s.to_json() for s in lst]},
                                 separators=(",", ":")).encode()
            if data:
                doc.update_stream(data, payload)
            else:
                doc.xref_set_key(pxref, DATA_KEY, f"{self._new_stream(payload)} 0 R")
        for h, xref in old.items():  # 已经没有任何页在用的图片 / 片段：把数据清掉，文件不再带着它
            if h not in used:
                doc.update_stream(xref, b"\n")

    def save(self, strokes: dict, path: str = None):
        """保存到 path（默认覆盖原文件）。先写临时文件再替换，中途失败不会损坏原文件。"""
        target = path or self.path
        self._write_strokes(strokes)
        tmp = target + ".ruipdf-tmp"
        try:
            data = self.doc.tobytes(deflate=True)
            with open(tmp, "wb") as f:
                f.write(data)
            self.doc.close()  # Windows 上必须先关闭才能替换文件
            os.replace(tmp, target)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            if self.doc.is_closed:  # 从内存里的数据重新打开，空白页等未保存的改动不会丢
                self.doc = pymupdf.open(stream=data, filetype="pdf")
            self._blank_ink()
            raise
        self.path = target
        self.ops = []
        self.doc = pymupdf.open(target)
        self._blank_ink()


def _ink_ops(page, strokes) -> bytes:
    """把笔画转成 PDF 绘图指令。每一小段单独设线宽，从而保留压感粗细。"""
    if not strokes:
        return b"\n"
    # 画布坐标（左上角原点、已旋转）-> PDF 页面坐标
    m = page.derotation_matrix * ~page.transformation_matrix
    out = ["q", f"{m.a:.5f} {m.b:.5f} {m.c:.5f} {m.d:.5f} {m.e:.3f} {m.f:.3f} cm", "1 J 1 j"]
    for s in strokes:
        if s.kind == "mask":  # 遮挡块只是复习辅助，不画进页面
            continue
        if s.kind in BOX_KINDS:
            # 图片的坐标空间是单位正方形，片段（Form XObject）的是它原来那一页的大小；
            # 两者都是左下角为原点、y 向上，而我们这里 y 向下，所以纵向取负并把原点放到外框左下角
            uw, uh = (1.0, 1.0) if s.kind == "img" else s.natural_size()
            out.append(f"q {s.w / uw:.5f} 0 0 {-s.h / uh:.5f} {s.x:.3f} {s.y + s.h:.3f} cm "
                       f"/{BOX_PREFIX}{s.hash} Do Q")
            continue
        if s.kind == "text":  # 文字以轮廓填充，不依赖字体；一种颜色一条路径
            for color, path in s.layout()[0]:
                c = QColor(color)
                out.append(f"{c.redF():.3f} {c.greenF():.3f} {c.blueF():.3f} rg")
                out.append(_path_ops(path) + " f")
            continue
        c = QColor(s.color)
        out.append(f"{c.redF():.3f} {c.greenF():.3f} {c.blueF():.3f} RG")
        if s.kind in ("hl", "poly"):  # 整条路径一次描完，避免自身重叠处变深
            ops, first = [], True
            for _, p0, ctrl, p1 in iter_pieces(s):
                if first:
                    ops.append(f"{p0[0]:.2f} {p0[1]:.2f} m")
                    first = False
                ops.append(_seg(p0, ctrl, p1))
            gs = f"/{HL_GSTATE} gs " if s.kind == "hl" else ""
            out.append(f"q {gs}{s.width:.2f} w {' '.join(ops)} S Q")
            continue
        for w, p0, ctrl, p1 in iter_pieces(s):
            out.append(f"{w:.2f} w {p0[0]:.2f} {p0[1]:.2f} m {_seg(p0, ctrl, p1)} S")
    out.append("Q")
    return "\n".join(out).encode()


def _seg(p0, ctrl, p1) -> str:
    if ctrl is None:
        return f"{p1[0]:.2f} {p1[1]:.2f} l"
    # 二次贝塞尔 -> 三次贝塞尔
    c1 = (p0[0] + 2 / 3 * (ctrl[0] - p0[0]), p0[1] + 2 / 3 * (ctrl[1] - p0[1]))
    c2 = (p1[0] + 2 / 3 * (ctrl[0] - p1[0]), p1[1] + 2 / 3 * (ctrl[1] - p1[1]))
    return f"{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p1[0]:.2f} {p1[1]:.2f} c"


def _path_ops(path: QPainterPath) -> str:
    """QPainterPath -> PDF 路径指令。"""
    ops, i, n = [], 0, path.elementCount()
    while i < n:
        e = path.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            ops.append(f"{e.x:.2f} {e.y:.2f} m")
        elif e.type == QPainterPath.ElementType.LineToElement:
            ops.append(f"{e.x:.2f} {e.y:.2f} l")
        elif e.type == QPainterPath.ElementType.CurveToElement:
            c2, end = path.elementAt(i + 1), path.elementAt(i + 2)
            ops.append(f"{e.x:.2f} {e.y:.2f} {c2.x:.2f} {c2.y:.2f} {end.x:.2f} {end.y:.2f} c")
            i += 2
        i += 1
    return " ".join(ops)
