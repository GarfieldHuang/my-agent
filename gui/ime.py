"""Windows IME 協助：偵測與強制 commit 組字（preedit）。

Tk 在 Windows 上遇到輸入法切換（Shift、Ctrl+Space 等）時，會直接丟棄
還沒 commit 的組字內容。這裡用 imm32 API 在切換前強制 commit，
行為就跟一般輸入框一樣。非 Windows 平台皆為 no-op。
"""
import sys

GCS_COMPSTR       = 0x0008
NI_COMPOSITIONSTR = 0x0015
CPS_COMPLETE      = 0x0001

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _imm32  = ctypes.windll.imm32

    _user32.GetFocus.restype = wintypes.HWND
    _imm32.ImmGetContext.argtypes = [wintypes.HWND]
    _imm32.ImmGetContext.restype = ctypes.c_void_p
    _imm32.ImmReleaseContext.argtypes = [wintypes.HWND, ctypes.c_void_p]
    _imm32.ImmGetCompositionStringW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _imm32.ImmNotifyIME.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]

    def has_composition() -> bool:
        """目前焦點視窗是否有未 commit 的組字。"""
        hwnd = _user32.GetFocus()
        if not hwnd:
            return False
        himc = _imm32.ImmGetContext(hwnd)
        if not himc:
            return False
        try:
            return _imm32.ImmGetCompositionStringW(himc, GCS_COMPSTR, None, 0) > 0
        finally:
            _imm32.ImmReleaseContext(hwnd, himc)

    def commit_composition() -> None:
        """把未 commit 的組字直接送進輸入框（模擬一般輸入框行為）。"""
        hwnd = _user32.GetFocus()
        if not hwnd:
            return
        himc = _imm32.ImmGetContext(hwnd)
        if not himc:
            return
        try:
            _imm32.ImmNotifyIME(himc, NI_COMPOSITIONSTR, CPS_COMPLETE, 0)
        finally:
            _imm32.ImmReleaseContext(hwnd, himc)

else:
    def has_composition() -> bool:
        return False

    def commit_composition() -> None:
        pass
