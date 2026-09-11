import pytest

from echoflow import vocab


def test_load_missing_file_returns_empty(tmp_path):
    assert vocab.load(tmp_path / "nope.txt") == []


def test_load_skips_comments_blanks_and_duplicates(tmp_path):
    path = tmp_path / "vocab.txt"
    path.write_text("# my words\nDashtoon\n\n  Claude Code  \ndashtoon\nArpit\n")
    assert vocab.load(path) == ["Dashtoon", "Claude Code", "Arpit"]


def test_add_creates_file_and_parent_dir(tmp_path):
    path = tmp_path / "sub" / "vocab.txt"
    assert vocab.add(path, "Ojasv") is True
    assert vocab.load(path) == ["Ojasv"]


def test_add_is_case_insensitive_no_duplicate(tmp_path):
    path = tmp_path / "vocab.txt"
    vocab.add(path, "Supabase")
    assert vocab.add(path, "supabase") is False
    assert vocab.load(path) == ["Supabase"]


def test_add_appends_on_new_line_when_file_lacks_trailing_newline(tmp_path):
    path = tmp_path / "vocab.txt"
    path.write_text("Vertex")
    vocab.add(path, "Gemini")
    assert vocab.load(path) == ["Vertex", "Gemini"]


def test_add_collapses_whitespace(tmp_path):
    path = tmp_path / "vocab.txt"
    vocab.add(path, "  Wispr   Flow ")
    assert vocab.load(path) == ["Wispr Flow"]


@pytest.mark.parametrize("bad", ["", "   ", "two\nlines", "x" * 61])
def test_add_rejects_empty_multiline_and_long_selections(tmp_path, bad):
    with pytest.raises(ValueError):
        vocab.add(tmp_path / "vocab.txt", bad)
