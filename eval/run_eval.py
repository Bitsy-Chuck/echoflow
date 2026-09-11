#!/usr/bin/env python3
"""Compare transcription pipelines on eval/cases.json + eval/audio/*.wav.

Metrics per pipeline:
- WER: word error rate vs the expected text, lenient to Hinglish spelling variants
  (hai/hain, toh/to, kyunki/kyonki) and ignoring case and punctuation.
- vocab: share of vocabulary terms in the expected text that appear spelled exactly.
- deva: number of outputs containing Devanagari (should be 0).
- latency: seconds from audio-ready to final text (median / max).

    venv/bin/python eval/run_eval.py                  # all pipelines
    venv/bin/python eval/run_eval.py echoflow         # just one
"""

import json
import re
import statistics
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from google.genai.errors import APIError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from echoflow import transcriber as t
from echoflow.gcp import make_client

EVAL_DIR = Path(__file__).resolve().parent

PIPELINES = {
    "echoflow": lambda c, wav, v: t.transcribe(c, wav, v),  # what the app runs
    "echoflow+app-context": lambda c, wav, v: t.transcribe(c, wav, v, app_name="Slack"),
    "transcribe-only": lambda c, wav, v: t.transcribe_verbatim(c, wav, v),
    "direct-3.8-flash": lambda c, wav, v: t.transcribe_direct(c, wav, v, "gemini-3.8-flash", "LOW"),
    "direct-3.1-pro": lambda c, wav, v: t.transcribe_direct(c, wav, v, "gemini-3.1-pro-preview", "LOW"),
}

DEVANAGARI = t.DEVANAGARI


def normalize_word(word: str) -> str:
    word = word.lower()
    for long, short in (("aa", "a"), ("ee", "i"), ("oo", "u"), ("w", "v")):
        word = word.replace(long, short)
    word = re.sub(r"ein$", "e", word)  # mein -> me, hamein -> hame, dein -> de
    word = re.sub(r"^nahin$", "nahi", word)
    return re.sub(r"([aeiou])h$", r"\1", word)  # toh -> to, yeh -> ye


def words(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 50,000 -> 50000
    return [normalize_word(w) for w in re.findall(r"[\w:]+", text)]


def same(a: str, b: str) -> bool:
    return a == b or SequenceMatcher(None, a, b).ratio() >= 0.75


def wer(expected: str, actual: str) -> float:
    ref, hyp = words(expected), words(actual)
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if same(r, h) else 1))
        prev = cur
    return prev[-1] / max(len(ref), 1)


def vocab_hits(expected: str, actual: str, vocab: list[str]) -> tuple[int, int]:
    wanted = [term for term in vocab if re.search(rf"\b{re.escape(term)}\b", expected)]
    found = [term for term in wanted if re.search(rf"\b{re.escape(term)}\b", actual)]
    return len(found), len(wanted)


def main():
    data = json.loads((EVAL_DIR / "cases.json").read_text())
    vocab, cases = data["vocab"], data["cases"]
    selected = sys.argv[1:] or list(PIPELINES)
    client = make_client()
    results = {}

    for name in selected:
        rows = []
        for case in cases:
            wav = (EVAL_DIR / "audio" / f"{case['id']}.wav").read_bytes()
            start = time.perf_counter()
            try:
                output = PIPELINES[name](client, wav, vocab)
            except APIError as e:  # keep going; a failed call scores as an empty output
                output = ""
                print(f"  {name} {case['id']}: ERROR {str(e)[:150]}")
            latency = time.perf_counter() - start
            hit, total = vocab_hits(case["expected"], output, vocab)
            rows.append({"id": case["id"], "output": output, "expected": case["expected"],
                         "wer": wer(case["expected"], output), "vocab_hit": hit, "vocab_total": total,
                         "devanagari": bool(DEVANAGARI.search(output)), "latency": latency})
        results[name] = rows
        latencies = [r["latency"] for r in rows]
        print(f"{name:28s} WER {statistics.mean(r['wer'] for r in rows):6.1%}  "
              f"vocab {sum(r['vocab_hit'] for r in rows)}/{sum(r['vocab_total'] for r in rows)}  "
              f"deva {sum(r['devanagari'] for r in rows):2d}  "
              f"latency p50 {statistics.median(latencies):.2f}s max {max(latencies):.2f}s", flush=True)

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{datetime.now().astimezone():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nDetails: {out}")


if __name__ == "__main__":
    main()
