"""和 Claude 桌面应用（或浏览器里的 Claude 页面）配合：找到它的窗口、把它贴在自己右边、把剪贴板内容贴过去。

只在 Windows 上有效，其他系统下这些函数什么都不做并返回 0 / False。
"""
import os
import sys

IS_WIN = sys.platform == "win32"

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        dwmapi = ctypes.WinDLL("dwmapi")
    except OSError:
        dwmapi = None

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    _ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _sig(fn, restype, *argtypes):
        fn.restype, fn.argtypes = restype, list(argtypes)

    _sig(user32.EnumWindows, wintypes.BOOL, _ENUMPROC, wintypes.LPARAM)
    _sig(user32.IsWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsIconic, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsZoomed, wintypes.BOOL, wintypes.HWND)
    _sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
    _sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _sig(user32.GetWindowRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(RECT))
    _sig(user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
         ctypes.c_int, ctypes.c_int, wintypes.UINT)
    _sig(user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
    _sig(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.MonitorFromWindow, wintypes.HANDLE, wintypes.HWND, wintypes.DWORD)
    _sig(user32.GetMonitorInfoW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(MONITORINFO))
    _sig(user32.keybd_event, None, wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p)
    _sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
    _sig(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
         wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    if dwmapi is not None:
        _sig(dwmapi.DwmGetWindowAttribute, ctypes.c_long, wintypes.HWND, wintypes.DWORD,
             ctypes.c_void_p, wintypes.DWORD)

    def _exe_name(pid: int) -> str:
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(520)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
            return ""
        finally:
            kernel32.CloseHandle(handle)

    def _cloaked(hwnd) -> bool:
        """窗口是不是"看不见但算可见"的（别的虚拟桌面上的、被系统藏起来的商店应用窗口）。"""
        if dwmapi is None:
            return False
        v = wintypes.DWORD(0)  # 14 = DWMWA_CLOAKED
        return dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(v), ctypes.sizeof(v)) == 0 and v.value != 0

    def _rect(hwnd) -> RECT:
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r


# 可以贴靠 / 粘贴的对象：代号 -> (桌面应用的进程名, 标题里要带的词)。
# 进程名对上的优先；标题带那个词的其次（比如浏览器里正开着的 claude.ai / chatgpt.com 标签）。
# Chrome 没有标题要求，任何一个 Chrome 窗口都算。
TARGETS = {
    "claude": ("claude.exe", "claude"),
    "chatgpt": ("chatgpt.exe", "chatgpt"),
    "chrome": ("chrome.exe", None),
}


def find_claude_window() -> int:
    return find_window("claude")


def find_window(target: str = "claude") -> int:
    """找某个对象的窗口（见 TARGETS）。找不到返回 0。

    同一优先级里有多个窗口时：Claude / ChatGPT 取面积最大的；Chrome 取最靠前（最近用过）的。
    """
    if not IS_WIN or target not in TARGETS:
        return 0
    want_exe, want_title = TARGETS[target]
    found = []  # (优先级, 面积, hwnd)，按叠放次序从前到后
    me = os.getpid()

    def visit(hwnd, _lparam):
        try:
            if not hwnd or not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == me:
                return True
            exe = _exe_name(pid.value)
            score = 2 if exe == want_exe else (1 if want_title and want_title in buf.value.lower() else 0)
            if score and not _cloaked(hwnd):
                r = _rect(hwnd)
                w, h = r.right - r.left, r.bottom - r.top
                if user32.IsIconic(hwnd) or (w > 300 and h > 200):  # 跳过托盘气泡之类的小窗口
                    found.append((score, w * h, hwnd))
        except Exception:
            pass
        return True

    user32.EnumWindows(_ENUMPROC(visit), 0)
    if not found:
        return 0
    if want_title is None:  # Chrome：sort 是稳定的，同优先级保持从前到后的叠放次序
        found.sort(key=lambda t: t[0], reverse=True)
    else:
        found.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return int(found[0][2])


def _frame(hwnd: int):
    """窗口可见边框的 (左, 上, 右, 下)，物理像素。"""
    if dwmapi is not None:
        frame = RECT()  # 9 = DWMWA_EXTENDED_FRAME_BOUNDS
        if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(frame), ctypes.sizeof(frame)) == 0:
            return frame.left, frame.top, frame.right, frame.bottom
    r = _rect(hwnd)
    return r.left, r.top, r.right, r.bottom


def _place(hwnd: int, x: int, y: int, w: int, h: int, behind: int = 0, flags: int = 0):
    """把窗口的可见边框放到 (x, y, w, h)。Windows 10/11 的窗口外面有一圈看不见的边框，要补偿掉。

    behind 不为 0 时，顺便把窗口在叠放次序里排到 behind 那个窗口的紧后面。
    """
    if user32.IsIconic(hwnd) or user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE：最大化 / 最小化的窗口先还原
    outer = _rect(hwnd)
    fl, ft, fr, fb = _frame(hwnd)
    left, top = fl - outer.left, ft - outer.top
    right, bottom = outer.right - fr, outer.bottom - fb
    flags |= 0x0010 | (0 if behind else 0x0004)  # SWP_NOACTIVATE，不排次序时加 SWP_NOZORDER
    user32.SetWindowPos(hwnd, behind or None, x - left, y - top, w + left + right, h + top + bottom, flags)


