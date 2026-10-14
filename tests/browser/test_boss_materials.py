import json

import pytest
from pydantic import ValidationError

from services.browser.site_adapters.boss_materials import (
    parse_material_catalog,
)


def test_metadata_reference_changes_with_revision_but_does_not_claim_file_hash() -> None:
    material = {
        "filename": "Synthetic.pdf",
        "displayed_size": "376.1KB",
        "displayed_revision": "2026.10.14 09:30",
    }
    first = parse_material_catalog(json.dumps({"state": "observed", "materials": [material]}))
    newer = parse_material_catalog(
        json.dumps(
            {
                "state": "observed",
                "materials": [material | {"displayed_revision": "2026.10.14 09:31"}],
            }
        )
    )
    assert first.state == "observed" and first.identity_basis == "rendered_metadata"
    assert first.materials[0].reference != newer.materials[0].reference
    assert len(first.materials[0].reference) == 64
    assert "Synthetic" not in repr(first)


@pytest.mark.parametrize(
    "change", ["truncated", "path", "missing_revision", "url", "duplicate", "empty", "unknown"]
)
def test_incomplete_or_unbounded_material_is_rejected(change: str) -> None:
    item = {
        "filename": "Synthetic.pdf",
        "displayed_size": "376.1KB",
        "displayed_revision": "2026.10.14 09:30",
    }
    state, materials = "observed", [item]
    if change == "truncated":
        item["filename"] = "Synthe….pdf"
    if change == "path":
        item["filename"] = "../Synthetic.pdf"
    if change == "missing_revision":
        item["displayed_revision"] = ""
    if change == "url":
        item["url"] = "https://private.invalid"
    if change == "duplicate":
        materials.append(item)
    if change == "empty":
        materials = []
    if change == "unknown":
        state = "unknown"
    with pytest.raises((ValueError, ValidationError)):
        parse_material_catalog(json.dumps({"state": state, "materials": materials}))
