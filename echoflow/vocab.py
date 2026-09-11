"""Personal vocabulary: names and terms the transcriber should spell exactly.

Plain text file, one term per line, lines starting with # are comments.
"""

from pathlib import Path

DEFAULT_PATH = Path.home() / ".echoflow" / "vocab.txt"
MAX_TERM_LENGTH = 60  # longer selections are almost certainly accidental


def load(path: Path = DEFAULT_PATH) -> list[str]:
    if not path.exists():
        return []
    terms, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        term = line.strip()
        if term and not term.startswith("#") and term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)
    return terms


def add(path: Path, term: str) -> bool:
    """Append term to the vocabulary. Returns False if it is already there."""
    if "\n" in term or "\r" in term:
        raise ValueError("Vocabulary terms must be a single line")
    term = " ".join(term.split())
    if not term:
        raise ValueError("Vocabulary term is empty")
    if len(term) > MAX_TERM_LENGTH:
        raise ValueError(f"Vocabulary term is longer than {MAX_TERM_LENGTH} characters")
    if term.lower() in {t.lower() for t in load(path)}:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    separator = "" if not existing or existing.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{separator}{term}\n")
    return True
