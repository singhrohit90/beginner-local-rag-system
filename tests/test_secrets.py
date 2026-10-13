import os

from rag.common.secrets import load_env


def load(tmp_path, monkeypatch, text, names):
    for name in names:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    load_env(path)
    return {name: os.environ.get(name) for name in names}


def test_an_inline_comment_is_not_part_of_the_value(tmp_path, monkeypatch):
    got = load(tmp_path, monkeypatch,
               "T_BUDGET=3000   # extra tokens\nT_EFFORT=low # lower is faster\nT_KEY=\n",
               ["T_BUDGET", "T_EFFORT", "T_KEY"])
    assert got == {"T_BUDGET": "3000", "T_EFFORT": "low", "T_KEY": ""}


def test_quoted_values_and_hashes_inside_values_are_kept(tmp_path, monkeypatch):
    got = load(tmp_path, monkeypatch,
               'T_A="has # inside"  # comment\nT_B=abc#def\nT_C=\'single\'\n',
               ["T_A", "T_B", "T_C"])
    assert got == {"T_A": "has # inside", "T_B": "abc#def", "T_C": "single"}


def test_an_existing_variable_is_not_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("T_SET", "from-shell")
    (tmp_path / ".env").write_text("T_SET=from-file\n", encoding="utf-8")
    load_env(tmp_path / ".env")
    assert os.environ["T_SET"] == "from-shell"
