"""Name the oversized input behind an error a reader raised below an entry point (apeSection#54).

JSON hands a reader values Python cannot always handle. A list nested hundreds deep makes
`repr` or a recursive check raise `RecursionError`, at a depth that depends on the thread's
stack (an HTTP handler thread has less left than the main one). An integer beyond the float
range raises `OverflowError` in `float()`, and past 4300 digits `ValueError` in `repr`. Any of
these, uncaught, kills an HTTP handler thread, and the client sees a dropped connection.

`refusing_unreadable` wraps each place outside input enters: `Session.apply` and
`apply_batch`, `Document.from_dict`, `transport.handle` and the scratchpad's POST routes. It
does not enumerate inputs or readers. When one of `UNREADABLE` escapes, it scans the input for
the cause and raises a refusal that names the path. The scan never recurses and visits each
container once, so it cannot fail the way the reader did. A scan that finds no cause lets
the original error go: a real bug stays loud.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
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


def _children(value: object) -> list[tuple[str, object]] | None:
    """`(path step, child)` of a JSON container; None for anything else."""
    if isinstance(value, Mapping):
        items = cast(Mapping[object, object], value).items()
        return [(f".{key}", child) for key, child in items]
    if isinstance(value, list | tuple):
        return [(f"[{i}]", child) for i, child in enumerate(cast(list[object], value))]
    return None


def _too_large(value: object, where: str) -> str | None:
    """The first integer no float can hold, depth first."""
    seen: set[int] = set()
    stack: list[tuple[str, object]] = [(where, value)]
    while stack:
        path, node = stack.pop()
        if isinstance(node, int) and not isinstance(node, bool):
            try:
                float(node)
            except OverflowError:
                bits = node.bit_length()
                return f"{path} is an integer too large to read ({bits} bits; a number holds 1024)"
            continue
        kids = _children(node)
        if kids is None or id(node) in seen:
            continue
        seen.add(id(node))
        stack.extend((path + step, child) for step, child in reversed(kids))
    return None


def _too_deep(value: object, where: str) -> str | None:
    """The deepest branch, named down to where plain list nesting starts (at most
    `PATH_STEPS` keys), if what is left there is `NESTING_FLOOR` deep or more; a container
    that holds itself is named as such."""
    heights = _heights(value)
    if heights is None:
        return f"{where} contains itself"
    path, node = where, value
    for _ in range(PATH_STEPS):
        kids = [(s, c) for s, c in _children(node) or [] if _children(c) is not None]
        if not kids:
            break
        step, child = max(kids, key=lambda kid: heights[id(kid[1])])
        if _is_sequence(node) and _is_sequence(child):
            break
        path, node = path + step, child
    height = heights.get(id(node), 0)
    if height < NESTING_FLOOR:
        return None
    return f"{path} is nested {height} levels deep, too deep to read"


def _is_sequence(value: object) -> bool:
    return isinstance(value, list | tuple)


def _heights(value: object) -> dict[int, int] | None:
    """Each container's height (a leaf is 0) by `id`, computed once per container without
    recursion; None when a container holds itself."""
    heights: dict[int, int] = {}
    open_: set[int] = set()
    stack: list[tuple[object, bool]] = [(value, False)]
    while stack:
        node, closing = stack.pop()
        kids = _children(node)
        if kids is None:
            continue
        key = id(node)
        if closing:
            open_.discard(key)
            heights[key] = 1 + max((heights.get(id(child), 0) for _, child in kids), default=0)
            continue
        if key in heights:
            continue
        if key in open_:
            return None
        open_.add(key)
        stack.append((node, True))
        stack.extend((child, False) for _, child in kids)
    return heights
