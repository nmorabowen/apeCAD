"""Errors raised by apeCAD documents, and the error codes every surface reports.

The codes are the agent-surface contract (spec `agent-surface-mcp.md` §1, ADR 0028). An
exception carries its code as the class attribute `code`.
"""

from __future__ import annotations

from typing import ClassVar

UNKNOWN_OP = "UNKNOWN_OP"
INVALID_ARGUMENT = "INVALID_ARGUMENT"
REFUSED = "REFUSED"
STALE = "STALE"
NOT_FOUND = "NOT_FOUND"
TOO_LARGE = "TOO_LARGE"
DETACHED = "DETACHED"
UNAVAILABLE = "UNAVAILABLE"
IO_ERROR = "IO_ERROR"
TEMPLATE_LOCKED = "TEMPLATE_LOCKED"

ERROR_CODES: tuple[str, ...] = (
    UNKNOWN_OP,
    INVALID_ARGUMENT,
    REFUSED,
    STALE,
    NOT_FOUND,
    TOO_LARGE,
    DETACHED,
    UNAVAILABLE,
    IO_ERROR,
    TEMPLATE_LOCKED,
)


class DocumentError(Exception):
    """Invalid document mutation or load. The document refused it: `REFUSED`."""

    code: ClassVar[str] = REFUSED


class OpArgumentError(DocumentError):
    """A missing, extra or mistyped op argument, caught before the document sees the op."""

    code: ClassVar[str] = INVALID_ARGUMENT


class TemplateLockedError(DocumentError):
    """An op would change, delete or reference a section-template child (ADR 0040 decision 3).

    A refusal like `REFUSED`, under its own code so a host can offer the two ways out: edit
    the template's params, or explode it into a freehand drawing.
    """

    code: ClassVar[str] = TEMPLATE_LOCKED


class UnknownOpError(OpArgumentError):
    """No catalog entry has that op name."""

    code: ClassVar[str] = UNKNOWN_OP
