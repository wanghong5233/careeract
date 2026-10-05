from difflib import SequenceMatcher

from services.api.domain.material import MaterialConflict, MaterialInvalid


def material_changes(base: str, proposed: str) -> list[dict[str, object]]:
    return [
        {
            "id": f"change-{index}",
            "start": start,
            "end": end,
            "original": base[start:end],
            "replacement": proposed[new_start:new_end],
            "state": "pending",
        }
        for index, (tag, start, end, new_start, new_end) in enumerate(
            SequenceMatcher(a=base, b=proposed, autojunk=False).get_opcodes()
        )
        if tag != "equal"
    ]


def review_body(base: str, changes: list[dict[str, object]], *, preview: bool = False) -> str:
    cursor = 0
    pieces: list[str] = []
    for change in changes:
        start, end = int(str(change["start"])), int(str(change["end"]))
        if (
            start < cursor
            or end < start
            or end > len(base)
            or base[start:end] != change["original"]
        ):
            raise MaterialConflict("Proposal ranges overlap or no longer match")
        pieces.append(base[cursor:start])
        applied = change["state"] == "accepted" or (preview and change["state"] == "pending")
        pieces.append(str(change["replacement"]) if applied else base[start:end])
        cursor = end
    pieces.append(base[cursor:])
    return "".join(pieces)


def decide_changes(
    changes: list[dict[str, object]], identifiers: tuple[str, ...], state: str
) -> list[dict[str, object]]:
    if (
        state not in {"accepted", "rejected"}
        or not identifiers
        or len(set(identifiers)) != len(identifiers)
    ):
        raise MaterialInvalid("Select distinct changes to review")
    selected = set(identifiers)
    if not selected.issubset({str(change["id"]) for change in changes}):
        raise MaterialInvalid("Unknown change selection")
    result = []
    for change in changes:
        if change["id"] in selected and change["state"] not in {"pending", state}:
            raise MaterialConflict("Change has already received a different decision")
        result.append({**change, "state": state} if change["id"] in selected else dict(change))
    return result
