"""程序的设置存在哪。

平时是 QSettings("RuiPDF", "RuiPDF")，在 Windows 上就是注册表 HKCU\\Software\\RuiPDF\\RuiPDF。
设了环境变量 RUIPDF_SETTINGS（一个 .ini 文件的路径）时改用那个文件 —— 测试用它，
免得测试把平时用的设置改掉。

注意：QSettings.setDefaultFormat / setPath 对 QSettings("组织", "程序") 这种写法不起作用
（它总是用系统原生的存法），早先的冒烟测试靠它们隔离，在 Windows 上其实一直在读写真实设置。
"""
import os

from PySide6.QtCore import QSettings


def app_settings() -> QSettings:
    path = os.environ.get("RUIPDF_SETTINGS")
    if path:
        return QSettings(path, QSettings.IniFormat)
    return QSettings("RuiPDF", "RuiPDF")
