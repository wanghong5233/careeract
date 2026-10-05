import pytest

from services.api.domain.material import MaterialConflict, MaterialInvalid
from services.api.domain.material_review import decide_changes, material_changes, review_body


def test_sentence_changes_can_be_decided_independently_and_keep_pending_remainder() -> None:
    changes = material_changes("负责接口设计，完成验证。", "负责平台接口设计，完成自动化验证。")
    assert len(changes) == 2
    accepted = decide_changes(changes, (str(changes[0]["id"]),), "accepted")
    assert review_body("负责接口设计，完成验证。", accepted) == "负责平台接口设计，完成验证。"
    assert accepted[1]["state"] == "pending"
    rejected = decide_changes(accepted, (str(changes[1]["id"]),), "rejected")
    assert review_body("负责接口设计，完成验证。", rejected) == "负责平台接口设计，完成验证。"


def test_review_rejects_overlap_stale_and_duplicate_decisions() -> None:
    changes = material_changes("同一句同一句", "新一句同一句")
    with pytest.raises(MaterialInvalid):
        decide_changes(changes, (str(changes[0]["id"]),) * 2, "accepted")
    with pytest.raises(MaterialConflict):
        review_body("不同", changes)
    decided = decide_changes(changes, (str(changes[0]["id"]),), "accepted")
    with pytest.raises(MaterialConflict):
        decide_changes(decided, (str(changes[0]["id"]),), "rejected")
