import json
from uuid import UUID, uuid4, uuid5

from sqlalchemy import RowMapping, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from services.api.application.context import ActorContext
from services.api.domain.material import (
    Material,
    MaterialConflict,
    MaterialDetail,
    MaterialDraft,
    MaterialInvalid,
    MaterialNotFound,
    MaterialPage,
    MaterialProposal,
    MaterialSource,
    MaterialUnavailable,
    MaterialVersion,
)
from services.api.domain.project import ProjectInvalid
from services.api.infrastructure.projects import decode_cursor, encode_cursor


def material_from_row(row: RowMapping) -> Material:
    return Material(**{name: row[name] for name in Material.__dataclass_fields__})


def material_version_from_row(row: RowMapping) -> MaterialVersion:
    return MaterialVersion(
        id=row["id"],
        material_id=row["material_id"],
        number=row["number"],
        body=row["body"],
        source=row["source"],
        created_at=row["created_at"],
        references=tuple(row["references"]),
    )


def proposal_from_row(row: RowMapping) -> MaterialProposal:
    return MaterialProposal(
        id=row["id"],
        material_id=row["material_id"],
        base_version_id=row["base_version_id"],
        proposed_body=row["proposed_body"],
        rationale=row["rationale"],
        state=row["state"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
        base_body=row["base_body"],
        base_number=row["base_number"],
        references=tuple(row["references"]),
    )


async def read_detail(
    connection: AsyncConnection, actor: ActorContext, material_id: UUID
) -> MaterialDetail | None:
    row = (
        (
            await connection.execute(
                text("SELECT * FROM career.materials WHERE id=:id AND user_id=:user_id"),
                {"id": material_id, "user_id": actor.user_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    material = material_from_row(row)
    versions = (
        (
            await connection.execute(
                text(
                    "SELECT * FROM career.material_versions "
                    "WHERE material_id=:id ORDER BY number DESC"
                ),
                {"id": material_id},
            )
        )
        .mappings()
        .all()
    )
    proposals = (
        (
            await connection.execute(
                text(
                    "SELECT p.*, v.body AS base_body, v.number AS base_number "
                    "FROM career.material_proposals p JOIN career.material_versions v "
                    "ON v.id=p.base_version_id AND v.material_id=p.material_id "
                    "WHERE p.material_id=:id ORDER BY p.created_at DESC, p.id DESC"
                ),
                {"id": material_id},
            )
        )
        .mappings()
        .all()
    )
    version_items = tuple(material_version_from_row(item) for item in versions)
    return MaterialDetail(
        material=material,
        current_version=next(
            item for item in version_items if item.id == material.current_version_id
        ),
        versions=version_items,
        proposals=tuple(proposal_from_row(item) for item in proposals),
    )


async def lock_material(
    connection: AsyncConnection, actor: ActorContext, material_id: UUID
) -> RowMapping | None:
    return (
        (
            await connection.execute(
                text(
                    "SELECT * FROM career.materials "
                    "WHERE id=:id AND user_id=:user_id AND state='active' FOR UPDATE"
                ),
                {"id": material_id, "user_id": actor.user_id},
            )
        )
        .mappings()
        .one_or_none()
    )


async def insert_version(
    connection: AsyncConnection,
    actor: ActorContext,
    material_id: UUID,
    *,
    body: str,
    source: MaterialSource,
    references: tuple[dict[str, str], ...],
) -> None:
    number = await connection.scalar(
        text(
            "SELECT COALESCE(MAX(number),0)+1 FROM career.material_versions WHERE material_id=:id"
        ),
        {"id": material_id},
    )
    version_id = uuid4()
    await connection.execute(
        text(
            "INSERT INTO career.material_versions "
            '(id,material_id,number,body,source,"references") '
            "VALUES (:id,:material_id,:number,:body,:source,CAST(:refs AS jsonb))"
        ),
        {
            "id": version_id,
            "material_id": material_id,
            "number": number,
            "body": body,
            "source": source,
            "refs": json.dumps(references, ensure_ascii=False),
        },
    )
    await connection.execute(
        text(
            "UPDATE career.materials SET current_version_id=:current_version_id, "
            "version=:version, updated_at=clock_timestamp() "
            "WHERE id=:id AND user_id=:user_id"
        ),
        {
            "current_version_id": version_id,
            "version": uuid4(),
            "id": material_id,
            "user_id": actor.user_id,
        },
    )


async def insert_proposal(
    connection: AsyncConnection,
    actor: ActorContext,
    material_id: UUID,
    *,
    proposal_id: UUID,
    base_version_id: UUID,
    draft: MaterialDraft,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO career.material_proposals "
            '(id,material_id,user_id,base_version_id,proposed_body,rationale,state,"references") '
            "VALUES (:id,:material_id,:user_id,:base,:body,:rationale,'pending',"
            "CAST(:refs AS jsonb))"
        ),
        {
            "id": proposal_id,
            "material_id": material_id,
            "user_id": actor.user_id,
            "base": base_version_id,
            "body": draft.body,
            "rationale": draft.rationale,
            "refs": json.dumps(draft.references, ensure_ascii=False),
        },
    )


class PostgresMaterialRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def list(
        self,
        actor: ActorContext,
        *,
        project_id: UUID | None,
        limit: int,
        cursor: str | None,
        scoped: bool = False,
    ) -> MaterialPage:
        try:
            boundary = decode_cursor(cursor) if cursor else None
        except ProjectInvalid:
            raise MaterialInvalid("Invalid material cursor") from None
        conditions = ["user_id=:user_id", "state='active'"]
        parameters: dict[str, object] = {"user_id": actor.user_id, "limit": limit + 1}
        if scoped:
            conditions.append("(project_id IS NULL OR project_id=:project_id)")
            parameters["project_id"] = project_id
        elif project_id is not None:
            conditions.append("project_id=:project_id")
            parameters["project_id"] = project_id
        if boundary:
            parameters.update({"cursor_time": boundary[0], "cursor_id": boundary[1]})
            conditions.append("(updated_at,id)<(:cursor_time,:cursor_id)")
        try:
            async with self.engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT * FROM career.materials WHERE "
                                + " AND ".join(conditions)
                                + " ORDER BY updated_at DESC,id DESC LIMIT :limit"
                            ),
                            parameters,
                        )
                    )
                    .mappings()
                    .all()
                )
                items = tuple(material_from_row(row) for row in rows[:limit])
                next_cursor = (
                    encode_cursor(items[-1].updated_at, items[-1].id) if len(rows) > limit else None
                )
                return MaterialPage(items, next_cursor)
        except (DBAPIError, PoolTimeoutError):
            raise MaterialUnavailable("Material storage is unavailable") from None

    async def get(self, actor: ActorContext, material_id: UUID) -> MaterialDetail | None:
        try:
            async with self.engine.connect() as connection:
                connection = await connection.execution_options(isolation_level="REPEATABLE READ")
                async with connection.begin():
                    return await read_detail(connection, actor, material_id)
        except (DBAPIError, PoolTimeoutError):
            raise MaterialUnavailable("Material storage is unavailable") from None

    async def create(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        project_id: UUID | None,
        title: str,
        body: str,
        draft: MaterialDraft | None = None,
    ) -> MaterialDetail:
        version_id = uuid4()
        try:
            async with self.engine.begin() as connection:
                if project_id is not None:
                    owned = await connection.scalar(
                        text(
                            "SELECT 1 FROM career.career_projects "
                            "WHERE id=:id AND user_id=:user_id FOR KEY SHARE"
                        ),
                        {"id": project_id, "user_id": actor.user_id},
                    )
                    if owned is None:
                        raise MaterialNotFound("Related project does not exist")
                inserted = await connection.scalar(
                    text(
                        "INSERT INTO career.materials "
                        "(id,user_id,project_id,title,state,current_version_id,version) "
                        "VALUES (:id,:user_id,:project_id,:title,'active',:current,:version) "
                        "ON CONFLICT (id) DO NOTHING RETURNING id"
                    ),
                    {
                        "id": material_id,
                        "user_id": actor.user_id,
                        "project_id": project_id,
                        "title": title,
                        "current": version_id,
                        "version": uuid4(),
                    },
                )
                if inserted is None:
                    detail = await read_detail(connection, actor, material_id)
                    if (
                        detail is None
                        or detail.material.title != title
                        or detail.material.project_id != project_id
                    ):
                        raise MaterialConflict("Create ID already exists")
                    initial = min(detail.versions, key=lambda item: item.number)
                    initial_draft = next(
                        (
                            item
                            for item in detail.proposals
                            if item.id == uuid5(material_id, "initial-draft")
                        ),
                        None,
                    )
                    if (
                        initial.body != body
                        or bool(initial_draft) != bool(draft)
                        or (
                            draft
                            and initial_draft
                            and (
                                initial_draft.proposed_body,
                                initial_draft.rationale,
                                initial_draft.references,
                            )
                            != (draft.body, draft.rationale, draft.references)
                        )
                    ):
                        raise MaterialConflict("Create replay differs from original")
                    return detail
                await connection.execute(
                    text(
                        "INSERT INTO career.material_versions "
                        '(id,material_id,number,body,source,"references") '
                        "VALUES (:id,:material_id,:number,:body,:source,'[]'::jsonb)"
                    ),
                    {
                        "id": version_id,
                        "material_id": material_id,
                        "body": body,
                        "number": 0 if draft else 1,
                        "source": "seed" if draft else "user",
                    },
                )
                if draft:
                    await insert_proposal(
                        connection,
                        actor,
                        material_id,
                        proposal_id=uuid5(material_id, "initial-draft"),
                        base_version_id=version_id,
                        draft=draft,
                    )
                detail = await read_detail(connection, actor, material_id)
                if detail is None:
                    raise MaterialUnavailable("Material was not readable after save")
                return detail
        except (DBAPIError, PoolTimeoutError):
            raise MaterialUnavailable("Material could not be saved") from None

    async def create_version(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        base_version_id: UUID,
        body: str,
        source: MaterialSource,
    ) -> MaterialDetail | None:
        try:
            async with self.engine.begin() as connection:
                material = await lock_material(connection, actor, material_id)
                if material is None or material["current_version_id"] != base_version_id:
                    return None
                detail = await read_detail(connection, actor, material_id)
                if detail is None:
                    return None
                if detail.current_version.body == body:
                    return detail
                await insert_version(
                    connection, actor, material_id, body=body, source=source, references=()
                )
                return await read_detail(connection, actor, material_id)
        except (DBAPIError, PoolTimeoutError):
            raise MaterialUnavailable("Material version could not be saved") from None

    async def create_proposal(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        base_version_id: UUID,
        proposed_body: str,
        rationale: str,
        proposal_id: UUID,
        references: tuple[dict[str, str], ...],
    ) -> MaterialProposal | None:
        try:
            async with self.engine.begin() as connection:
                material = await lock_material(connection, actor, material_id)
                if material is None:
                    return None
                detail = await read_detail(connection, actor, material_id)
                if detail is None:
                    return None
                replay = next((item for item in detail.proposals if item.id == proposal_id), None)
                if replay:
                    return replay
                if material["current_version_id"] != base_version_id:
                    return None
                if detail.current_version.body == proposed_body:
                    raise MaterialInvalid("Proposal contains no changes")
                await insert_proposal(
                    connection,
                    actor,
                    material_id,
                    proposal_id=proposal_id,
                    base_version_id=base_version_id,
                    draft=MaterialDraft(proposed_body, rationale, references),
                )
                saved = await read_detail(connection, actor, material_id)
                if saved is None:
                    return None
                return next((item for item in saved.proposals if item.id == proposal_id), None)
        except (DBAPIError, PoolTimeoutError):
            raise MaterialUnavailable("Material proposal could not be saved") from None

    async def resolve_proposal(
        self,
        actor: ActorContext,
        *,
        material_id: UUID,
        proposal_id: UUID,
        state: str,
    ) -> MaterialDetail | None:
        try:
            async with self.engine.begin() as connection:
                material = await lock_material(connection, actor, material_id)
                if material is None:
                    return None
                detail = await read_detail(connection, actor, material_id)
                if detail is None:
                    return None
                proposal = next((item for item in detail.proposals if item.id == proposal_id), None)
                if proposal is None:
                    raise MaterialNotFound("Proposal does not exist")
                if proposal.state == state:
                    return detail
                if proposal.state != "pending":
                    return None
                if state == "accepted":
                    if material["current_version_id"] != proposal.base_version_id:
                        return None
                    await insert_version(
                        connection,
                        actor,
                        material_id,
                        body=proposal.proposed_body,
                        source="agent",
                        references=proposal.references,
                    )
                await connection.execute(
                    text(
                        "UPDATE career.material_proposals SET state=:state, "
                        "resolved_at=clock_timestamp() WHERE id=:id AND user_id=:user_id"
                    ),
                    {"state": state, "id": proposal_id, "user_id": actor.user_id},
                )
                return await read_detail(connection, actor, material_id)
        except (DBAPIError, PoolTimeoutError):
            raise MaterialUnavailable("Material proposal could not be resolved") from None
