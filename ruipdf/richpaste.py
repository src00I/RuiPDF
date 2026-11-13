"""把 AI 的回答（Markdown + LaTeX 公式）排版成只有一页的矢量 PDF，用来贴进页面（见 stroke.RichItem）。

分两步：
  1. 纯文本处理。to_source() 得到这段内容的原文（Markdown）：剪贴板里带着网页上已经渲染好的公式
     （KaTeX 的 HTML）时从 HTML 还原，否则就是纯文本。markdown_to_body() 把原文里的公式找出来换成
     占位符，其余按 Markdown 转成 HTML，再把占位符换成待渲染的公式标记。能认的公式写法：
     $…$、$$…$$、\\(…\\)、\\[…\\]、裸写的 \\begin{align}…\\end{align}、```math 代码块。
     原文跟着对象一起保存（RichItem.src），改内容、改宽度时都是拿它重新排版。
  2. Renderer：用 Qt 自带的浏览器引擎（Chromium）加载这段 HTML，KaTeX 把公式渲染出来，
     量出内容的高度，再"打印"成正好那么大的一页 PDF。字体会被嵌进去，所以结果是矢量的。
     浏览器引擎第一次用到时才启动（要一两秒），之后复用同一个页面。

KaTeX 的文件在 ruipdf/assets/katex/（0.16.11，从 jsDelivr 下载后随程序带着，运行时不联网）。
"""
import html
import json
import os
import re
from html.parser import HTMLParser

from PySide6.QtCore import QMarginsF, QObject, QSizeF, QTimer, QUrl
from PySide6.QtGui import QPageLayout, QPageSize

KATEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "katex")
TIMEOUT_MS = 20000
_TOKEN = "RUIMATH%dX"
_TOKEN_RE = re.compile(r"RUIMATH(\d+)X")

# 独立成段的公式环境：没有被 $$ 包着直接写出来的也认
_ENVS = (r"equation\*?|align\*?|aligned|alignat\*?|gather\*?|gathered|multline\*?|split|cases|array|"
         r"[pbvBV]?matrix|smallmatrix|eqnarray\*?")

_MATH_RE = re.compile(r"""
    (?P<fence>^[ \t]*(?P<fmark>`{3,}|~{3,})(?P<finfo>[^\n`]*)\n(?P<fbody>.*?)^[ \t]*(?P=fmark)[ \t]*$)
  | (?P<code>(?P<cmark>`+)(?:(?!(?P=cmark)).|\n(?!\n))+?(?P=cmark))
  | \$\$(?P<dd>.+?)\$\$
  | \\\[(?P<br>.+?)\\\]
  | (?P<env>\\begin\{(?P<envname>%s)\}.+?\\end\{(?P=envname)\})
  | \\\((?P<pa>.+?)\\\)
  | (?P<esc>\\\$)
  | \$(?P<d>(?=[^\s$])(?:\\.|[^$\\\n])+?(?<=[^\s\\]))\$(?!\d)
""" % _ENVS, re.M | re.S | re.X)


def _extract_math(text: str):
    """把公式换成占位符。返回 (换过的文本, [(LaTeX, 是否独立成行)])。代码块和行内代码里的内容不动。"""
    found = []

    def token(tex: str, display: bool) -> str:
        found.append((tex.strip(), display))
        return _TOKEN % (len(found) - 1)

    def repl(m):
        if m.group("fence") is not None:
            if m.group("finfo").strip().lower() in ("math", "katex"):
                return token(m.group("fbody"), True)
            return m.group(0)
        if m.group("code") is not None:
            return m.group(0)
        if m.group("esc") is not None:
            return "$"
        for name, display in (("dd", True), ("br", True), ("env", True), ("pa", False), ("d", False)):
            if m.group(name) is not None:
                return token(m.group(name), display)
        return m.group(0)

    return _MATH_RE.sub(repl, text), found


