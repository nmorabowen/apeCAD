"""The `apeCAD.section-draft` v1 of a `Document`, and reopening one (ADR 0025, stage C4).

`section_block(document)` is the derived `section` block; `section_draft(document)` is the
whole draft a consumer stores (apeConcrete reads `section`, apeCAD replays `document`);
`document_from_draft(draft)` reopens it under rule P9: numbers warn, structure refuses.

This module sits above `document.py` because it needs the ops log and `Document.from_dict`.
`apeCAD.section` (pure geometry, below the handlers) holds the projection itself and may not
import `document`; nothing under `draft/`, `section/` or `document.py` imports this module
(tests/test_architecture.py).
"""

from __future__ import annotations

import functools
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from apeCAD._version import __version__
from apeCAD.document import Document
from apeCAD.entities import Entity, EntityId
from apeCAD.errors import DocumentError
from apeCAD.section.draft import (
    DRAFT_FRAME,
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_VERSION,
    DRAFT_UNITS,
    compare_sections,
    project_section,
    require_header,
)

Json = dict[str, object]

COMMIT_ENV = "APECAD_COMMIT"
"""Overrides the detected git sha in `producer.apeCAD_commit` (a build or CI can set it)."""


def _entities(document: Document) -> Mapping[EntityId, Entity]:
    return {entity_id: document.entity(entity_id) for entity_id in document.entity_ids()}


def section_block(document: Document) -> Json:
    """The draft's `section` block: a pure function of the document (ADR 0025 decision 2)."""
    return project_section(_entities(document))


def section_draft(document: Document, *, commit: str | None | Literal["auto"] = "auto") -> Json:
    """The whole `apeCAD.section-draft` v1 (specs/section-draft.md).

    `commit="auto"` takes `APECAD_COMMIT`, else the sha of the git checkout this package
    runs from, else null. Pass `None` for output that must not depend on the checkout
    (the committed fixtures do).
    """
    return {
        "schema": DRAFT_SCHEMA,
        "version": DRAFT_SCHEMA_VERSION,
        "units": DRAFT_UNITS,
        "frame": dict(DRAFT_FRAME),
        "producer": {
            "apeCAD_version": __version__,
            "apeCAD_commit": producer_commit() if commit == "auto" else commit,
        },
        "document": document.to_dict(),
        "section": section_block(document),
        "warnings": [warning.to_dict() for warning in document.section_lint()],
    }


def document_from_draft(draft: Mapping[str, object]) -> tuple[Document, list[Json]]:
    """Reopen a draft by replaying its `document` (ADR 0025 decision 3, P9).

    Returns the document and the reopen warnings, `{code, ids, message}`, one per stored
    item whose numbers differ from the replay beyond rel 1e-9. Raises `DocumentError` for
    an unknown schema, version or units, a log that does not replay, or a structural
    difference between the stored `section` and the recomputed one. The stored
    `warnings[]` are advisory and not compared; `Document.section_lint()` recomputes them.
    """
    require_header(draft)
    raw = draft.get("document")
    if not isinstance(raw, dict):
        raise DocumentError("a section-draft needs a document object (the ops log)")
    payload = cast(Json, raw)
    try:
        document = Document.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:  # an op that does not decode
        raise DocumentError(f"the draft's document does not replay: {exc}") from exc
    if "section" not in draft:
        raise DocumentError("a section-draft needs its section block")
    warnings = compare_sections(draft["section"], section_block(document))
    return document, warnings


@functools.cache
def _git_commit() -> str | None:
    """HEAD of the checkout this package was imported from, when it is one (an editable
    install or a source tree); None for an installed wheel or without git."""
    package = Path(__file__).resolve().parent
    try:
        top = subprocess.run(
            ["git", "-C", str(package), "rev-parse", "--show-toplevel", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    if len(top) != 2 or Path(top[0]).resolve() / "src" / "apeCAD" != package:
        return None  # a wheel inside some other repository's tree
    return top[1]


def producer_commit() -> str | None:
    """`producer.apeCAD_commit`: `APECAD_COMMIT` when set, else the git sha, else None."""
    override = os.environ.get(COMMIT_ENV, "").strip()
    return override or _git_commit()
