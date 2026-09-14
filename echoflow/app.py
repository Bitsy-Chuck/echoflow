"""EchoFlow: hold Left Ctrl + Left Shift, speak Hinglish, release -> clean text at the cursor.

Left Ctrl + Left Shift + D adds the selected text to your vocabulary.
"""

import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from google.auth.exceptions import GoogleAuthError
from google.genai.errors import APIError
from pynput import keyboard

from echoflow import audio, button, macos, transcriber, vocab
from echoflow.gcp import make_client
from echoflow.hotkeys import Action, HoldToTalk

log = logging.getLogger("echoflow")

TRIGGER = {keyboard.Key.ctrl_l, keyboard.Key.shift_l}
VOCAB_KEY = ("vk", 2)  # D
START_SOUND_DELAY = 0.2  # a Ctrl+Shift shortcut is cancelled before this, so it stays silent
EXPECTED_FAILURES = (APIError, httpx.HTTPError, GoogleAuthError)  # quota, outage, offline, auth


def normalize(key):
    # With Ctrl held, pynput reports D as '\x04'; the virtual key code is stable.
    return ("vk", key.vk) if isinstance(key, keyboard.KeyCode) else key


class App:
    def __init__(self, client, recorder: audio.Recorder, vocab_path=vocab.DEFAULT_PATH):
        self.client = client
        self.recorder = recorder
        self.vocab_path = vocab_path
        self.hotkeys = HoldToTalk(trigger=TRIGGER, vocab_key=VOCAB_KEY)
        self.worker = ThreadPoolExecutor(max_workers=1)  # one job at a time keeps pastes in order
        self.start_sound = None
        self.state = "idle"  # idle | recording | working; the floating button renders this
        self.source = None   # which trigger owns the current recording: hotkey or button
        self.started_at = None

    def _begin(self, source):
        self.recorder.start()
        self.state, self.source, self.started_at = "recording", source, time.monotonic()
        if source == "hotkey":  # delayed, so plain Ctrl+Shift shortcuts stay silent
            self.start_sound = threading.Timer(START_SOUND_DELAY, macos.play_sound, ["Tink"])
            self.start_sound.start()
        else:
            macos.play_sound("Tink")

    def _end(self):
        if self.start_sound:
            self.start_sound.cancel()
        samples = self.recorder.stop()
        self.state, self.source, self.started_at = "idle", None, None
        return samples

    def recording_seconds(self) -> int:
        return int(time.monotonic() - self.started_at) if self.started_at else 0

    def toggle(self):
        """Floating button click: start recording, or finish the recording it started."""
        if self.state == "idle":
            self._begin("button")
        elif self.source == "button":
            samples = self._end()
            self.state = "working"
            self._submit(self.dictate, samples)

    # Listener callbacks: keep them fast, slow work goes to the worker.
    def on_press(self, key):
        action = self.hotkeys.press(normalize(key))
        if action is Action.START and self.state == "idle":
            self._begin("hotkey")
        elif action in (Action.CANCEL, Action.ADD_VOCAB):
            if self.source == "hotkey":
                self._end()
            if action is Action.ADD_VOCAB:
                self._submit(self.add_vocab)

    def on_release(self, key):
        if self.hotkeys.release(normalize(key)) is Action.STOP and self.source == "hotkey":
            samples = self._end()
            self.state = "working"
            self._submit(self.dictate, samples)

    def _submit(self, fn, *args):
        def run():
            try:
                fn(*args)
            except Exception:
                log.exception("Unexpected error")
                macos.play_sound("Basso")
        self.worker.submit(run)

    def dictate(self, samples):
        try:
            if not audio.has_speech(samples):
                log.info("(nothing heard)")
                return
            started = time.perf_counter()
            try:
                text = transcriber.transcribe(self.client, audio.to_wav(samples),
                                              vocab.load(self.vocab_path), macos.frontmost_app())
            except EXPECTED_FAILURES as e:
                log.error("Transcription failed: %s", e)
                macos.play_sound("Basso")
                return
            if not text:
                log.info("(no speech recognized)")
                return
            macos.paste(text)
            macos.play_sound("Glass")
            log.info("[%.1fs audio, %.1fs] %s", len(samples) / audio.SAMPLE_RATE,
                     time.perf_counter() - started, text)
        finally:
            self.state = "idle"

    def add_vocab(self):
        text = macos.copy_selection()
        if not text:
            log.info("Vocab: select a word first, then press Left Ctrl + Left Shift + D")
            macos.play_sound("Basso")
            return
        try:
            added = vocab.add(self.vocab_path, text)
        except ValueError as e:
            log.info("Vocab: %s", e)
            macos.play_sound("Basso")
            return
        log.info("Vocab: %s %r", "added" if added else "already has", " ".join(text.split()))
        macos.play_sound("Pop")


def main():
    logging.basicConfig(level=logging.WARNING, format="%(message)s")  # third-party INFO is noise
    log.setLevel(logging.INFO)
    if not macos.has_accessibility_permission():
        sys.exit("EchoFlow needs Accessibility permission to read the hotkey and paste.\n"
                 "System Settings > Privacy & Security > Accessibility: enable your terminal app, "
                 "then restart it and run EchoFlow again.")

    client = make_client()
    transcriber.warm_up(client)
    with audio.Recorder() as recorder:
        app = App(client, recorder)
        with keyboard.Listener(on_press=app.on_press, on_release=app.on_release) as listener:
            listener.wait()  # only announce "ready" once keys and microphone are really live
            log.info("EchoFlow ready - %s -> %s", transcriber.TRANSCRIBE_MODEL, transcriber.CLEANUP_MODEL)
            log.info("Click the floating button, or hold Left Ctrl + Left Shift, to talk.")
            log.info("Select text + Left Ctrl + Left Shift + D adds it to your vocabulary.")
            log.info("Vocabulary: %s (%d terms). Ctrl+C to quit.\n", vocab.DEFAULT_PATH, len(vocab.load()))
            button.run(app)  # AppKit needs the main thread; the key listener runs in its own
