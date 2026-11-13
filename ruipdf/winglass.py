"""液态玻璃效果要用的系统毛玻璃背景（Windows 11 的 Acrylic：窗口后面的桌面被模糊后透出来）。

做法：主窗口设成背景透明（Qt 的 WA_TranslucentBackground），再让系统在整个窗口后面铺一层
毛玻璃；界面上半透明的地方（工具栏、状态栏）就会透出它来，不透明的地方（页面）不受影响。
需要 Windows 11 22H2（内部版本 22621）及以上；更老的系统上 available() 返回 False，界面保持原样。
"""
import sys

MIN_BUILD = 22621  # Windows 11 22H2：从这一版开始才有 DWMWA_SYSTEMBACKDROP_TYPE


def available() -> bool:
    return sys.platform == "win32" and sys.getwindowsversion().build >= MIN_BUILD


def enable_popup(hwnd: int) -> bool:
    """给弹出窗口（菜单、下拉列表）铺毛玻璃，并让系统把它的四个角切圆、加上阴影。"""
    if not enable(hwnd):
        return False
    try:
        import ctypes
        from ctypes import wintypes
        pref = ctypes.c_int(2)  # DWMWA_WINDOW_CORNER_PREFERENCE = 33，DWMWCP_ROUND = 2
        ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        return True
    except Exception:
        return False


def disable_popup(hwnd: int) -> bool:
    """撤掉弹出窗口的毛玻璃（圆角和系统阴影留着，它的方形阴影已经关掉了）。"""
    disable(hwnd)
    try:
        import ctypes
        from ctypes import wintypes
        pref = ctypes.c_int(2)
        ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(wintypes.HWND(hwnd), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        return True
    except Exception:
        return False


def set_caption(hwnd: int, color=None, dark: bool = False) -> bool:
    """让系统标题栏（最上面带最小化 / 关闭按钮的那一条）跟着界面风格变色。
    color 是 "#RRGGBB"，None = 恢复系统默认；dark 为真时标题文字和按钮用浅色。需要 Windows 11。"""
    if not available():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        dwm, h = ctypes.WinDLL("dwmapi"), wintypes.HWND(hwnd)

        def put(attr, value):
            v = ctypes.c_uint(value)
            return dwm.DwmSetWindowAttribute(h, attr, ctypes.byref(v), ctypes.sizeof(v))

        if color is None:
            ref = 0xFFFFFFFF  # DWMWA_COLOR_DEFAULT
        else:
            c = int(color.lstrip("#"), 16)
            ref = ((c & 0xFF) << 16) | (c & 0xFF00) | (c >> 16)  # COLORREF 是 0x00BBGGRR
        put(20, 1 if dark else 0)        # DWMWA_USE_IMMERSIVE_DARK_MODE：标题文字、按钮的深浅
        r = put(35, ref)                 # DWMWA_CAPTION_COLOR：标题栏底色
        put(34, ref)                     # DWMWA_BORDER_COLOR：窗口那圈细边
        return r == 0
    except Exception:
        return False


def disable(hwnd: int) -> bool:
    """撤掉窗口的毛玻璃背景（关掉液态玻璃时用）。"""
    if not available():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        kind = ctypes.c_int(1)  # DWMSBT_NONE
        r = ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(wintypes.HWND(hwnd), 38, ctypes.byref(kind), ctypes.sizeof(kind))
        return r == 0
    except Exception:
        return False


def enable(hwnd: int) -> bool:
    """给窗口铺上毛玻璃背景。窗口必须是背景透明的才看得到。成功返回 True。"""
    if not available():
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class MARGINS(ctypes.Structure):
            _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int), ("bottom", ctypes.c_int)]

        dwm = ctypes.WinDLL("dwmapi")
        kind = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW = Acrylic；窗口不在前台时也保持模糊（Mica 会变成纯色）
        r1 = dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 38, ctypes.byref(kind), ctypes.sizeof(kind))
        margins = MARGINS(-1, -1, -1, -1)  # 背景铺满整个窗口，不只是标题栏
        r2 = dwm.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(margins))
        return r1 == 0 and r2 == 0
    except Exception:
        return False
