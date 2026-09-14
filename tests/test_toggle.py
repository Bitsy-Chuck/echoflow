"""Click-to-toggle recording, used by the floating button."""

from pynput.keyboard import Key

from tests.conftest import SILENCE, SPEECH, drain, make_app


def test_first_click_records_second_click_dictates(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, "raw", "Kal milte hain.")
    assert app.state == "idle"

    app.toggle()
    assert app.state == "recording" and app.recorder.started == 1

    app.toggle()
    drain(app)
    assert mac["pasted"] == ["Kal milte hain."]
    assert app.state == "idle"


def test_state_shows_working_while_transcribing(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, "raw", "Done.")
    app.toggle()
    app.toggle()
    assert app.state == "working"
    drain(app)
    assert app.state == "idle"


def test_state_returns_to_idle_after_a_silent_recording(tmp_path, mac):
    app, client = make_app(tmp_path, SILENCE)
    app.toggle()
    app.toggle()
    drain(app)
    assert app.state == "idle" and client.calls == []


def test_state_returns_to_idle_after_an_error(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, ZeroDivisionError("bug"))
    app.toggle()
    app.toggle()
    drain(app)
    assert app.state == "idle" and mac["pasted"] == []


def test_button_click_is_ignored_while_the_hotkey_is_held(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, "raw", "Hotkey text.")
    app.on_press(Key.ctrl_l)
    app.on_press(Key.shift_l)
    app.toggle()  # stray click mid-hold must not stop the hotkey recording
    assert app.state == "recording"

    app.on_release(Key.shift_l)
    drain(app)
    assert mac["pasted"] == ["Hotkey text."]


def test_hotkey_is_ignored_while_the_button_is_recording(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, "raw", "Button text.")
    app.toggle()
    app.on_press(Key.ctrl_l)
    app.on_press(Key.shift_l)
    app.on_release(Key.shift_l)
    drain(app)
    assert mac["pasted"] == []  # still recording for the button
    assert app.state == "recording"

    app.toggle()
    drain(app)
    assert mac["pasted"] == ["Button text."]


def test_recording_seconds_counts_up_only_while_recording(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, "raw", "x")
    assert app.recording_seconds() == 0
    app.toggle()
    assert app.recording_seconds() >= 0
    app.toggle()
    drain(app)
    assert app.recording_seconds() == 0
