from types import SimpleNamespace

import pytest

from echoflow import transcriber
from tests.conftest import FakeClient


def test_transcribe_runs_verbatim_asr_then_cleanup():
    client = FakeClient("कल meeting है", "Kal meeting hai.")
    assert transcriber.transcribe(client, b"wav", ["Dashtoon"], app_name="Slack") == "Kal meeting hai."

    asr, cleanup = client.calls
    assert asr.model == transcriber.TRANSCRIBE_MODEL
    cfg = asr.config.audio_transcription_config
    assert cfg.mode.value == "VERBATIM"  # SMART mode silently ignores custom vocabulary
    assert cfg.language_codes == ["hi-IN", "en-IN"]
    assert cfg.custom_vocabulary == ["Dashtoon"]

    assert cleanup.model == transcriber.CLEANUP_MODEL
    assert "कल meeting है" in cleanup.contents
    assert "Dashtoon" in cleanup.config.system_instruction
    assert "Slack" in cleanup.config.system_instruction


def test_transcribe_skips_cleanup_when_nothing_was_heard():
    client = FakeClient("")
    assert transcriber.transcribe(client, b"wav", []) == ""
    assert len(client.calls) == 1


def test_transcribe_falls_back_to_raw_text_when_cleanup_fails():
    client = FakeClient("raw words", RuntimeError("503"))
    assert transcriber.transcribe(client, b"wav", []) == "raw words"


def test_devanagari_left_by_cleanup_is_retried_with_stronger_model():
    client = FakeClient("Kubernetes में pods crash", "Kubernetes में pods crash", "Kubernetes mein pods crash.")
    assert transcriber.transcribe(client, b"wav", []) == "Kubernetes mein pods crash."
    assert client.calls[2].model == transcriber.RETRY_MODEL


def test_cleanup_prompt_demands_roman_script_for_mixed_input():
    client = FakeClient("pods बार-बार crash", "Pods baar baar crash.")
    transcriber.transcribe(client, b"wav", [])
    assert "Roman" in client.calls[1].contents and "pods बार-बार crash" in client.calls[1].contents


def test_transcribe_raises_when_asr_fails():
    with pytest.raises(RuntimeError):
        transcriber.transcribe(FakeClient(RuntimeError("401")), b"wav", [])


def test_empty_vocab_is_not_sent_to_asr():
    client = FakeClient("")
    transcriber.transcribe(client, b"wav", [])
    assert client.calls[0].config.audio_transcription_config.custom_vocabulary is None


def test_vocab_is_capped_at_the_model_limit():
    client = FakeClient("")
    transcriber.transcribe(client, b"wav", [f"term{i}" for i in range(1500)])
    assert len(client.calls[0].config.audio_transcription_config.custom_vocabulary) == 1000


def test_instructions_without_vocab_or_app_have_only_the_rules():
    assert transcriber.build_instructions([]) == transcriber.STYLE_RULES


def test_text_ignores_thought_parts():
    thought = SimpleNamespace(text="thinking...", thought=True, audio_transcription=None)
    answer = SimpleNamespace(text="Final.", thought=False, audio_transcription=None)
    resp = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[thought, answer]))])
    assert transcriber._text(resp) == "Final."
