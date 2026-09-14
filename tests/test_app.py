from google.genai.errors import APIError
from pynput.keyboard import Key, KeyCode

from echoflow import vocab
from tests.conftest import SILENCE, SPEECH, drain, make_app


def hold_and_release(app, *extra_keys):
    app.on_press(Key.ctrl_l)
    app.on_press(Key.shift_l)
    for key in extra_keys:
        app.on_press(key)
        app.on_release(key)
    app.on_release(Key.shift_l)
    app.on_release(Key.ctrl_l)
    drain(app)


def test_dictation_pastes_cleaned_text(tmp_path, mac):
    vocab.add(tmp_path / "vocab.txt", "Dashtoon")
    app, client = make_app(tmp_path, SPEECH, "raw", "Dashtoon ka plan ready hai.")
    hold_and_release(app)
    assert mac["pasted"] == ["Dashtoon ka plan ready hai."]
    assert client.calls[0].config.audio_transcription_config.custom_vocabulary == ["Dashtoon"]
    assert "Slack" in client.calls[1].config.system_instruction
    assert "Glass" in mac["sounds"]


def test_ctrl_shift_shortcut_is_cancelled_without_api_calls(tmp_path, mac):
    app, client = make_app(tmp_path, SPEECH)
    hold_and_release(app, KeyCode(vk=17, char="t"))
    assert mac["pasted"] == [] and client.calls == []


def test_silence_is_not_sent_to_the_api(tmp_path, mac):
    app, client = make_app(tmp_path, SILENCE)
    hold_and_release(app)
    assert mac["pasted"] == [] and client.calls == []


def test_transcription_error_plays_error_sound_and_pastes_nothing(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH, APIError(429, {"error": {"message": "quota"}}))
    hold_and_release(app)
    assert mac["pasted"] == [] and "Basso" in mac["sounds"]


def test_ctrl_shift_d_adds_selection_to_vocab(tmp_path, mac):
    mac["selection"] = "  Ojasv "
    app, client = make_app(tmp_path, SPEECH)
    hold_and_release(app, KeyCode(vk=2, char="\x04"))  # Ctrl+D arrives as a control character
    assert vocab.load(tmp_path / "vocab.txt") == ["Ojasv"]
    assert mac["pasted"] == [] and client.calls == [] and "Pop" in mac["sounds"]


def test_ctrl_shift_d_without_selection_warns(tmp_path, mac):
    app, _ = make_app(tmp_path, SPEECH)
    hold_and_release(app, KeyCode(vk=2, char="\x04"))
    assert vocab.load(tmp_path / "vocab.txt") == [] and "Basso" in mac["sounds"]


def test_unexpected_bug_is_reported_not_swallowed(tmp_path, mac, caplog):
    app, _ = make_app(tmp_path, SPEECH, ZeroDivisionError("bug"))
    hold_and_release(app)
    assert "Basso" in mac["sounds"] and "Unexpected error" in caplog.text
