"""ADR 0041 Errata E1: the `apeCAD.section-overlay` v2 spec, its fenced block and its SHA-256."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_V2 = ROOT / "AProjects" / "specs" / "section-overlay-v2.md"
CONTRACT_SHA256_V2 = "8fe206a9c4e55af5f67246b59b57a0073e1d7e10cce7341bc149ffa8c4337231"
WORKED_FIXTURE = "tests/fixtures/section_draft_v2/circular_column_spiral.json"
WORKED_SHA256 = "fd20de574ef8e5c73a027ac3972beecc0b1f42538510bd004ea954aedde548df"


def _text() -> str:
    return SPEC_V2.read_text(encoding="utf-8").replace("\r\n", "\n")


def _contract_body(text: str) -> str:
    """Same regex and LF normalisation as test_render_overlay.py's v1 hash test."""
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
    assert body.startswith('{ "schema": "apeCAD.section-overlay", "version": 2, "units": "mm",\n')


def test_spec_v2_worked_hash_is_the_canonical_hash_of_its_fixture() -> None:
    """The spec's worked `section_sha256`, recomputed here so every CI platform checks it.

    A reference copy of apeSection's `canonical_section_hash`, local to this test: apeCAD's
    src never computes the hash (ADR 0041 Errata E1).
    """
    printed = re.findall(r"^(tests/fixtures/\S+\.json)  ([0-9a-f]{64})$", _text(), flags=re.M)
    assert printed == [(WORKED_FIXTURE, WORKED_SHA256)]
    draft = json.loads((ROOT / WORKED_FIXTURE).read_text(encoding="utf-8"))
    text = json.dumps(
        draft["section"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == WORKED_SHA256
