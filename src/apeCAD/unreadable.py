"""Name the oversized input behind an error a reader raised below an entry point (apeSection#54).

JSON hands a reader values Python cannot always handle. A list nested hundreds deep makes
`repr` or a recursive check raise `RecursionError`, at a depth that depends on the thread's
stack (an HTTP handler thread has less left than the main one). An integer beyond the float
range raises `OverflowError` in `float()`, and past 4300 digits `ValueError` in `repr`. Any of
these, uncaught, kills an HTTP handler thread, and the client sees a dropped connection.

`refusing_unreadable` wraps each place outside input enters: `Session.apply` and
`apply_batch`, `Document.from_dict`, `transport.handle` and the scratchpad's POST routes. It
does not enumerate inputs or readers. When one of `UNREADABLE` escapes, it scans the input for
the cause and raises a refusal that names the path. The scan never recurses, visits each
container once and holds a few small records per container, never a string per child (a
path is built only for what it names), so it cannot fail the way the reader did. A scan
that finds no cause lets the original error go: a real bug stays loud.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import cast

from apeCAD.errors import DocumentError

UNREADABLE: tuple[type[Exception], ...] = (RecursionError, OverflowError, ValueError)
NESTING_FLOOR = 32
"""A `RecursionError` is put down to nesting only at this depth or deeper; under it, no JSON
reader here recurses far enough to run out of stack, so the error is a bug and propagates."""
PATH_STEPS = 8
"""A deep branch is named at most this many keys down: `body.ops[0].start_id`, not 900 `[0]`."""


@contextmanager
def refusing_unreadable(
    where: str, read: Callable[[], object], error: type[DocumentError]
) -> Generator[None, None, None]:
    """Raise `error` naming the cause when the body raises one of `UNREADABLE` on an
    oversized part of `read()`; re-raise unchanged when no such part is found."""
    try:
        yield
    except UNREADABLE as exc:
        named = cause(read(), where, deep_first=isinstance(exc, RecursionError))
        if named is None:
            raise
        raise error(named) from None


def cause(value: object, where: str, *, deep_first: bool) -> str | None:
    """What makes `value` unreadable, with its path from `where`, or None."""
    checks = (_too_deep, _too_large) if deep_first else (_too_large, _too_deep)
    for check in checks:
        found = check(value, where)
        if found is not None:
            return found
    return None


def _is_container(value: object) -> bool:
    return isinstance(value, Mapping | list | tuple)


def _is_sequence(value: object) -> bool:
    return isinstance(value, list | tuple)


def _items(container: object) -> Iterator[tuple[object, object]]:
    """`(key or index, child)` of a container, lazily: no list, no strings per child."""
    if isinstance(container, Mapping):
        return iter(cast(Mapping[object, object], container).items())
    return enumerate(cast(Sequence[object], container))


def _step(container: object, key: object) -> str:
    return f".{key}" if isinstance(container, Mapping) else f"[{key}]"


def _overflows(value: object) -> bool:
    if not isinstance(value, int) or isinstance(value, bool):
        return False
    try:
        float(value)
    except OverflowError:
        return True
    return False


def _too_large(value: object, where: str) -> str | None:
    """An integer no float can hold: a leaf of the first container that has one, in a
    depth-first walk. Memory is one parent link per container, never a path per child: the
    path is built only for the integer it names (apeSection#371 review)."""
    if not _is_container(value):
        return _large(where, value) if _overflows(value) else None
    links: list[tuple[int, object, object]] = []  # (parent link, container, key); -1 = root
    seen: set[int] = set()
    stack: list[tuple[object, int]] = [(value, -1)]
    while stack:
        node, link = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        below: list[tuple[object, object]] = []
        for key, child in _items(node):
            if _is_container(child):
                if id(child) not in seen:
                    below.append((key, child))
            elif _overflows(child):
                return _large(_path(where, links, link) + _step(node, key), child)
        for key, child in reversed(below):
            links.append((link, node, key))
            stack.append((child, len(links) - 1))
    return None


def _large(path: str, value: object) -> str:
    bits = cast(int, value).bit_length()
    return f"{path} is an integer too large to read ({bits} bits; a number holds 1024)"


def _path(where: str, links: list[tuple[int, object, object]], link: int) -> str:
    steps: list[str] = []
    while link >= 0:
        link, container, key = links[link]
        steps.append(_step(container, key))
    return where + "".join(reversed(steps))


def _too_deep(value: object, where: str) -> str | None:
    """The deepest branch, named down to where plain list nesting starts (at most
    `PATH_STEPS` keys), if what is left there is `NESTING_FLOOR` deep or more; a container
    that holds itself is named as such."""
    heights = _heights(value)
    if heights is None:
        return f"{where} contains itself"
    path, node = where, value
    for _ in range(PATH_STEPS):
        best: tuple[object, object] | None = None
        for key, child in _items(node) if _is_container(node) else ():
            if _is_container(child) and (best is None or heights[id(child)] > heights[id(best[1])]):
                best = (key, child)
        if best is None or (_is_sequence(node) and _is_sequence(best[1])):
            break
        path, node = path + _step(node, best[0]), best[1]
    height = heights.get(id(node), 0) if _is_container(node) else 0
    if height < NESTING_FLOOR:
        return None
    return f"{path} is nested {height} levels deep, too deep to read"


def _heights(value: object) -> dict[int, int] | None:
    """Each container's height (a leaf is 0) by `id`, computed once per container without
    recursion; None when a container holds itself. Only containers go on the stack."""
    heights: dict[int, int] = {}
    if not _is_container(value):
        return heights
    open_: set[int] = set()
    stack: list[tuple[object, bool]] = [(value, False)]
    while stack:
        node, closing = stack.pop()
        key = id(node)
        if closing:
            open_.discard(key)
            heights[key] = 1 + max(
                (heights[id(c)] for _, c in _items(node) if _is_container(c)), default=0
            )
            continue
        if key in heights:
            continue
        if key in open_:
            return None
        open_.add(key)
        stack.append((node, True))
        stack.extend((c, False) for _, c in _items(node) if _is_container(c))
    return heights
