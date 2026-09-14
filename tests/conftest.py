"""Shared fakes and fixtures: no network, no microphone, no real key or clipboard events."""

from types import SimpleNamespace

import numpy as np
import pytest

from echoflow import app as app_module
from echoflow import audio

SPEECH = (0.1 * np.sin(np.arange(audio.SAMPLE_RATE) * 0.1)).astype(np.float32)  # 1s, clearly audible
SILENCE = np.zeros(audio.SAMPLE_RATE, dtype=np.float32)


def response(text: str):
    part = SimpleNamespace(text=text, thought=False, audio_transcription=None)
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


class FakeClient:
    """Records generate_content calls; returns queued results (Exceptions are raised)."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return response(result)


class FakeRecorder:
    def __init__(self, samples):
        self.samples = samples
        self.started = 0

    def start(self):
        self.started += 1

    def stop(self):
        return self.samples


@pytest.fixture
def mac(monkeypatch):
    """Replace the macOS side effects and record them."""
    events = {"pasted": [], "sounds": [], "selection": None}
    monkeypatch.setattr(app_module.macos, "paste", events["pasted"].append)
    monkeypatch.setattr(app_module.macos, "play_sound", events["sounds"].append)
    monkeypatch.setattr(app_module.macos, "frontmost_app", lambda: "Slack")
    monkeypatch.setattr(app_module.macos, "copy_selection", lambda: events["selection"])
    return events


def make_app(tmp_path, samples, *results):
    client = FakeClient(*results)
    return app_module.App(client, FakeRecorder(samples), vocab_path=tmp_path / "vocab.txt"), client


def drain(app):
    """Wait for queued work without shutting the worker down."""
    app.worker.submit(lambda: None).result()
