# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 的打包配置。用法见 build_exe.bat。
#
# 打成"一个文件夹"（dist/RuiPDF/RuiPDF.exe + _internal/），不打成单个 exe：
# 程序带着浏览器引擎（粘贴 AI 回答时排公式用），单文件每次启动都要先解压几百 MB，会很慢。
import os
import re

here = os.path.abspath(SPECPATH)
version = re.search(r'__version__ = "([^"]+)"', open(os.path.join(here, "ruipdf", "__init__.py"), encoding="utf8").read()).group(1)

a = Analysis(
    [os.path.join(here, "main.py")],
    pathex=[here],
    # 图标和 KaTeX 是程序运行时按 ruipdf/assets/ 这个相对位置去找的，原样带上
    datas=[(os.path.join(here, "ruipdf", "assets"), os.path.join("ruipdf", "assets"))],
    hiddenimports=["ruipdf.selftest"],
    # 这些是开发环境里碰巧装着、程序用不到的大块头，明确排除掉，免得被顺带打进去
    excludes=["tkinter", "numpy", "pymupdf4llm", "pymupdf_layout", "pyflakes", "PySide6.QtQuick3D",
              "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
              "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth", "PySide6.QtSql", "PySide6.QtTest",
              "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPdf", "PySide6.QtPdfWidgets"],
    noarchive=False,
)

def needed(entry) -> bool:
    """去掉浏览器引擎带的、这个程序用不到的东西（共一百多 MB）：
    调试版的资源包、几十种界面语言里除了中 / 英 / 德以外的。"""
    dest = entry[0].replace("\\", "/")
    name = dest.rsplit("/", 1)[-1]
    if name.endswith((".debug.pak", ".debug.bin")):
        return False
    if "/qtwebengine_locales/" in dest:
        return name in ("en-US.pak", "zh-CN.pak", "zh-TW.pak", "de.pak")
    if "/translations/" in dest and name.endswith(".qm"):
        return bool(re.search(r"_(zh_CN|zh_TW|en|de)\.qm$", name))
    return True


a.datas = [e for e in a.datas if needed(e)]
a.binaries = [e for e in a.binaries if needed(e)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RuiPDF",
    console=False,  # 窗口程序，不带黑色的控制台窗口
    icon=os.path.join(here, "ruipdf", "assets", "icon.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RuiPDF", upx=False)
