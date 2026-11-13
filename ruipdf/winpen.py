"""关闭 Windows 对笔的视觉反馈（笔尖点下时的小圆圈、长按出现的圆环、笔势等），只对本窗口生效。"""
import sys


def disable_pen_feedback(hwnd: int):
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    try:
        # 长按右键(0x1) | 点按反馈(0x8) | 侧键反馈(0x10) | 笔势(0x10000)
        user32.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
        user32.SetPropW.restype = wintypes.BOOL
        user32.SetPropW(hwnd, "MicrosoftTabletPenServiceProperty", 0x1 | 0x8 | 0x10 | 0x10000)
    except Exception:
        pass
    try:
        fn = user32.SetWindowFeedbackSetting  # Windows 8 及以上
        fn.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.DWORD, ctypes.c_uint32, ctypes.c_void_p]
        fn.restype = wintypes.BOOL
        off = wintypes.BOOL(False)
        # 2 侧键 3 点按 4 双击 5 长按 6 右键点按 11 长按手势
        for feedback in (2, 3, 4, 5, 6, 11):
            fn(hwnd, feedback, 0, ctypes.sizeof(off), ctypes.byref(off))
    except Exception:
        pass
