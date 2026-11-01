"""ADR 0039 decision 1: the `apeCAD.section-draft` v2 spec, its fenced block and its SHA-256."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

SPECS = Path(__file__).resolve().parents[1] / "AProjects" / "specs"
SPEC_V2 = SPECS / "section-draft-v2.md"
CONTRACT_SHA256_V2 = "eb0efd21715d46bc5fdab99ac20d979ab9569de4ed8ee7ce9ea9a7e2f83ae267"


def _text() -> str:
    return SPEC_V2.read_text(encoding="utf-8").replace("\r\n", "\n")


def _contract_body(text: str) -> str:
    """Same regex and LF normalisation as test_section_draft.py's v1 hash test."""
    blocks = re.findall(r"^## The contract\n\n```\n(.*?)```\n", text, flags=re.S | re.M)
    assert len(blocks) == 1
    return blocks[0] if blocks[0].endswith("\n") else blocks[0] + "\n"


def test_spec_v2_contract_block_hash_is_unchanged() -> None:
    """The fenced block is the v2 contract only while it hashes to this (ADR 0025 decision 1)."""
    body = _contract_body(_text())
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == CONTRACT_SHA256_V2


def test_spec_v2_states_the_hash_it_pins() -> None:
    """The hash printed in the spec is the one this test pins, so a paster can check a copy."""
    printed = re.findall(r"^```text\n([0-9a-f]{64})\n```$", _text(), flags=re.M)
    assert printed == [CONTRACT_SHA256_V2]


def test_spec_v2_block_is_version_2_of_the_same_schema() -> None:
    body = _contract_body(_text())
    assert body.startswith('{ "schema": "apeCAD.section-draft", "version": 2, "units": "mm",\n')
