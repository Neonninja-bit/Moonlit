import ctypes
import ctypes.wintypes
import time
import io
from datetime import datetime

import win32clipboard
import win32con
import win32api
from PIL import Image

from PyQt6.QtCore import QThread, pyqtSignal, QTimer

# Windows constants
MOD_CTRL     = 0x0002
MOD_SHIFT    = 0x0004
MOD_NOREPEAT = 0x4000
user32       = ctypes.windll.user32

class HotkeyThread(QThread):
    triggered = pyqtSignal()

    def __init__(self, hk_id=102):
        super().__init__()
        self.hk_id    = hk_id
        self._running = True

    def run(self):
        registered = False
        try:
            rc = user32.RegisterHotKey(None, self.hk_id,
                                       MOD_CTRL | MOD_SHIFT | MOD_NOREPEAT, 0x51)
            if rc:
                registered = True
            else:
                err = ctypes.GetLastError()
                print(f"[HotkeyThread] RegisterHotKey failed, err={err}")

            msg = ctypes.wintypes.MSG()
            while self._running:
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312 and msg.wParam == self.hk_id:
                        self.triggered.emit()
                time.sleep(0.02)
        finally:
            if registered:
                try:
                    user32.UnregisterHotKey(None, self.hk_id)
                except Exception:
                    pass

    def stop(self):
        self._running = False

class ClipboardWatcher(QThread):
    new_item = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._running  = True
        self._last_seq = win32clipboard.GetClipboardSequenceNumber()

    def run(self):
        while self._running:
            time.sleep(0.4)
            try:
                seq = win32clipboard.GetClipboardSequenceNumber()
                if seq != self._last_seq:
                    self._last_seq = seq
                    item = self._read()
                    if item:
                        self.new_item.emit(item)
            except Exception:
                pass

    def _read(self):
        item = {"ts": datetime.now()}
        try:
            win32clipboard.OpenClipboard()
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
                data = win32clipboard.GetClipboardData(win32con.CF_DIB)
                win32clipboard.CloseClipboard()
                try:
                    img = Image.open(io.BytesIO(data))
                except Exception:
                    import struct
                    hdr = struct.pack('<2sIHHI', b'BM', len(data) + 14, 0, 0, 14)
                    img = Image.open(io.BytesIO(hdr + data))
                item.update(type="image", image=img.copy(),
                            label=f"Image  {img.width}×{img.height}")
                return item
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                win32clipboard.CloseClipboard()
                if text and text.strip():
                    item.update(type="text", text=text,
                                label=text[:120].replace("\n", " "))
                    return item
            win32clipboard.CloseClipboard()
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass
        return None

    def stop(self):
        self._running = False

# Paste helpers
def _send_paste():
    win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
    win32api.keybd_event(ord('V'), 0, 0, 0)
    win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

def paste_text(text: str):
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()
    except Exception:
        pass
    QTimer.singleShot(120, _send_paste)

def paste_image(img: Image.Image):
    output = io.BytesIO()
    img.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, data)
        win32clipboard.CloseClipboard()
    except Exception:
        pass
    QTimer.singleShot(120, _send_paste)