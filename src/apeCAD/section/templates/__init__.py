"""Parametric section templates (ADR 0040): pure functions from parameters to a `Plan`.

    plan             Plan and its parts, TemplateParamError, the shared parameter readers
    rect_column      rectangular tied column, versions 1 and 2
    polygon_column   convex polygonal tied column, versions 1 and 2
    rect_hollow      rectangular hollow section without crossties, versions 1 and 2
    t_beam           symmetric T beam, versions 1 and 2
    circular_column  circular column with a spiral or a hoop, versions 1 and 2
    cft_round        round concrete-filled steel tube, versions 1 and 2
    cft_rect         rectangular concrete-filled steel tube, versions 1 and 2
    hole_rules       the rules R1 to R7 a user hole must clear, decided exactly (Errata 17)
    holes            the hole step of version 2: v1 composed with user holes (Errata 13.2)

`TEMPLATES[name][version]` is the expansion function of one template version. A version is
kept for ever once released (ADR 0040 decision 4): a change to how a template expands adds a
version beside the old one, so a log recorded years ago replays to the same drawing. Version 2
is version 1 wrapped in the hole step (`holes.version_2`, ADR 0040 Errata 13.2 and 15); no v1
module changes.

Stage C3-S1 holds only the functions. The entity, the ops, the lock and the catalog entries
come in C3-S2. This package imports only apeCAD.section, apeCAD.geometry and apeCAD.errors
(tests/test_architecture.py).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType

from apeCAD.section.templates import (
    cft_rect,
    cft_round,
    circular_column,
    holes,
    polygon_column,
    rect_column,
    rect_hollow,
    t_beam,
)
from apeCAD.section.templates.plan import Plan, TemplateParamError, shown

Expansion = Callable[[Mapping[str, object]], Plan]

TEMPLATES: Mapping[str, Mapping[int, Expansion]] = MappingProxyType(
    {
        rect_column.TEMPLATE: MappingProxyType({
            1: rect_column.expand_v1,
            2: holes.version_2(
                rect_column.TEMPLATE, rect_column.FIELDS, rect_column.expand_v1, centred=True
            ),
        }),
        polygon_column.TEMPLATE: MappingProxyType({
            1: polygon_column.expand_v1,
            2: holes.version_2(
                polygon_column.TEMPLATE, polygon_column.FIELDS, polygon_column.expand_v1,
                centred=False,
            ),
        }),
        rect_hollow.TEMPLATE: MappingProxyType({
            1: rect_hollow.expand_v1,
            2: holes.version_2(
                rect_hollow.TEMPLATE, rect_hollow.FIELDS, rect_hollow.expand_v1, centred=True
            ),
        }),
        t_beam.TEMPLATE: MappingProxyType({
            1: t_beam.expand_v1,
            2: holes.version_2(t_beam.TEMPLATE, t_beam.FIELDS, t_beam.expand_v1, centred=True),
        }),
        circular_column.TEMPLATE: MappingProxyType({
            1: circular_column.expand_v1,
            2: holes.version_2(
                circular_column.TEMPLATE, circular_column.FIELDS, circular_column.expand_v1,
                centred=True,
            ),
        }),
        cft_round.TEMPLATE: MappingProxyType({
            1: cft_round.expand_v1,
            2: holes.version_2(
                cft_round.TEMPLATE, cft_round.FIELDS, cft_round.expand_v1, centred=True
            ),
        }),
        cft_rect.TEMPLATE: MappingProxyType({
            1: cft_rect.expand_v1,
            2: holes.version_2(
                cft_rect.TEMPLATE, cft_rect.FIELDS, cft_rect.expand_v1, centred=True
            ),
        }),
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
            template, "template_version", f"must be a whole number, got {shown(version)}"
        )
    if chosen not in versions:
        raise TemplateParamError(
            template,
            "template_version",
            f"unknown version {shown(version)}; known: {', '.join(map(str, sorted(versions)))}",
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
