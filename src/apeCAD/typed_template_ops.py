"""Typed `Document` methods for the section-template ops (ADR 0040, stage C3-S2).

A mixin beside `SectionTypedOps`: each method builds one op and applies it. Template
params are a JSON-like mapping (lists and objects of numbers and strings), the same object
an agent sends through the op catalog.
"""

from __future__ import annotations

from collections.abc import Mapping

from apeCAD.entities import EntityId, SectionTemplate
from apeCAD.errors import DocumentError
from apeCAD.ops import AddSectionTemplate, EditSectionTemplate, ExplodeSectionTemplate
from apeCAD.typed_ops import TypedOps


class TemplateTypedOps(TypedOps):
    """Add, edit and explode section templates."""

    def add_section_template(
        self,
        template: str,
        params: Mapping[str, object],
        *,
        template_version: int | None = None,
        label: str | None = None,
    ) -> SectionTemplate:
        """Draw a template (the latest version unless one is named); returns its entity."""
        op = AddSectionTemplate(
            template=template, params=params, template_version=template_version, label=label
        )
        return self._require_produced(self._apply(op), SectionTemplate)

    def edit_section_template(
        self,
        template_id: EntityId,
        params: Mapping[str, object],
        *,
        template_version: int | None = None,
    ) -> SectionTemplate:
        """Replace a template's params whole and draw it again; returns the template."""
        self._apply(
            EditSectionTemplate(
                template_id=template_id, params=params, template_version=template_version
            )
        )
        return self._template(template_id)

    def explode_section_template(self, template_id: EntityId) -> None:
        """Drop the template and keep its children as a freehand drawing."""
        self._apply(ExplodeSectionTemplate(template_id=template_id))

    def section_templates(self) -> tuple[SectionTemplate, ...]:
        """The section templates, by id. `Document` supplies it."""
        raise NotImplementedError

    def template_of(self, entity_id: EntityId) -> SectionTemplate | None:
        """The template that owns `entity_id`, or None for a freehand entity (Errata 4)."""
        for template in self.section_templates():
            if entity_id in template.child_ids:
                return template
        return None

    def _template(self, template_id: EntityId) -> SectionTemplate:
        entity = self.entity(template_id)
        if not isinstance(entity, SectionTemplate):
            raise DocumentError(f"entity {template_id} is not a section template")
        return entity
