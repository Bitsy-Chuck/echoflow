"""macOS integration: permissions, frontmost app, clipboard, synthetic Cmd+V / Cmd+C, sounds."""

import subprocess
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString
from ApplicationServices import AXIsProcessTrusted

KEY_C, KEY_V = 8, 9  # macOS virtual key codes
MODIFIER_MASK = (Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskShift
                 | Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskAlternate)
PASTE_SETTLE_SECONDS = 0.3  # time for the target app to read the clipboard before we restore it


def has_accessibility_permission() -> bool:
    return bool(AXIsProcessTrusted())


def frontmost_app() -> str | None:
    """Owner of the frontmost normal window. Queries the window server directly because
    NSWorkspace.frontmostApplication goes stale in processes without a Cocoa run loop."""
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID) or []
    for window in windows:
        if window.get("kCGWindowLayer") == 0 and window.get("kCGWindowAlpha", 1) > 0:
            return window.get("kCGWindowOwnerName")
    return None


def wait_for_modifiers_released(timeout: float = 2.0):
    """Synthetic Cmd+V while the user still holds Ctrl or Shift would arrive as Cmd+Ctrl+V."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not Quartz.CGEventSourceFlagsState(Quartz.kCGEventSourceStateHIDSystemState) & MODIFIER_MASK:
            return
        time.sleep(0.02)


def _press_cmd(key_code: int):
    for down in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(None, key_code, down)
        Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


class ClipboardSnapshot:
    """Every item and type on the general pasteboard, so text, images and files all survive."""

    def __init__(self):
        self.pasteboard = NSPasteboard.generalPasteboard()
        self.items = [
            [(t, item.dataForType_(t)) for t in item.types()]
            for item in (self.pasteboard.pasteboardItems() or [])
        ]

    def restore(self):
        self.pasteboard.clearContents()
        restored = []
        for saved in self.items:
            item = NSPasteboardItem.alloc().init()
            for pasteboard_type, data in saved:
                if data is not None:
                    item.setData_forType_(data, pasteboard_type)
            restored.append(item)
        if restored:
            self.pasteboard.writeObjects_(restored)


def paste(text: str):
    """Paste text at the cursor via the clipboard, then put the user's clipboard back."""
    wait_for_modifiers_released()
    snapshot = ClipboardSnapshot()
    pasteboard = snapshot.pasteboard
    pasteboard.clearContents()
    pasteboard.setString_forType_(text, NSPasteboardTypeString)
    ours = pasteboard.changeCount()
    _press_cmd(KEY_V)
    time.sleep(PASTE_SETTLE_SECONDS)
    if pasteboard.changeCount() == ours:  # don't clobber something the user copied meanwhile
        snapshot.restore()


def copy_selection(timeout: float = 0.5) -> str | None:
    """Currently selected text in the frontmost app, leaving the clipboard as it was."""
    wait_for_modifiers_released()
    snapshot = ClipboardSnapshot()
    pasteboard = snapshot.pasteboard
    before = pasteboard.changeCount()
    _press_cmd(KEY_C)
    deadline = time.monotonic() + timeout
    while pasteboard.changeCount() == before and time.monotonic() < deadline:
        time.sleep(0.02)
    text = pasteboard.stringForType_(NSPasteboardTypeString) if pasteboard.changeCount() != before else None
    snapshot.restore()
    return text


def play_sound(name: str):
    subprocess.Popen(["afplay", f"/System/Library/Sounds/{name}.aiff"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