# KaTeX 在文本模式（\text{…} 里面）不认这些字符，会把整条命令当错误显示成红字；数学模式下都认。
# AI 写单位时很爱用间隔号，比如 \text{kg·K}。做法：在文本模式里遇到它们就临时切回数学模式（$…$）。
_TEXT_MODE_FIX = {"·": r"\cdot", "⋅": r"\cdot", "≠": r"\neq", "∑": r"\sum", "∏": r"\prod", "∫": r"\int"}
_TEXT_CMD_RE = re.compile(r"\\(?:text(?:rm|bf|it|sf|tt|normal|up|md)?|mbox|hbox)\s*\{")


def _fix_text_mode(tex: str) -> str:
    """把 \\text{…} 里 KaTeX 不认的字符换成它认的写法。其余原样返回。"""
    if not any(ch in tex for ch in _TEXT_MODE_FIX):
        return tex
    out, stack, i, n = [], [], 0, len(tex)  # stack：每层花括号是不是文本模式
    while i < n:
        m = _TEXT_CMD_RE.match(tex, i)
        if m:
            out.append(m.group(0))
            stack.append(True)
            i = m.end()
            continue
        ch = tex[i]
        if ch == "\\" and i + 1 < n:  # 转义字符或命令名的开头：连同下一个字符原样带过
            out.append(tex[i:i + 2])
            i += 2
            continue
        if ch == "{":
            stack.append(bool(stack and stack[-1]))  # 普通花括号沿用外层的模式
        elif ch == "}" and stack:
            stack.pop()
        elif ch in _TEXT_MODE_FIX and stack and stack[-1]:
            ch = "$%s$" % _TEXT_MODE_FIX[ch]
        out.append(ch)
        i += 1
    return "".join(out)


def _math_span(tex: str, display: bool) -> str:
    return '<span class="rm" data-d="%d" data-tex="%s"></span>' % (display, html.escape(_fix_text_mode(tex), quote=True))


_BR_AROUND_DISPLAY = re.compile(r'(?:<br\s*/?>\s*)*(<span class="rm" data-d="1"[^>]*></span>)(?:\s*<br\s*/?>)*')


def _fill_tokens(body: str, found) -> str:
    body = _TOKEN_RE.sub(lambda m: _math_span(*found[int(m.group(1))]), body)
    # 独立成行的公式自己就占一行：把它前后的换行去掉，否则公式上下会各多出一个空行
    return _BR_AROUND_DISPLAY.sub(r"\1", body)


_LIST_LINE = re.compile(r"^[ \t]*(?:[*+-]|\d{1,3}[.)])[ \t]+\S")
_FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


def _end_lists(text: str) -> str:
    """列表项后面紧跟着一行顶格的普通文字时，在中间补一个空行。

    按 Markdown 的规矩，这样的一行会被并进上一个列表项；但从聊天里复制出来的内容常常就是
    "列表完了直接换行接着写"，并进去会让最后一段缩进到列表里面。代码块里的内容不动。
    """
    lines, out, fence = text.split("\n"), [], None
    for k, line in enumerate(lines):
        out.append(line)
        m = _FENCE_LINE.match(line)
        if m:
            fence = None if fence and line.strip().startswith(fence) else (fence or m.group(1)[:3])
            continue
        if fence or k + 1 >= len(lines):
            continue
        nxt = lines[k + 1]
        if _LIST_LINE.match(line) and nxt.strip() and not nxt[0].isspace() and not _LIST_LINE.match(nxt):
            out.append("")
    return "\n".join(out)


_md = None


def markdown_to_body(text: str) -> str:
    """Markdown（里面可以有各种写法的公式）-> HTML 片段。"""
    global _md
    if _md is None:
        from markdown_it import MarkdownIt
        # html=True：原文里可以写 <u>、<span style="color:…"> 这类格式标记（格式工具条插的就是它们）。
        # 这也意味着原文里可能混进任意 HTML，所以排版前一律过一遍 _sanitize。
        _md = MarkdownIt("commonmark", {"html": True, "breaks": True}).enable(["table", "strikethrough"])
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    marked, found = _extract_math(text)
    return _fill_tokens(_sanitize(_md.render(_end_lists(marked))), found)


