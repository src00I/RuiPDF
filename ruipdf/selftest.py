"""打包后的自检：RuiPDF.exe --selftest 报告文件.json

打包成 exe 之后，最容易出问题的是"东西没带全"：图标、KaTeX、PDF 库、浏览器引擎。
这里把这几样各用一次，把结果写进报告文件（exe 是窗口程序，没有控制台可以打印），全部正常时退出码为 0。
不读写平时的设置，不打开主窗口。
"""
import json
import os
import sys
import time
import traceback


def run(report_path: str) -> int:
    report = {"frozen": bool(getattr(sys, "frozen", False)), "exe": sys.executable, "checks": {}}
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            report["checks"][name] = fn()
        except Exception:
            ok = False
            report["checks"][name] = "失败: " + traceback.format_exc(limit=3)

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])

    def icon():
        from .mainwindow import ASSETS, app_icon
        sizes = sorted({s.width() for s in app_icon().availableSizes()})
        assert sizes, "没有找到图标文件：" + ASSETS
        return {"目录": ASSETS, "尺寸": sizes}

    def pdf():
        import pymupdf
        d = pymupdf.open()
        d.new_page().insert_text((50, 50), "selftest")
        data = d.tobytes()
        d.close()
        assert pymupdf.open(stream=data, filetype="pdf")[0].get_text().strip() == "selftest"
        return pymupdf.__doc__.split("\n")[0]

    def katex():
        from .richpaste import KATEX_DIR
        names = ["katex.min.js", "katex.min.css", os.path.join("fonts", "KaTeX_Main-Regular.woff2")]
        missing = [n for n in names if not os.path.exists(os.path.join(KATEX_DIR, n))]
        assert not missing, "缺文件：%s（目录 %s）" % (missing, KATEX_DIR)
        return {"目录": KATEX_DIR, "字体数": len(os.listdir(os.path.join(KATEX_DIR, "fonts")))}

    def typeset():
        import pymupdf
        from . import richpaste
        result = {}
        t0 = time.perf_counter()
        body = richpaste.markdown_to_body("自检 **粗体** $E=mc^2$\n\n$$\\int_0^1 x\\,dx=\\tfrac12$$")
        richpaste.render(body, 260, "", 11, lambda data: (result.update(data=data), app.quit()))
        QTimer.singleShot(40000, app.quit)
        app.exec()
        richpaste.shutdown()
        data = result.get("data")
        assert data, "浏览器引擎没有排出结果（40 秒内）"
        doc = pymupdf.open(stream=data, filetype="pdf")
        fonts = sorted({f[3] for f in doc[0].get_fonts()})
        assert len(doc) == 1 and any("KaTeX" in f for f in fonts), "排出来的结果不对：%d 页，字体 %s" % (len(doc), fonts)
        return {"秒": round(time.perf_counter() - t0, 1), "字节": len(data), "KaTeX 字体": sum("KaTeX" in f for f in fonts)}

    check("图标", icon)
    check("PDF 库", pdf)
    check("KaTeX 文件", katex)
    check("公式排版（浏览器引擎）", typeset)
    report["ok"] = ok
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return 0 if ok else 1
