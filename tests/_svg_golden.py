"""Structural comparison of an SVG with its golden (C5 record §3 "Goldens"; C5-S2, apeSection#60).

The v2 goldens are never compared as bytes or as a hash. The renderer prints numbers to two
decimals (`render/svg.py::num`), and a value the trig feeds can sit on a rounding tie
(`214.125`): one platform's last ulp prints `214.12`, the other's `214.13` (the class that
broke an exact hash in apeCAD#60). So the comparison is:

- the element tree, tags and attribute names, exactly;
- element text and tails as whitespace-split tokens, exactly (labels and dimensions are
  integers in mm, not trig-fed px);
- each attribute value as a run of literal and number tokens: literals (path commands,
  separators, class names, `#rrggbb` colours) exactly, numbers within `PX_TOL`.

`PX_TOL` is twice the writer's 0.01 px step, so a tie flip passes and a 0.05 px move fails.
A dropped subpath changes the token count of its `d`, and fails.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

PX_TOL = 0.02
_EPS = 1e-9  # parsing "214.13" and "214.11" leaves 0.02 plus float noise
_NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
_COLOUR = re.compile(r"#[0-9A-Fa-f]{3,8}")
MAX_REPORTED = 20

Token = str | float


def tokens(value: str) -> list[Token]:
    """`value` split into literal strings and floats; a `#rrggbb` colour stays one literal."""
    if _COLOUR.fullmatch(value):
        return [value]
    out: list[Token] = []
    pos = 0
    for match in _NUMBER.finditer(value):
        if match.start() > pos:
            out.append(value[pos : match.start()])
        out.append(float(match.group()))
        pos = match.end()
    if pos < len(value):
        out.append(value[pos:])
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _same_token(a: Token, b: Token) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= PX_TOL + _EPS
    return type(a) is type(b) and a == b


def _compare_value(actual: str, expected: str, where: str, out: list[str]) -> None:
    got, want = tokens(actual), tokens(expected)
    if len(got) != len(want):
        out.append(f"{where}: {len(got)} tokens, golden has {len(want)}")
        return
    for k, (a, b) in enumerate(zip(got, want, strict=True)):
        if not _same_token(a, b):
            out.append(f"{where}: token {k} is {a!r}, golden has {b!r}")
            return


def _compare_text(actual: str | None, expected: str | None, where: str, out: list[str]) -> None:
    got, want = (actual or "").split(), (expected or "").split()
    if got != want:
        out.append(f"{where}: {' '.join(got)!r}, golden has {' '.join(want)!r}")


def _walk(actual: ET.Element, expected: ET.Element, where: str, out: list[str]) -> None:
    if actual.tag != expected.tag:
        out.append(f"{where}: <{_local(actual.tag)}>, golden has <{_local(expected.tag)}>")
        return
    if sorted(actual.attrib) != sorted(expected.attrib):
        out.append(
            f"{where}: attributes {sorted(actual.attrib)}, golden has {sorted(expected.attrib)}"
        )
    for name in sorted(set(actual.attrib) & set(expected.attrib)):
        _compare_value(actual.attrib[name], expected.attrib[name], f"{where}@{name}", out)
    _compare_text(actual.text, expected.text, f"{where} text", out)
    got, want = list(actual), list(expected)
    if len(got) != len(want):
        out.append(f"{where}: {len(got)} children, golden has {len(want)}")
    for k, (a, b) in enumerate(zip(got, want, strict=False)):
        child = f"{where}/{_local(b.tag)}[{k}]"
        _walk(a, b, child, out)
        _compare_text(a.tail, b.tail, f"{child} tail", out)


def svg_differences(actual: str, expected: str) -> list[str]:
    """Every structural difference of `actual` from the golden `expected`; empty when they
    match. Each entry names the element path, the attribute and the token."""
    out: list[str] = []
    root_a, root_e = ET.fromstring(actual), ET.fromstring(expected)
    _walk(root_a, root_e, _local(root_e.tag), out)
    return out


def assert_svg_matches(actual: str, expected: str, name: str) -> None:
    found = svg_differences(actual, expected)
    if found:
        shown = "\n  ".join(found[:MAX_REPORTED])
        more = f"\n  ... and {len(found) - MAX_REPORTED} more" if len(found) > MAX_REPORTED else ""
        raise AssertionError(f"{name} differs from its golden:\n  {shown}{more}")
