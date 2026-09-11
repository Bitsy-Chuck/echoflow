from echoflow.hotkeys import Action, HoldToTalk

CTRL, SHIFT, D, T, CMD = "ctrl_l", "shift_l", "d", "t", "cmd"


def machine():
    return HoldToTalk(trigger={CTRL, SHIFT}, vocab_key=D)


def test_hold_both_starts_and_releasing_either_stops():
    m = machine()
    assert m.press(CTRL) is None
    assert m.press(SHIFT) is Action.START
    assert m.release(SHIFT) is Action.STOP
    assert m.release(CTRL) is None


def test_trigger_order_does_not_matter():
    m = machine()
    m.press(SHIFT)
    assert m.press(CTRL) is Action.START


def test_other_key_during_hold_cancels_shortcut():
    m = machine()
    m.press(CTRL)
    m.press(SHIFT)
    assert m.press(T) is Action.CANCEL  # e.g. Ctrl+Shift+T is a shortcut, not dictation
    assert m.release(T) is None
    assert m.release(SHIFT) is None  # no STOP after a cancel
    assert m.release(CTRL) is None


def test_no_restart_while_trigger_still_held_after_cancel():
    m = machine()
    m.press(CTRL)
    m.press(SHIFT)
    m.press(T)
    m.release(T)
    assert m.press(T) is None


def test_vocab_key_during_hold_adds_vocab():
    m = machine()
    m.press(CTRL)
    m.press(SHIFT)
    assert m.press(D) is Action.ADD_VOCAB
    assert m.release(SHIFT) is None


def test_can_start_again_after_stop():
    m = machine()
    m.press(CTRL)
    m.press(SHIFT)
    m.release(SHIFT)
    assert m.press(SHIFT) is Action.START


def test_stale_non_trigger_key_does_not_block_start():
    m = machine()
    m.press(CMD)  # its release was never seen (e.g. lost during secure input)
    m.press(CTRL)
    assert m.press(SHIFT) is Action.START


def test_repeated_press_events_while_recording_are_ignored():
    m = machine()
    m.press(CTRL)
    m.press(SHIFT)
    assert m.press(SHIFT) is None
    assert m.release(CTRL) is Action.STOP