def is_alive(hwnd: int) -> bool:
    """窗口还在不在（Claude 被关掉后句柄就失效了）。"""
    return bool(IS_WIN and hwnd and user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))


def frame_width(hwnd: int) -> int:
    """窗口可见边框的宽度（物理像素）。"""
    if not IS_WIN or not hwnd:
        return 0
    l, _t, r, _b = _frame(hwnd)
    return r - l


def make_room(own_hwnd: int, ratio: float, min_other: int = 0, side: str = "right") -> bool:
    """开始贴靠前，保证自己右边（side="left" 时是左边）留得出对方的位置（自己宽度 × ratio，且不小于 min_other）：
    先尽量只往另一边挪；挪到屏幕边上还不够，再把自己缩窄。最大化的窗口会先还原。"""
    if not IS_WIN or not own_hwnd:
        return False
    if user32.IsZoomed(own_hwnd):
        user32.ShowWindow(own_hwnd, 9)
    monitor = user32.MonitorFromWindow(own_hwnd, 2)  # MONITOR_DEFAULTTONEAREST
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    wk = info.rcWork
    l, t, r, b = _frame(own_hwnd)
    w = r - l
    need = max(round(w * ratio), min_other)
    if (l - need >= wk.left) if side == "left" else (r + need <= wk.right):
        return True
    total = wk.right - wk.left
    w = max(200, min(w, int(total / (1 + ratio)), total - min_other))
    need = max(round(w * ratio), min_other)
    if side == "left":  # 自己往右挪，左边空出 need
        l = min(wk.right - w, wk.left + need)
    else:
        l = max(wk.left, wk.right - w - need)
    _place(own_hwnd, l, t, w, b - t)
    return True


def dock_right(own_hwnd: int, other_hwnd: int, ratio: float, restore: bool = False, hratio: float = 1.0,
               side: str = "right", min_other: int = 0) -> bool:
    """把另一个窗口贴在自己窗口的右边（side="left" 时贴在左边）：顶部对齐，宽度是自己的 ratio 倍，高度是自己的 hratio 倍。

    min_other 是已经量到的对方的最小宽度（物理像素）。贴左边时对方的右边要对齐自己的左边，位置得按它实际的
    宽度来算；它比要求的宽（被自己的最小宽度顶住）时，不告诉这里就会盖住自己的左边一截。

    对方有自己的最小宽度（Claude 桌面应用大约 600 逻辑像素），比它还窄的要求会被它自己顶回去。
    自己最大化 / 最小化时不动（右边没有位置）。restore=False 是跟随时用的：对方被最小化了就不去动它，
    并且异步摆放；restore=True 是开始贴靠时用的：同步摆放，返回后马上能量到对方实际的宽度。
    """
    if not IS_WIN or not own_hwnd or not other_hwnd:
        return False
    if user32.IsIconic(own_hwnd) or user32.IsZoomed(own_hwnd):
        return False
    if not restore and user32.IsIconic(other_hwnd):
        return False
    l, t, r, b = _frame(own_hwnd)
    # SWP_ASYNCWINDOWPOS：对方窗口卡住时不拖住自己
    w = max(1, round((r - l) * ratio), min_other)
    _place(other_hwnd, l - w if side == "left" else r, t, w, max(1, round((b - t) * hratio)), behind=own_hwnd,
           flags=0 if restore else 0x4000)
    return True


def activate(hwnd: int) -> bool:
    """把窗口切到前台。"""
    if not IS_WIN or not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    return bool(user32.SetForegroundWindow(hwnd))


# ---------------------------------------------------------------------- 把键盘焦点放进对话输入框
# Claude / ChatGPT / Chrome 都是 Chromium：窗口被切到前台后，页面里的输入框不一定有键盘焦点，
# 这时发 Ctrl+V 会落空（Claude 会报"图片处理失败"），用户得先用鼠标点一下输入框。
# 这里通过 UI Automation 找到页面里的输入框并让它获得焦点，相当于替用户点那一下。
# 直接按 COM 接口的虚表序号调用（序号来自 UIAutomationClient.h，是固定的 ABI），不依赖第三方库。
_UIA_EDIT, _UIA_DOCUMENT = 50004, 50030          # ControlType
_UIA_CONTROLTYPE_PROP = 30003
_SCOPE_DESCENDANTS = 4