class _Sanitizer(HTMLParser):
    """只放行排版用得着的标签和少数几个样式属性，其余标签去掉（文字留下），脚本之类连内容一起丢。

    这段 HTML 会被浏览器引擎加载（基地址是本地目录），所以绝不能让粘贴进来的内容带着脚本、
    事件属性、外部资源进去。
    """
    KEEP = {"p", "br", "strong", "b", "em", "i", "u", "s", "del", "code", "pre", "ul", "ol", "li",
            "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table", "thead", "tbody", "tr", "th", "td",
            "hr", "sub", "sup", "span", "div", "mark", "small"}
    DROP = {"script", "style", "iframe", "object", "embed", "svg", "math", "head", "title", "noscript",
            "template", "textarea", "select", "button", "form", "audio", "video", "canvas", "link", "meta"}
    VOID = {"br", "hr", "img", "input", "meta", "link", "wbr", "area", "base", "col", "embed", "source", "track"}
    STYLE = {"color", "background-color", "font-size", "font-family", "font-weight", "font-style",
             "text-decoration", "text-align"}
    _VALUE = re.compile(r"^[\w\s#%.,'\"()+-]{1,80}$")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.drop_depth = [], 0

    def _style(self, value: str) -> str:
        keep = []
        for decl in (value or "").split(";"):
            name, _, val = decl.partition(":")
            name, val = name.strip().lower(), val.strip()
            if name in self.STYLE and self._VALUE.match(val) and "url" not in val.lower() \
                    and "expression" not in val.lower():
                keep.append("%s:%s" % (name, val))
        return ";".join(keep)

    def handle_starttag(self, tag, attrs):
        if self.drop_depth:
            if tag not in self.VOID:
                self.drop_depth += 1
            return
        if tag in self.DROP:
            if tag not in self.VOID:
                self.drop_depth = 1
            return
        if tag not in self.KEEP:
            return
        a, extra = dict(attrs), ""
        style = self._style(a.get("style"))
        if style:
            extra += ' style="%s"' % html.escape(style, quote=True)
        if tag == "ol" and (a.get("start") or "").isdigit():
            extra += ' start="%s"' % a["start"]
        if tag == "code" and re.fullmatch(r"language-[\w+-]+", a.get("class") or ""):
            extra += ' class="%s"' % a["class"]
        self.out.append("<%s%s>" % (tag, extra))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.drop_depth:
            if tag not in self.VOID:
                self.drop_depth -= 1
        elif tag in self.KEEP and tag not in self.VOID:
            self.out.append("</%s>" % tag)

    def handle_data(self, data):
        if not self.drop_depth:
            self.out.append(html.escape(data, quote=False))


def _sanitize(body: str) -> str:
    p = _Sanitizer()
    p.feed(body)
    p.close()
    return "".join(p.out)


