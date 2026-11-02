"""Section-template ops (ADR 0040, stage C3-S2): add, edit and explode a template.

A template's intent is its `template`, its `template_version` and its `template_params`
(named so, not `params`, because the op catalog's request envelope uses `params`); the
entities it draws are derived (`section.templates`, a pure function to a `Plan`, and
`draft.templates`, which builds the entities). The committed op records the version it ran
and the `child_ids` it allocated, so replay rebuilds the same ids and refuses a log whose
expansion no longer matches (ADR 0040 decision 4, Errata 3).

`params` is stored read-only: `freeze_params` turns lists into tuples and objects into
read-only mappings, and `thaw_params` turns them back for JSON. The structure is checked
here (a known template and version, an object of params, at most `MAX_PARAMS_DEPTH` levels
deep and `MAX_PARAMS_VALUES` values); the params themselves are checked by the expansion,
which refuses a bad one with `TemplateParamError` (`INVALID_ARGUMENT`).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from apeCAD.entities import EntityId
from apeCAD.errors import DocumentError, OpArgumentError
from apeCAD.ops.base import optional_label
from apeCAD.section.templates import TEMPLATES, TemplateParamError
from apeCAD.section.templates.plan import MAX_TEMPLATE_BARS, shown

MAX_PARAMS_DEPTH = 16
"""Most levels of objects and lists a template's params may nest; the params object is the
first. The deepest real param, a polygon's `ring`, is three. The cap keeps the recursive
`_freeze`, `thaw_params` and JSON encoder far from Python's recursion limit."""

MAX_PARAMS_VALUES = 4 * MAX_TEMPLATE_BARS
"""Most objects, lists and scalars a template's params may hold, counted as `_freeze` walks
them, so a value reached by two paths counts twice. The largest params the expansions accept
are a polygon's `ring` at `MAX_TEMPLATE_BARS` vertices (three values each) and a few scalars.
The cap keeps a shared-reference DAG, which JSON cannot produce but an in-process caller can
(five levels of `v = [v] * 1000` reach 10^15 paths), from hanging `_freeze`."""


def freeze_params(params: object, path: str = "params") -> Mapping[str, object]:
    """A read-only deep copy of a params object: objects as mappings, lists as tuples."""
    _require_depth(params, path)
    frozen = _freeze(params, path)
    if not isinstance(frozen, MappingProxyType):
        raise DocumentError(f"{path} must be an object, got {type(params).__name__}")
    return cast(Mapping[str, object], frozen)


def _require_depth(params: object, path: str) -> None:
    """Refuse params nested or sized past the caps. A loop, not a recursion, so it cannot
    overflow, and it stops at the budget, so a shared-reference DAG cannot hang it."""
    stack: list[tuple[object, int]] = [(params, 1)]
    values = 1
    while stack:
        value, depth = stack.pop()
        children: Collection[object]
        if isinstance(value, Mapping):
            children = cast(Mapping[object, object], value).values()
        elif isinstance(value, list | tuple):
            children = cast(Sequence[object], value)
        else:
            continue
        if depth > MAX_PARAMS_DEPTH:
            raise OpArgumentError(f"{path} nests deeper than {MAX_PARAMS_DEPTH} levels")
        values += len(children)
        if values > MAX_PARAMS_VALUES:
            raise OpArgumentError(f"{path} holds more than {MAX_PARAMS_VALUES} values")
        stack.extend((child, depth + 1) for child in children)


def _freeze(value: object, path: str) -> object:
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, item in cast(Mapping[object, object], value).items():
            if not isinstance(key, str):
                raise DocumentError(f"{path} keys must be strings, got {shown(key)}")
            out[key] = _freeze(item, f"{path}.{key}")
        return MappingProxyType(out)
    if isinstance(value, list | tuple):
        items = cast(Sequence[object], value)
        return tuple(_freeze(item, f"{path}[{k}]") for k, item in enumerate(items))
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise DocumentError(f"{path} holds {type(value).__name__}, which JSON cannot carry")


def thaw_params(value: object) -> object:
    """The JSON form of a frozen value: mappings as dicts, tuples as lists."""
    if isinstance(value, Mapping):
        pairs = cast(Mapping[object, object], value).items()
        return {str(k): thaw_params(v) for k, v in pairs}
    if isinstance(value, tuple):
        return [thaw_params(v) for v in cast(tuple[object, ...], value)]
    return value


def require_template(template: str) -> str:
    if template not in TEMPLATES:
        raise TemplateParamError(
            template, "template", f"unknown template; known: {', '.join(TEMPLATES)}"
        )
    return template


def require_version(template: str, version: object) -> int | None:
    """None (the latest, filled in when the op commits) or a released version of `template`."""
    if version is None:
        return None
    if isinstance(version, bool) or not isinstance(version, int):
        raise TemplateParamError(
            template, "template_version", f"must be a whole number, got {shown(version)}"
        )
    if version not in TEMPLATES[template]:
        known = ", ".join(str(v) for v in sorted(TEMPLATES[template]))
        raise TemplateParamError(
            template, "template_version", f"unknown version {shown(version)}; known: {known}"
        )
    return version


def _require_child_ids(child_ids: tuple[EntityId, ...]) -> None:
    if len(set(child_ids)) != len(child_ids) or any(i < 1 for i in child_ids):
        raise DocumentError(f"child_ids must be distinct positive ids, got {list(child_ids)}")


@dataclass(frozen=True, slots=True)
class AddSectionTemplate:
    """A parametric section (ADR 0040 decision 1): one template entity and its children.

    `template_version` None means the latest; the committed op records the version it ran,
    the template's `entity_id` and its `child_ids`, so replay draws the same ids.
    """

    template: str
    template_params: Mapping[str, object]
    template_version: int | None = None
    label: str | None = None
    entity_id: EntityId | None = None
    child_ids: tuple[EntityId, ...] = ()

    def __post_init__(self) -> None:
        require_template(self.template)
        require_version(self.template, self.template_version)
        object.__setattr__(
            self, "template_params", freeze_params(self.template_params, "template_params")
        )
        object.__setattr__(self, "label", optional_label(self.label))
        _require_child_ids(self.child_ids)


@dataclass(frozen=True, slots=True)
class EditSectionTemplate:
    """Replace a template's params whole and draw it again (ADR 0040 decision 2).

    The template keeps its id, and its version unless `template_version` names another.
    The old children are deleted and the new ones get fresh ids, recorded in `child_ids`.
    Moving a template is an edit of its `center_mm`.
    """

    template_id: EntityId
    template_params: Mapping[str, object]
    template_version: int | None = None
    child_ids: tuple[EntityId, ...] = ()

    def __post_init__(self) -> None:
        version = cast(object, self.template_version)  # JSON may carry anything
        if isinstance(version, bool) or not (version is None or isinstance(version, int)):
            raise TemplateParamError(
                "template", "template_version",
                f"must be a whole number, got {shown(self.template_version)}",
            )  # fmt: skip
        object.__setattr__(
            self, "template_params", freeze_params(self.template_params, "template_params")
        )
        _require_child_ids(self.child_ids)


@dataclass(frozen=True, slots=True)
class ExplodeSectionTemplate:
    """Leave the template (ADR 0040 decision 3): its children stay, as a freehand drawing.

    The template entity is dropped and nothing else changes. There is no re-implode.
    """

    template_id: EntityId


TemplateOp = AddSectionTemplate | EditSectionTemplate | ExplodeSectionTemplate
TEMPLATE_OPS = (AddSectionTemplate, EditSectionTemplate, ExplodeSectionTemplate)
