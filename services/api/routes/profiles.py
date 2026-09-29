from dataclasses import asdict
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.api.application.context import ActorContext
from services.api.application.profiles import ProfileService
from services.api.domain.profile import CareerProfile, ProfileContent, ProfileEntry

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


class EntryBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    organization: str = Field(default="", max_length=200)
    period: str = Field(default="", max_length=100)
    details: str = Field(default="", max_length=4000)
    evidence: str = Field(default="", max_length=1000)


class ContentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(default="", max_length=100)
    education: list[EntryBody] = Field(default_factory=list, max_length=30)
    experience: list[EntryBody] = Field(default_factory=list, max_length=30)
    projects: list[EntryBody] = Field(default_factory=list, max_length=30)
    skills: str = Field(default="", max_length=4000)
    goals: str = Field(default="", max_length=4000)
    constraints: str = Field(default="", max_length=4000)

    def to_domain(self) -> ProfileContent:
        return ProfileContent(
            display_name=self.display_name,
            education=tuple(ProfileEntry(**entry.model_dump()) for entry in self.education),
            experience=tuple(ProfileEntry(**entry.model_dump()) for entry in self.experience),
            projects=tuple(ProfileEntry(**entry.model_dump()) for entry in self.projects),
            skills=self.skills,
            goals=self.goals,
            constraints=self.constraints,
        )


class SaveProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: ContentBody
    version: UUID | None
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def require_explicit_confirmation(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit confirmation is required")
        return value


class ProfileResponse(BaseModel):
    content: ContentBody
    version: UUID | None
    confirmed_at: str | None


def get_profile_service(request: Request) -> ProfileService:
    return cast(ProfileService, request.app.state.profile_service)


def get_actor(request: Request) -> ActorContext:
    request_id = str(uuid4())
    request.state.request_id = request_id
    return ActorContext(user_id=request.state.user_id, request_id=request_id)


def serialize_profile(profile: CareerProfile | None) -> ProfileResponse:
    if profile is None:
        return ProfileResponse(content=ContentBody(), version=None, confirmed_at=None)
    return ProfileResponse(
        content=ContentBody.model_validate(asdict(profile.content)),
        version=profile.version,
        confirmed_at=profile.confirmed_at.isoformat(),
    )


@router.get("", response_model=ProfileResponse)
async def read_profile(
    response: Response,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_profile(await service.read(actor))


@router.put("", response_model=ProfileResponse)
async def save_profile(
    body: SaveProfileBody,
    response: Response,
    service: Annotated[ProfileService, Depends(get_profile_service)],
    actor: Annotated[ActorContext, Depends(get_actor)],
) -> ProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    return serialize_profile(
        await service.confirm(
            actor, body.content.to_domain(), body.version, confirmed=body.confirmed
        )
    )
