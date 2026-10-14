"""UI strings (ADR 0031 stage D2): the static markup in index.html follows the same
register as js/strings.js, and run-time strings live in the table, not in modules."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from apeCAD.scratchpad.server import STATIC_DIR

INDEX = STATIC_DIR / "index.html"
# Dash pause, ellipsis outside a menu item, exclamation, question mark, verdict chips, "you".
_FORBIDDEN = re.compile(r"—|–|\.\.\.|!|\?|\bOK\b|\byou\b|\bwe\b|\bplease\b", re.IGNORECASE)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        for name, value in attrs:
            if name in ("title", "aria-label", "placeholder") and value:
                self.found.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.found.append(data.strip())


def _texts() -> list[str]:
    parser = _Text()
    parser.feed(INDEX.read_text(encoding="utf-8"))
    return parser.found


def test_index_text_follows_the_register() -> None:
    for text in _texts():
        assert not _FORBIDDEN.search(text), text
        if "…" in text:
            assert text.endswith("…"), f"ellipsis only ends a menu item that opens a dialog: {text}"


def test_index_uses_sentence_case_and_one_noun_per_concept() -> None:
    texts = _texts()
    assert "Save as…" in texts and "Save As…" not in texts
    assert not any(re.search(r"\bRect\b", text) for text in texts)
    assert not any("outliner" in text.lower() for text in texts), "say the model panel"


def test_modules_keep_no_hint_literal() -> None:
    hint_call = re.compile(r"setHint\(\s*[\"'`]")
    for path in sorted((STATIC_DIR / "js").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        assert not hint_call.search(source), f"{path.name}: hint text belongs in js/strings.js"
        assert "setHint(error.message)" not in source, f"{path.name}: use refuse(error)"