if IS_WIN:
    class _GUID(ctypes.Structure):
        _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

        def __init__(self, text):
            super().__init__()
            ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(self))

    class _VARIANT(ctypes.Structure):  # 只用到 VT_I4
        _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort), ("r2", ctypes.c_ushort),
                    ("r3", ctypes.c_ushort), ("lVal", ctypes.c_long), ("pad", ctypes.c_void_p)]

    def _com(index, *argtypes):
        """COM 对象虚表里第 index 个方法（返回 HRESULT，失败时抛 OSError）。"""
        return ctypes.WINFUNCTYPE(ctypes.HRESULT, *argtypes)(index, "m")

    _P = ctypes.POINTER
    _release = ctypes.WINFUNCTYPE(ctypes.c_ulong)(2, "Release")
    _uia_from_handle = _com(6, wintypes.HWND, _P(ctypes.c_void_p))                 # IUIAutomation::ElementFromHandle
    _uia_prop_cond = _com(23, ctypes.c_int, _VARIANT, _P(ctypes.c_void_p))         # ::CreatePropertyCondition
    _el_set_focus = _com(3)                                                        # IUIAutomationElement::SetFocus
    _el_find_all = _com(6, ctypes.c_int, ctypes.c_void_p, _P(ctypes.c_void_p))     # ::FindAll
    _el_focusable = _com(27, _P(wintypes.BOOL))                                    # ::get_CurrentIsKeyboardFocusable
    _el_offscreen = _com(38, _P(wintypes.BOOL))                                    # ::get_CurrentIsOffscreen
    _el_rect = _com(43, _P(RECT))                                                  # ::get_CurrentBoundingRectangle
    _arr_length = _com(3, _P(ctypes.c_int))                                        # IUIAutomationElementArray::get_Length
    _arr_get = _com(4, ctypes.c_int, _P(ctypes.c_void_p))                          # ::GetElement

_uia = None  # IUIAutomation，第一次用到时创建


def _automation():
    global _uia
    if _uia is None:
        ole32 = ctypes.oledll.ole32
        try:
            ole32.CoInitialize(None)  # Qt 一般已经初始化过；重复调用无害
        except OSError:
            pass
        obj = ctypes.c_void_p()
        ole32.CoCreateInstance(ctypes.byref(_GUID("{ff48dba4-60ef-4201-aa87-54103eef594e}")), None, 1,  # CUIAutomation
                               ctypes.byref(_GUID("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")), ctypes.byref(obj))
        _uia = obj
    return _uia


def _find_input(hwnd: int):
    """窗口网页内容里最靠下的那个可聚焦输入框：(元素指针, (左, 上, 右, 下))；找不到返回 (None, None)。
    调用方负责 _release 返回的元素。只在网页文档里找，所以不会选中浏览器的地址栏。"""
    uia = _automation()
    held = []  # 用完要释放的 COM 对象

    def cond(control_type):
        c = ctypes.c_void_p()
        _uia_prop_cond(uia, _UIA_CONTROLTYPE_PROP, _VARIANT(vt=3, lVal=control_type), ctypes.byref(c))
        held.append(c)
        return c

    try:
        root = ctypes.c_void_p()
        _uia_from_handle(uia, hwnd, ctypes.byref(root))
        held.append(root)
        def children(start, control_type):
            arr = ctypes.c_void_p()
            _el_find_all(start, _SCOPE_DESCENDANTS, cond(control_type), ctypes.byref(arr))
            if not arr:
                return
            held.append(arr)
            n = ctypes.c_int()
            _arr_length(arr, ctypes.byref(n))
            for i in range(n.value):
                el = ctypes.c_void_p()
                _arr_get(arr, i, ctypes.byref(el))
                yield el

        # 一个窗口里可能有不止一个网页文档（Claude 桌面应用就有两个），每个都找。
        # 文档一个都没有时：Chromium 的无障碍树是第一次被问到才开始建的，调用方稍后再试。
        best, best_rect = None, None
        for doc in children(root, _UIA_DOCUMENT):
            held.append(doc)
            for el in children(doc, _UIA_EDIT):
                ok, off, r = wintypes.BOOL(), wintypes.BOOL(), RECT()
                _el_focusable(el, ctypes.byref(ok))
                _el_offscreen(el, ctypes.byref(off))
                _el_rect(el, ctypes.byref(r))
                if ok.value and not off.value and r.right > r.left and (best is None or r.bottom > best_rect[3]):
                    if best is not None:
                        _release(best)
                    best, best_rect = el, (r.left, r.top, r.right, r.bottom)
                else:
                    _release(el)
        return best, best_rect
    finally:
        for obj in held:
            _release(obj)


def focus_input(hwnd: int) -> bool:
    """把键盘焦点放进窗口里的对话输入框。成功返回 True；没找到输入框（或不是 Windows、出了任何错）返回 False。"""
    if not IS_WIN or not hwnd:
        return False
    try:
        el, _rect = _find_input(hwnd)
        if el is None:
            return False
        try:
            _el_set_focus(el)
        finally:
            _release(el)
        return True
    except Exception:
        return False


def send_paste():
    """向当前前台窗口发送 Ctrl+V。"""
    if not IS_WIN:
        return
    KEYUP = 0x0002
    user32.keybd_event(0x11, 0, 0, None)       # Ctrl 按下
    user32.keybd_event(0x56, 0, 0, None)       # V 按下
    user32.keybd_event(0x56, 0, KEYUP, None)   # V 抬起
    user32.keybd_event(0x11, 0, KEYUP, None)   # Ctrl 抬起
