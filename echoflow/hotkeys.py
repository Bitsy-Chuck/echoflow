"""Hold-to-talk hotkey logic, independent of any keyboard library.

Keys are any hashable values; the app passes normalized pynput keys.
"""

from enum import Enum, auto


class Action(Enum):
    START = auto()      # trigger fully held: start recording
    STOP = auto()       # trigger released: transcribe what was recorded
    CANCEL = auto()     # another key pressed during the hold: it was a shortcut, discard
    ADD_VOCAB = auto()  # vocab key pressed during the hold: discard and add the selection


class _State(Enum):
    IDLE = auto()
    RECORDING = auto()
    CANCELLED = auto()  # wait for the trigger to be released before arming again


class HoldToTalk:
    def __init__(self, trigger: set, vocab_key):
        self.trigger = frozenset(trigger)
        self.vocab_key = vocab_key
        self.pressed: set = set()
        self.state = _State.IDLE

    def press(self, key) -> Action | None:
        self.pressed.add(key)
        if self.state is _State.IDLE and self.trigger <= self.pressed:
            self.state = _State.RECORDING
            return Action.START
        if self.state is _State.RECORDING and key not in self.trigger:
            self.state = _State.CANCELLED
            return Action.ADD_VOCAB if key == self.vocab_key else Action.CANCEL
        return None

    def release(self, key) -> Action | None:
        self.pressed.discard(key)
        if self.state is not _State.IDLE and not self.trigger <= self.pressed:
            was_recording = self.state is _State.RECORDING
            self.state = _State.IDLE
            return Action.STOP if was_recording else None
        return None
