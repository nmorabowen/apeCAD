"""Parametric section templates (ADR 0040): pure functions from parameters to a `Plan`.

    plan             Plan and its parts, TemplateParamError, the shared parameter readers
    rect_column      rectangular tied column, version 1
    polygon_column   convex polygonal tied column, version 1
    rect_hollow      rectangular hollow section without crossties, version 1
    t_beam           symmetric T beam, version 1
    circular_column  circular column with a spiral or a hoop, version 1

`TEMPLATES[name][version]` is the expansion function of one template version. A version is
kept for ever once released (ADR 0040 decision 4): a change to how a template expands adds a
version beside the old one, so a log recorded years ago replays to the same drawing.

Stage C3-S1 holds only the functions. The entity, the ops, the lock and the catalog entries
come in C3-S2. This package imports only apeCAD.section, apeCAD.geometry and apeCAD.errors
(tests/test_architecture.py).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from apeCAD.section.templates import (
    circular_column,
    polygon_column,
    rect_column,
    rect_hollow,
    t_beam,
)
from apeCAD.section.templates.plan import Plan, TemplateParamError

Expansion = Callable[[Mapping[str, object]], Plan]

TEMPLATES: Mapping[str, Mapping[int, Expansion]] = MappingProxyType(
    {
        rect_column.TEMPLATE: MappingProxyType({1: rect_column.expand_v1}),
        polygon_column.TEMPLATE: MappingProxyType({1: polygon_column.expand_v1}),
        rect_hollow.TEMPLATE: MappingProxyType({1: rect_hollow.expand_v1}),
        t_beam.TEMPLATE: MappingProxyType({1: t_beam.expand_v1}),
        circular_column.TEMPLATE: MappingProxyType({1: circular_column.expand_v1}),
    }
)


def latest_version(template: str) -> int:
    """The newest version of `template`, the one an op that names none records."""
    return max(_versions(template))


def expand(template: str, params: Mapping[str, object], version: object = None) -> Plan:
    """The plan of `template` at `version` (the latest when None) for `params`.

    `version` is typed `object`: it arrives from JSON, and anything but a whole number is
    refused by name.
    """
    versions = _versions(template)
    chosen: object = max(versions) if version is None else version
    if isinstance(chosen, bool) or not isinstance(chosen, int):  # 1.0 == 1, but is no version
        raise TemplateParamError(
            template, "template_version", f"must be a whole number, got {version!r}"
        )
    if chosen not in versions:
        raise TemplateParamError(
            template,
            "template_version",
            f"unknown version {version!r}; known: {', '.join(map(str, sorted(versions)))}",
        )
    return versions[chosen](params)


def _versions(template: str) -> Mapping[int, Expansion]:
    versions = TEMPLATES.get(template)
    if versions is None:
        raise TemplateParamError(
            template, "template", f"unknown template; known: {', '.join(TEMPLATES)}"
        )
    return versions


__all__ = ["TEMPLATES", "Expansion", "Plan", "TemplateParamError", "expand", "latest_version"]
