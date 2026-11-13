"""界面语言。源码里的界面文字是中文，T("中文") 在英文界面下返回对应的英文。"""
from PySide6.QtCore import QLocale

from .appsettings import app_settings


def _initial_language() -> str:
    saved = app_settings().value("language", "")
    if saved in ("zh", "en"):
        return saved
    return "zh" if QLocale.system().language() == QLocale.Language.Chinese else "en"


LANG = _initial_language()
EN = {}  # 中文 -> English，见文件末尾


def T(text: str) -> str:
    if LANG == "en":
        return EN.get(text, text)
    return text


EN.update({
    # 配色方案
    "经典": "Classic", "鲜艳": "Vivid", "柔和": "Soft", "深色": "Deep", "暖色": "Warm", "冷色": "Cool",
    "自定义": "Custom",
    # 顶部工具栏
    "文件": "File", "视图": "View", "工具": "Tools", "笔设置": "Pen settings",
    "打开": "Open", "保存": "Save", "另存为": "Save As", "撤销": "Undo", "重做": "Redo",
    "缩小": "Zoom Out", "放大": "Zoom In", "适合宽度": "Fit Width",
    "页面": "Page", "复习": "Review", "设置": "Settings",
    "查找": "Find", "分屏": "Split", "侧栏": "Sidebar", "全屏": "Full Screen",
    "关闭标签页": "Close tab", "下一个标签页": "Next tab", "上一个标签页": "Previous tab",
    "查找下一个": "Find next", "查找上一个": "Find previous",
    "在当前页后插入空白页": "Insert blank page after this page",
    "当前页右侧加留白": "Add margin on the right",
    "当前页底部加留白": "Add margin at the bottom",
    "调整当前页的留白…": "Adjust this page's margins…", "去掉当前页的留白": "Remove this page's margins",
    "自己定右侧 / 底部留白的宽度，或把加过的留白改小、去掉": "Set the right / bottom margin width yourself, or shrink or remove margins added earlier",
    "去掉留白": "Remove margins", "调整留白": "Adjust margins", "右侧留白": "Right margin", "底部留白": "Bottom margin",
    " 毫米": " mm", "第 {} 页：原来的页面 {:.0f} × {:.0f} 毫米": "Page {}: original page {:.0f} × {:.0f} mm",
    "这一页没有可以去掉的留白。\n（只认得这个版本开始加的留白；更早加的没有记录。）":
        "This page has no margins that can be removed.\n(Only margins added from this version on are recorded.)",
    "填 0 就是去掉。改小或去掉留白时，留白里被裁掉的那部分上的笔迹、文字、图片会一起删掉，而且不能撤销。":
        "0 removes the margin. When a margin is shrunk or removed, ink, text and images on the part that is cut off are deleted too, and this cannot be undone.",
    "留白改小后，被裁掉的那部分就没有了。": "After shrinking, the part that is cut off is gone.",
    "那里有 {} 个对象（笔迹、文字、图片）会被删掉。": "{} objects there (ink, text, images) will be deleted.",
    "那里现在没有笔迹。": "There is nothing drawn there right now.",
    "这一步不能撤销，之前的撤销记录也会清空。确定吗？": "This cannot be undone, and the undo history will be cleared. Continue?",
    "删除当前空白页": "Delete this blank page",
    "给当前页加书签": "Bookmark this page",
    "导出有标注的页…": "Export annotated pages…",
    "插入图片…": "Insert image…", "插入图片": "Insert image", "图片 ({})": "Images ({})",
    "这不是能识别的图片。": "This is not a readable image.",
    "图片 / 粘贴的内容": "Images / pasted content",
    "粘贴剪贴板里的内容（Ctrl+V）": "Paste clipboard contents (Ctrl+V)",
    "正在排版要粘贴的内容…": "Typesetting the pasted content…",
    "排版失败，没有粘贴。": "Typesetting failed; nothing was pasted.",
    "内容比这一页长，超出页面的部分看不到：可以拉右下角缩小，或先用“页面 → 底部加留白”。":
        "The content is taller than this page and the overflow is hidden: drag the corner handle to shrink it, "
        "or add space first with Page → Add space at bottom.",
    "已粘贴。拖动移动，拖四角缩放，拖左右两边改宽度，双击改内容。":
        "Pasted. Drag to move, drag a corner to scale, drag the left/right edge to change width, "
        "double-click to edit.",
    "悬浮工具栏的不透明度…": "Floating toolbar opacity…", "悬浮工具栏的不透明度": "Floating toolbar opacity",
    "只改变工具条那块底的透明程度，上面的按钮不会变淡。工具栏固定在窗口顶部时不起作用。":
        "Only the bar's background changes; the buttons on it stay solid. No effect when the toolbar is fixed at the top of the window.",
    "更多": "More", "收起": "Less",
    "展开 / 收起其余的按钮（问 Claude、分屏、设置等）": "Show / hide the remaining buttons (Ask Claude, split view, settings…)",
    "界面风格": "Appearance", "液态玻璃": "Liquid glass", "浅色": "Light", "深色主题": "Dark",
    "浅绿色": "Light green", "浅紫色": "Light purple", "浅蓝色": "Light blue",
    "搜索": "Search", "搜索全文，按回车": "Search the document, press Enter", "共 {} 处": "{} matches",
    "共 {} 处（列表只显示前 {} 处）": "{} matches (only the first {} are listed)", "没有找到": "No matches",
    "结果列表": "Results", "在侧栏里列出全部搜索结果，点一条跳过去": "List all matches in the sidebar; click one to jump to it",
    "查找（Ctrl+F）": "Find (Ctrl+F)",
    "搜索 PDF 里的文字：回车 = 下一处，Shift+回车 = 上一处，Esc = 清掉": "Search the PDF text: Enter = next, Shift+Enter = previous, Esc = clear",
    "贴靠在哪一边": "Dock on which side", "右边": "the right", "左边": "the left",
    "{} 已贴在{}，会跟着这个窗口移动和缩放；再点一次取消。": "{} is docked on {} and follows this window; click again to undock.",
    "工具栏位置": "Toolbar position", "悬浮在上方": "Floating at the top", "悬浮在下方": "Floating at the bottom",
    "悬浮在左侧": "Floating on the left", "悬浮在右侧": "Floating on the right",
    "固定在窗口顶部（不悬浮）": "Fixed at the top of the window (not floating)",
    "笔设置": "Pen settings", "展开 / 收起笔的设置（笔触、粗细、配色）": "Show / hide pen settings (stroke style, width, palette)",
    "界面字体": "Interface font", "系统默认（微软雅黑）": "System default",
    "现代（Segoe UI Variable + 思源黑体）": "Modern (Segoe UI Variable + Noto Sans SC)",
    "现代 · 略粗（玻璃底上更清楚）": "Modern, medium weight (clearer on glass)", "轻盈（细一些）": "Light (thinner)",
    "液态玻璃效果": "Liquid glass effect", "重启 RuiPDF 后生效。": "Takes effect after restarting RuiPDF.",
    "工具栏变成半透明的玻璃质感，透出窗口后面模糊的桌面（需要 Windows 11）":
        "Translucent glass toolbars showing the blurred desktop behind the window (needs Windows 11)",
    "加粗（Ctrl+B）": "Bold (Ctrl+B)", "下划线（Ctrl+U）": "Underline (Ctrl+U)", "文字颜色": "Text colour",
    "其他颜色…": "More colours…", "先选中要改格式的文字。": "Select the text to format first.",
    "正在重新排版…": "Re-typesetting…", "已重新排版。": "Re-typeset.",
    "重新排版失败，内容没有变。": "Re-typesetting failed; the content is unchanged.",
    "正在改这段内容的原文（公式是 LaTeX）。点别处或 Ctrl+回车确认并重新排版，Esc 放弃。":
        "Editing the source of this block (formulas are LaTeX). Click elsewhere or press Ctrl+Enter to apply "
        "and re-typeset; Esc cancels.",
    "粘贴内容的字体和大小…": "Pasted text font and size…",
    "粘贴内容的字体和大小": "Pasted text font and size",
    "用默认字体": "Use the default font",
    "自动（按页面宽度：A4 约 11 pt，宽屏幻灯片 16 pt）": "Automatic (by page width: about 11 pt on A4, 16 pt on wide slides)",
    "字体": "Font", "宽度（页面宽度的百分比）": "Width (% of page width)",
    "公式用 KaTeX 自己的数学字体，不受这里的字体影响。贴进去之后还可以用套索拉右下角整体缩放。":
        "Formulas use KaTeX's own math fonts and are not affected by this font. After pasting you can still "
        "scale the whole block with the lasso's corner handle.",
    "导出有标注的页": "Export annotated pages",
    "全部遮住": "Cover all", "全部揭开": "Reveal all",
    "书写分辨率": "Ink resolution", "笔迹平滑": "Stroke smoothing", "光标样式": "Cursor style",
    "100%（最省内存）": "100% (least memory)", "200%（推荐）": "200% (recommended)",
    "300%（最细腻，占内存）": "300% (smoothest, more memory)",
    "关": "Off", "低": "Low", "中": "Medium", "高（更顺滑，略有滞后）": "High (smoother, slight lag)",
    "搜索 PDF 里的文字（Ctrl+F）": "Search the PDF's text (Ctrl+F)",
    "把当前标签移到另一栏，两个 PDF 并排显示；再按一次移回来":
        "Move this tab to the other pane to view two PDFs side by side; press again to move it back",
    "缩略图 / 目录 / 书签 / 标注汇总": "Thumbnails / Outline / Bookmarks / Annotation summary",
    # 工具条
    "笔": "Pen", "荧光笔": "Highlighter", "橡皮": "Eraser", "套索": "Lasso", "形状": "Shape",
    "文本": "Text", "遮挡": "Cover",
    "直线": "Line", "箭头": "Arrow", "矩形": "Rectangle", "椭圆": "Ellipse",
    "橡皮（整个对象擦除；按住笔侧键可临时使用）":
        "Eraser (removes whole objects; hold the pen's side button to use it temporarily)",
    "套索选择：圈住后可拖动、拉右下角缩放、点颜色改色；右键有复制 / 剪切 / 粘贴 / 删除":
        "Lasso: circle objects, then drag to move, pull the corner handle to scale, "
        "click a colour to recolour; right-click for Copy / Cut / Paste / Delete",
    "复制": "Copy", "剪切": "Cut", "粘贴": "Paste",
    "形状（点右侧小箭头换种类）": "Shape (click the small arrow to change type)",
    "文本框：点空白处新建，点已有文字修改": "Text box: click empty space to add, click existing text to edit",
    "遮挡块：拖出一块盖住答案；点一下揭开，用本工具再点一下重新遮住":
        "Cover block: drag to hide an answer; tap to reveal, tap again with this tool to cover it",
    "笔色 {}": "Pen colour {}", "荧光色 {}": "Highlighter colour {}",
    "细": "Thin", "粗": "Thick",
    "{}（预设：笔、荧光笔、文本字号一起变）": "{} (preset: sets pen, highlighter and text size together)",
    "粗细": "Width", "  粗细 ": "  Width ", "荧光笔宽": "Highlighter", "字号": "Text size",
    "钢笔（压感）": "Fountain pen (pressure)", "圆珠笔（等粗）": "Ballpoint (uniform)",
    "毛笔（压感强烈）": "Brush (strong pressure)",
    "笔触风格（只影响之后写的笔画）": "Pen style (affects new strokes only)",
    "粗细随页面": "Width follows page", "粗细随屏幕": "Width follows screen",
    "粗细随页面：线按页面算，放大后看起来也变粗，写出来始终一样粗\n粗细随屏幕：放大后笔看起来不变粗，实际画出的线更细，适合放大写小字":
        "Follows page: width is measured on the page, so strokes look thicker when zoomed in "
        "and are always the same size on paper\n"
        "Follows screen: the pen looks the same at any zoom, so strokes drawn while zoomed in "
        "are finer on the page (good for small writing)",
    "配色方案：一次换掉左侧 4 个笔色和 3 个荧光色":
        "Colour scheme: replaces the 4 pen colours and 3 highlighter colours at once",
    "调色盘…": "Colour…", "调色盘": "Choose colour",
    "自选颜色，替换左侧当前选中的那个色块（当前是荧光笔时替换荧光色）":
        "Pick any colour to replace the currently selected swatch "
        "(the highlighter swatch when the highlighter is active)",
    "圆点（随笔宽和颜色变化）": "Dot (matches pen width and colour)", "圆环": "Ring", "实心圆点（固定大小）": "Solid dot (fixed size)",
    "圆点 + 刻度": "Dot with ticks", "细十字": "Fine crosshair", "系统箭头": "System arrow",
    # 查找栏
    "  查找 ": "  Find ", "输入后按回车；回车 = 下一个": "Type and press Enter; Enter = next",
    "上一个": "Previous", "下一个": "Next", "关闭": "Close",
    "  没有找到  ": "  No matches  ", "  第 {} / {} 处  ": "  {} of {}  ",
    # 状态栏
    "  第 {} / {} 页  ": "  Page {} / {}  ", "缩放 {}%": "Zoom {}%", "已保存": "Saved",
    "鼠标（无压感）": "Mouse (no pressure)", "数位板  压感 {:.2f}": "Tablet  pressure {:.2f}",
    "已导出 {} 页": "Exported {} pages",
    # 对话框
    "打开 PDF（Ctrl+O），或把文件拖进来": "Open a PDF (Ctrl+O), or drop a file here",
    "打开 PDF": "Open PDF", "PDF 文件 (*.pdf)": "PDF files (*.pdf)",
    "_标注": "_annotated", "_标注页": "_annotated_pages",
    "恢复笔迹": "Recover work", "恢复": "Recover", "丢弃": "Discard",
    "上次有没保存的内容（自动备份于 {}）。要恢复吗？":
        "There is unsaved work from last time (auto-backup at {}). Recover it?",
    "未保存": "Unsaved changes", "不保存": "Don't Save", "取消": "Cancel",
    "有内容还没有保存，要保存吗？": "There are unsaved changes. Save them?",
    "保存失败": "Save failed",
    "如果这个 PDF 正被别的软件打开，请先关掉它再保存，或者用“另存为”。":
        "If this PDF is open in another program, close it there first, or use Save As.",
    "打不开": "Cannot open", "文件里没有页面": "The file has no pages",
    "分屏需要至少打开两个 PDF。": "Split view needs at least two open PDFs.",
    "导出": "Export", "导出失败": "Export failed",
    "这个 PDF 里还没有标注。": "This PDF has no annotations yet.",
    "不能覆盖当前打开的文件，请换一个文件名。": "Cannot overwrite the open file; choose another name.",
    "删除空白页": "Delete blank page",
    "只能删除由 RuiPDF 插入的空白页，当前页是 PDF 原有的页面。":
        "Only blank pages inserted by RuiPDF can be deleted; this page belongs to the original PDF.",
    "第 {} 页上有笔迹，删除后无法撤销。确定删除吗？":
        "Page {} has annotations, and deleting it cannot be undone. Delete it?",
    "输入文字：": "Enter text:",
    # 新建笔记 / 模板
    "新建": "New", "新建笔记": "New note", "新建笔记：选一种模板纸，生成一个新的 PDF":
        "New note: pick a paper template and create a new PDF",
    "新建笔记（Ctrl+N），打开 PDF（Ctrl+O），或把文件拖进来":
        "New note (Ctrl+N), open a PDF (Ctrl+O), or drop a file here",
    "插入模板页": "Insert template page", "保存新笔记": "Save new note", "笔记": "Notes",
    "这个文件正开着，请换一个文件名。": "That file is currently open; choose another name.",
    "竖向 A4": "A4 portrait", "横向 A4": "A4 landscape", "纸张": "Paper", "页数": "Pages", "创建": "Create",
    "之后随时可以用 Ctrl+Shift+N 在当前页后面加一页同样的纸":
        "You can add another page of the same paper after the current one at any time with Ctrl+Shift+N",
    "空白": "Blank", "横线": "Lined", "方格": "Grid", "点阵": "Dotted", "康奈尔笔记": "Cornell notes",
    "坐标纸": "Graph paper", "错题本": "Mistake log", "待办清单": "To-do list",
    "主题": "Topic", "日期": "Date", "线索 / 问题": "Cues / Questions", "总结": "Summary",
    "科目 / 章节": "Subject / Chapter", "来源": "Source", "题目": "Problem",
    "我的解答 / 错因": "My attempt / What went wrong", "正确解法": "Correct solution",
    "总结 / 易错点": "Takeaways / Pitfalls",
    "关于": "About", "关于 RuiPDF": "About RuiPDF", "版本 {}": "Version {}", "作者：{}": "Author: {}",
    "配合数位板在 PDF 上手写标注、复习备考的工具。":
        "A tool for handwriting annotations on PDFs with a pen tablet, built for exam review.",
    # 和 Claude 窗口配合
    "Claude 分屏": "Claude side-by-side",
    "把对话窗口（Claude / ChatGPT / Chrome，在“设置”里选对象和大小）贴在本窗口右边，并跟着本窗口移动和缩放；再点一次取消":
        "Dock the chat window (Claude / ChatGPT / Chrome; pick the app and size under Settings) to the right of "
        "this window; it follows this window when moved or resized. Click again to release",
    "已取消贴靠。": "Docked window released.",
    "{} 已贴在右边，会跟着这个窗口移动和缩放；再点一次取消。":
        "{} is docked on the right and follows this window. Click again to release.",
    "Chrome 浏览器": "Chrome browser",
    "贴靠 / 粘贴的对象": "App to dock / paste into",
    "贴靠窗口的大小…": "Docked window size…",
    "贴靠窗口的大小": "Docked window size",
    "宽度（本窗口宽度的百分比）": "Width (% of this window's width)",
    "高度（本窗口高度的百分比）": "Height (% of this window's height)",
    "对方窗口有自己的最小尺寸（Claude 桌面应用宽约 600 像素），设得比它小时以它的最小尺寸为准。":
        "The other window has its own minimum size (the Claude desktop app is about 600 px wide); "
        "smaller values fall back to that minimum.",
    "“问 Claude”发到哪里": "Where “Ask Claude” sends",
    "Claude 窗口（桌面应用或网页，不需要密钥）": "Claude window (desktop app or web, no key needed)",
    "API（侧栏面板，需要密钥）": "API (side panel, needs a key)",
    "已复制。没找到 {} 的窗口，请打开它后按 Ctrl+V 粘贴。":
        "Copied. No {} window found; open it and press Ctrl+V to paste.",
    "选字": "Select text",
    "选择文字：在 PDF 自带的文字上拖过去选中，Ctrl+C 复制成文本；点“问”把选中的文字粘贴到对话窗口。扫描件没有文字可选":
        "Select text: drag across the PDF's own text, Ctrl+C copies it as text; “Ask” pastes the selected text "
        "into the chat window. Scanned pages have no selectable text",
    "这一页没有可以选的文字（扫描件或图片），请用套索截图":
        "No selectable text on this page (scan or image); use the lasso to take a screenshot instead",
    "已粘贴到 {}，输入问题后回车发送。": "Pasted into {}; type your question and press Enter.",
    "没找到 {} 的窗口。请先打开它（Claude / ChatGPT 也可以是浏览器里正显示着的网页），再点一次。":
        "No {} window found. Open it first (for Claude / ChatGPT a browser window currently showing the site "
        "also works), then try again.",
    # Claude 面板
    "问 Claude": "Ask Claude",
    "问 {}": "Ask {}", "{} 分屏": "{} side-by-side",
    "把套索选中的内容（没有选中则是当前页）发给 {} 提问":
        "Send the lasso selection (or the current page if nothing is selected) to {}",
    "讲解": "Explain", "翻译": "Translate", "出题": "Quiz me", "检查": "Check",
    "请讲解这部分内容：它在说什么，关键点和容易出错的地方是什么。":
        "Explain this part: what it says, the key points, and the common pitfalls.",
    "请把这部分内容翻译成中文，术语保留原文。":
        "Translate this part into English, keeping technical terms in the original language in brackets.",
    "请根据这部分内容出 3 道考试风格的题目，先只给题目；我作答后再给答案和解析。":
        "Write 3 exam-style questions on this part. Give only the questions first; "
        "give answers and explanations after I respond.",
    "请检查图中我手写的解答：哪一步有错，正确的做法是什么。":
        "Check my handwritten solution in the image: which step is wrong, and what is the correct approach?",
    "模型。Sonnet 快而便宜，Opus / Fable 更强更贵。":
        "Model. Sonnet is fast and cheap; Opus / Fable are stronger and cost more.",
    "API 密钥…": "API key…", "Claude API 密钥": "Claude API key",
    "在 Claude Console（platform.claude.com）创建 API 密钥后粘贴到这里。\n"
    "密钥只保存在这台电脑上。使用时，选中的截图和问题会发送给 Anthropic，按用量计费。":
        "Create an API key in the Claude Console (platform.claude.com) and paste it here.\n"
        "The key is stored only on this computer. When you ask, the selected screenshot and your question "
        "are sent to Anthropic and billed by usage.",
    "输入问题，回车发送（Shift+回车换行）": "Type a question, Enter to send (Shift+Enter for a new line)",
    "发送": "Send", "停止": "Stop", "贴到页面": "Paste to page", "清空": "Clear",
    "把最后一条回答作为文本框贴到当前页": "Paste the last answer onto the current page as a text box",
    "没有收到回答。": "No answer was received.",
    "密钥无效，请点“API 密钥…”重新填写。": "The key is invalid; click “API key…” to enter it again.",
    "账户没有权限或余额不足，请到 Claude Console 检查。":
        "The account lacks permission or credit; check the Claude Console.",
    "模型代号不对，请换一个模型。": "Unknown model ID; pick another model.",
    "请求太频繁或额度用完了，稍后再试。": "Rate limit or quota reached; try again later.",
    "网络连接失败，请检查网络。": "Network error; check your connection.",
    "还没有可以贴的回答。": "There is no answer to paste yet.",
    "用套索圈住讲义上的一块内容，右键选“问 Claude”；或点顶部的“问 Claude”发送当前页。":
        "Circle part of a page with the lasso and right-click “Ask Claude”, "
        "or click “Ask Claude” in the top bar to send the current page.",
    "你": "You", "出错了": "Something went wrong",
    # 侧栏
    "缩略图": "Pages", "目录": "Outline", "书签": "Bookmarks", "标注": "Notes",
    "＋ 当前页": "+ This page", "删除": "Delete", "书签名称：": "Bookmark name:",
    "第 {} 页": "Page {}", "{}  （第 {} 页）": "{}  (page {})",
    "笔迹": "Ink", "遮挡块": "Cover blocks",
    "{}  {} 处 · {} 页": "{}  {} items · {} pages", "第 {} 页（{} 处）": "Page {} ({})",
})
