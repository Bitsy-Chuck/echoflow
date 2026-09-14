"""Floating record button: click to start, click again to write.

A non-activating panel, so clicking it never takes focus away from the app you are
typing into - otherwise the text would be pasted into this window instead.
The view polls App.state on the main thread; background threads never touch the UI.
"""

import json
import logging
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSMakeSize,
    NSPanel,
    NSScreen,
    NSString,
    NSTimer,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from PyObjCTools import AppHelper

log = logging.getLogger("echoflow")

POSITION_FILE = Path.home() / ".echoflow" / "button.json"
WIDTH, HEIGHT = 132.0, 46.0
MARGIN = 24.0
REFRESH_SECONDS = 0.2
DRAG_THRESHOLD = 3.0  # points of movement before a click becomes a drag

LOOKS = {  # state -> (background, label)
    "idle": ((0.16, 0.17, 0.20, 0.96), "Speak"),
    "recording": ((0.80, 0.18, 0.20, 0.97), "Stop {seconds}s"),
    "working": ((0.20, 0.32, 0.55, 0.97), "Writing..."),
}


class RecordButtonView(NSView):
    def initWithApp_(self, app):
        # Reassigning self is the PyObjC initializer idiom: the superclass may return another instance.
        self = objc.super(RecordButtonView, self).initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))  # noqa: PLW0642
        self.app = app
        self.press_origin = None
        self.dragging = False
        return self

    def drawRect_(self, rect):
        state = self.app.state
        colour, template = LOOKS.get(state, LOOKS["idle"])
        NSColor.colorWithCalibratedRed_green_blue_alpha_(*colour).set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(self.bounds(), 12.0, 12.0).fill()

        label = ("● " if state == "recording" else "\U0001f399 ") + template.format(
            seconds=self.app.recording_seconds())
        attributes = {
            NSFontAttributeName: NSFont.systemFontOfSize_(14.0),
            NSForegroundColorAttributeName: NSColor.whiteColor(),
        }
        text = NSString.stringWithString_(label)
        size = text.sizeWithAttributes_(attributes)
        text.drawAtPoint_withAttributes_(
            ((self.bounds().size.width - size.width) / 2, (self.bounds().size.height - size.height) / 2),
            attributes)

    # A click toggles recording; a drag moves the window instead.
    def mouseDown_(self, event):
        self.press_origin = event.locationInWindow()
        self.dragging = False

    def mouseDragged_(self, event):
        if self.dragging or self.press_origin is None:
            return
        moved = event.locationInWindow()
        if abs(moved.x - self.press_origin.x) > DRAG_THRESHOLD or abs(moved.y - self.press_origin.y) > DRAG_THRESHOLD:
            self.dragging = True
            self.window().performWindowDragWithEvent_(event)

    def mouseUp_(self, event):
        if not self.dragging:
            self.app.toggle()
            self.setNeedsDisplay_(True)
        self.press_origin = None

    def refresh_(self, timer):
        self.setNeedsDisplay_(True)


def _saved_origin():
    try:
        saved = json.loads(POSITION_FILE.read_text())
        return float(saved["x"]), float(saved["y"])
    except (OSError, ValueError, KeyError):
        frame = NSScreen.mainScreen().visibleFrame()
        return frame.origin.x + frame.size.width - WIDTH - MARGIN, frame.origin.y + MARGIN


def save_position(panel):
    origin = panel.frame().origin
    POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
    POSITION_FILE.write_text(json.dumps({"x": origin.x, "y": origin.y}))


def make_panel(app):
    x, y = _saved_origin()
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(x, y, WIDTH, HEIGHT),
        NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
        NSBackingStoreBuffered, False)
    panel.setLevel_(3)  # NSFloatingWindowLevel: above normal windows
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(True)
    panel.setHidesOnDeactivate_(False)
    panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                 | NSWindowCollectionBehaviorFullScreenAuxiliary
                                 | NSWindowCollectionBehaviorStationary)
    panel.setContentSize_(NSMakeSize(WIDTH, HEIGHT))
    panel.setContentView_(RecordButtonView.alloc().initWithApp_(app))
    panel.orderFrontRegardless()
    return panel


def run(app):
    """Show the button and run the AppKit event loop until interrupted."""
    ns_app = NSApplication.sharedApplication()
    ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon, never steals focus
    panel = make_panel(app)
    view = panel.contentView()
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        REFRESH_SECONDS, view, "refresh:", None, True)
    try:
        AppHelper.runEventLoop(installInterrupt=True)
    finally:
        timer.invalidate()
        save_position(panel)