class _HtmlToMarkdown(HTMLParser):
    """从网页上复制下来的 HTML -> Markdown。

    只认排版用得着的标签，脚本、样式、按钮之类连内容一起丢掉；
    遇到 KaTeX 渲染好的公式（class 里带 katex），整块换成 $原始 LaTeX$ —— 原始 LaTeX 就藏在公式里的
    <annotation encoding="application/x-tex"> 中。
    转成 Markdown 而不是直接拿 HTML 去排版，是为了让每段粘贴内容都有一份能看能改的原文。
    """
    DROP = {"script", "style", "button", "svg", "head", "title", "noscript", "template", "textarea", "select"}
    VOID = {"br", "hr", "img", "input", "meta", "link", "wbr", "area", "base", "col", "embed", "source", "track"}
    INLINE = {"strong": "**", "b": "**", "em": "*", "i": "*", "del": "~~", "s": "~~"}
    BLOCK = {"p", "div", "section", "article", "blockquote", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.math_depth = 0     # > 0：正在一块渲染好的公式里面
        self.math_display = False
        self.math_tex = None
        self.in_annotation = False
        self.drop_depth = 0
        self.lists = []         # 每层列表：[类型, 已经数到第几项]
        self.in_pre = False
        self.row_cells = 0      # 表格当前这一行已经有几格
        self.header_done = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.math_depth:
            if tag not in self.VOID:
                self.math_depth += 1
            if tag == "annotation" and "x-tex" in (a.get("encoding") or ""):
                self.in_annotation, self.math_tex = True, ""
            if tag == "math" and a.get("display") == "block":
                self.math_display = True
            return
        if self.drop_depth:
            if tag not in self.VOID:
                self.drop_depth += 1
            return
        cls = (a.get("class") or "").split()
        if "katex" in cls or "katex-display" in cls:
            self.math_depth, self.math_tex = 1, None
            self.math_display = "katex-display" in cls
            return
        w = self.out.append
        if tag in self.DROP:
            self.drop_depth = 1
        elif tag in self.INLINE:
            w(self.INLINE[tag])
        elif tag == "br":
            w("\n")
        elif tag == "hr":
            w("\n\n---\n\n")
        elif tag == "pre":
            self.in_pre = True
            w("\n\n```\n")
        elif tag == "code" and not self.in_pre:
            w("`")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            w("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0])
            if len(self.lists) == 1:  # 最外层列表前空一行；嵌套的列表紧跟在上一项后面
                w("\n\n")
        elif tag == "li":
            kind, n = self.lists[-1] if self.lists else ("ul", 0)
            if self.lists:
                self.lists[-1][1] = n + 1
            w("\n" + "    " * max(0, len(self.lists) - 1) + ("- " if kind == "ul" else "%d. " % (n + 1)))
        elif tag == "table":
            self.header_done = False
            w("\n\n")
        elif tag == "tr":
            self.row_cells = 0
            w("\n|")
        elif tag in ("td", "th"):
            self.row_cells += 1
            w(" ")
        elif tag in self.BLOCK and not self.lists:
            w("\n\n" + ("> " if tag == "blockquote" else ""))

    def handle_startendtag(self, tag, attrs):
        if not self.math_depth and not self.drop_depth:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.math_depth:
            if tag == "annotation":
                self.in_annotation = False
            if tag not in self.VOID:
                self.math_depth -= 1
            if self.math_depth == 0 and self.math_tex and self.math_tex.strip():
                tex = self.math_tex.strip()
                self.out.append("\n\n$$\n%s\n$$\n\n" % tex if self.math_display else "$%s$" % " ".join(tex.split()))
            return
        if self.drop_depth:
            if tag not in self.VOID:
                self.drop_depth -= 1
            return
        w = self.out.append
        if tag in self.INLINE:
            w(self.INLINE[tag])
        elif tag == "pre":
            self.in_pre = False
            w("\n```\n\n")
        elif tag == "code" and not self.in_pre:
            w("`")
        elif tag in ("ul", "ol"):
            if self.lists:
                self.lists.pop()
            if not self.lists:
                w("\n\n")
        elif tag in ("td", "th"):
            w(" |")
        elif tag == "tr":
            if not self.header_done:  # Markdown 的表格必须有表头分隔行：第一行后面补上
                self.header_done = True
                w("\n|" + "---|" * max(1, self.row_cells))
        elif tag in self.BLOCK or tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if not self.lists:
                w("\n\n")

    def handle_data(self, data):
        if self.math_depth:
            if self.in_annotation:
                self.math_tex += data
        elif self.in_pre:
            self.out.append(data)
        elif not self.drop_depth:
            data = re.sub(r"\s+", " ", data)
            if data.strip() or (self.out and not self.out[-1].endswith(("\n", " "))):
                # 普通文字里的 $、*、< 不是公式 / 强调 / 标签的记号：转义掉
                self.out.append(data.replace("<", "&lt;").replace("$", "\\$").replace("*", "\\*"))


def html_to_markdown(source: str) -> str:
    p = _HtmlToMarkdown()
    p.feed(source)
    p.close()
    text = "".join(p.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def to_source(text: str, source_html: str = "") -> str:
    """剪贴板内容 -> 这段内容的原文（Markdown，公式是 LaTeX）。自动判断用哪一份：
    网页 HTML 里带着渲染好的公式时从 HTML 还原（这时纯文本那份里的公式通常是乱的）；否则就用纯文本。"""
    if source_html and "application/x-tex" in source_html:
        md = html_to_markdown(source_html)
        if "$" in md:
            return md
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def to_body(text: str, source_html: str = "") -> str:
    """剪贴板内容 -> 待排版的 HTML 片段。"""
    return markdown_to_body(to_source(text, source_html))


_SHELL = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="katex.min.css">
<style>
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: transparent; }
body { line-height: 1.45; overflow-wrap: anywhere; }
#c { padding: 2pt 3pt; display: flow-root; }
#c > :first-child { margin-top: 0; } #c > :last-child { margin-bottom: 0; }
p { margin: .5em 0; }
h1, h2, h3, h4, h5, h6 { margin: .7em 0 .35em; line-height: 1.25; }
h1 { font-size: 1.45em; } h2 { font-size: 1.28em; } h3 { font-size: 1.14em; } h4, h5, h6 { font-size: 1em; }
ul, ol { margin: .4em 0; padding-left: 1.6em; } li { margin: .15em 0; } li > p { margin: .2em 0; }
blockquote { margin: .5em 0; padding-left: .8em; border-left: 2pt solid #C7C7CC; color: #48484A; }
code { font-family: Consolas, "Cascadia Mono", monospace; font-size: .9em; background: #F0F0F3; border-radius: 2pt;
       padding: 0 2pt; }
pre { background: #F4F4F6; border-radius: 3pt; padding: 4pt 6pt; white-space: pre-wrap; font-size: .9em; margin: .5em 0; }
pre code { background: none; padding: 0; font-size: 1em; }
table { border-collapse: collapse; margin: .5em 0; } th, td { border: .5pt solid #8E8E93; padding: 2pt 5pt; }
th { background: #F0F0F3; }
hr { border: none; border-top: .5pt solid #C7C7CC; margin: .7em 0; }
.katex { font-size: 1.1em; } .katex-display { margin: .55em 0; }
.rm[data-d="1"] { display: block; }
</style>
<script src="katex.min.js"></script></head><body><div id="c"></div>
<script>
// 排一段内容：换掉正文、渲染公式、量出大小，用页面标题把结果报回去（RUIDONE 编号 宽 高，单位是网页像素）
window.ruiRender = function (job, body, width, family, size, color) {
  var c = document.getElementById('c'), st = document.body.style;
  st.width = width + 'pt'; st.fontFamily = family; st.fontSize = size + 'pt'; st.color = color;
  c.innerHTML = body;
  c.querySelectorAll('.rm').forEach(function (e) {
    try {
      katex.render(e.dataset.tex, e, {displayMode: e.dataset.d === '1', throwOnError: false, strict: 'ignore'});
    } catch (err) { e.textContent = e.dataset.tex; }
  });
  var report = function () {
    var r = c.getBoundingClientRect();
    document.title = 'RUIDONE ' + job + ' ' + Math.ceil(Math.max(r.width, c.scrollWidth)) + ' ' + Math.ceil(r.height);
  };
  // 字体在页面刚加载时就全部预先载入了，这里一般不用等；万一还有没到的（比如用到了系统里刚装的字体）再等一下
  if (document.fonts && document.fonts.status !== 'loaded') { document.fonts.ready.then(report); } else { report(); }
};
// 页面只加载这一次。先把 KaTeX 的二十个字体都载入，之后每次排版就不用再等字体了
var fonts = document.fonts ? Array.from(document.fonts).map(function (f) { return f.load().catch(function () {}); }) : [];
Promise.all(fonts).then(function () { document.title = 'RUIREADY'; });
</script></body></html>"""


class Renderer(QObject):
    """排版队列：一次排一段，排完用回调把结果（PDF 的字节，失败时为 None）交回去。

    浏览器页面只建一次、只加载一次（KaTeX 的脚本、样式、字体都留在里面），之后每次排版只是
    用脚本换掉正文再量大小，所以除了第一次要等引擎启动，后面都很快。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = None
        self._ready = False   # 页面加载好、字体都到齐了
        self._queue = []      # [(排版参数, 回调)]
        self._job = 0         # 当前这一段的编号；页面标题里带着它，过期的结果据此丢掉
        self._callback = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._finish(None))

    def warm_up(self):
        """提前把浏览器引擎和页面准备好（程序空闲时调用），这样第一次粘贴不用等那两三秒。"""
        if self._page is None:
            from PySide6.QtWebEngineCore import QWebEnginePage  # 用到时才加载浏览器引擎
            self._page = QWebEnginePage(self)
            self._page.setBackgroundColor("transparent")
            self._page.titleChanged.connect(self._on_title)
            self._page.setHtml(_SHELL, QUrl.fromLocalFile(KATEX_DIR + os.sep))

    def render(self, body: str, width_pt: float, family: str, size_pt: float, callback, color: str = "#111111"):
        fonts = ", ".join('"%s"' % f.replace('"', "") for f in (family, "Microsoft YaHei UI", "Microsoft YaHei",
                                                                "Segoe UI") if f) + ", sans-serif"
        self._queue.append(((body, round(width_pt, 2), fonts, round(size_pt, 2), color), callback))
        self.warm_up()
        if self._callback is None:
            self._next()

    def _next(self):
        if not self._queue or self._callback is not None:
            return
        if not self._ready:  # 页面还在加载：等它报 RUIREADY 再开始（给够时间，免得一直卡在这）
            if not self._timer.isActive():
                self._timer.start(TIMEOUT_MS)
            return
        params, self._callback = self._queue.pop(0)
        self._job += 1
        self._timer.start(TIMEOUT_MS)
        self._page.runJavaScript("ruiRender(%s)" % json.dumps([self._job, *params])[1:-1])

    def _on_title(self, title: str):
        if title == "RUIREADY":
            self._ready = True
            self._timer.stop()
            self._next()
            return
        parts = title.split()
        if len(parts) != 4 or parts[0] != "RUIDONE" or int(parts[1]) != self._job or self._callback is None:
            return
        job = self._job
        # 网页里的 1 px = 0.75 pt；高度多留一点，免得因为取整被分到第二页
        size = QSizeF(int(parts[2]) * 0.75 + 0.5, int(parts[3]) * 0.75 + 1.5)
        layout = QPageLayout(QPageSize(size, QPageSize.Point), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0))
        self._page.printToPdf(lambda data: self._finish(bytes(data)) if job == self._job else None, layout)

    def _finish(self, data):
        self._timer.stop()
        if self._callback is None and self._queue and not self._ready:
            _params, self._callback = self._queue.pop(0)  # 页面一直没加载好：让排在最前面的那个失败
        callback, self._callback = self._callback, None
        if callback is not None:
            try:
                callback(data if data else None)
            finally:
                QTimer.singleShot(0, self._next)

    def close(self):
        """丢掉还没排的，销毁浏览器页面。"""
        self._timer.stop()
        self._queue.clear()
        self._callback = None
        self._ready = False
        page, self._page = self._page, None
        if page is not None:
            page.setParent(None)  # 交还给 Python 管，下面这个引用一没，页面立刻销毁
            del page


_renderer = None


def _get() -> Renderer:
    global _renderer
    if _renderer is None:
        _renderer = Renderer()
    return _renderer


def warm_up():
    """提前启动浏览器引擎并加载好排版页面。主窗口显示后空闲时调用一次。"""
    _get().warm_up()


def shutdown():
    """程序退出前调用：浏览器页面必须在 QApplication 销毁之前先销毁，否则退出时会崩。"""
    global _renderer
    if _renderer is not None:
        _renderer.close()
        _renderer = None


def render(body: str, width_pt: float, family: str, size_pt: float, callback):
    """排版一段 HTML 片段（markdown_to_body 的结果），完成后调用 callback(PDF 字节或 None)。"""
    _get().render(body, width_pt, family, size_pt, callback)
