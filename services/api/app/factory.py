from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from services.api.app.settings import Settings
from services.api.application.profiles import ProfileService
from services.api.domain.profile import ProfileConflict, ProfileUnavailable
from services.api.infrastructure.agent_runtime import build_agent_os
from services.api.infrastructure.authentication import JwtAuthenticationMiddleware
from services.api.infrastructure.database import create_engine
from services.api.infrastructure.profiles import PostgresProfileRepository
from services.api.routes.errors import profile_error
from services.api.routes.profiles import router as profile_router
from services.api.routes.system import router as system_router

PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json"})
PROTECTED_PATH_PREFIXES = ("/agui", "/status", "/api/")


class AgentRuntime(Protocol):
    def get_app(self) -> FastAPI: ...


RuntimeFactory = Callable[[Settings], AgentRuntime]


def create_app(
    settings: Settings,
    runtime_factory: RuntimeFactory = build_agent_os,
) -> FastAPI:
    agent_os = runtime_factory(settings)
    app = agent_os.get_app()
    engine = create_engine(settings)
    runtime_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            async with runtime_lifespan(application):
                yield
        finally:
            await engine.dispose()

    app.router.lifespan_context = lifespan
    app.state.profile_service = ProfileService(PostgresProfileRepository(engine))
    app.state.settings = settings
    app.state.agent_os = agent_os
    app.add_middleware(
        JwtAuthenticationMiddleware,
        jwks_url=str(settings.auth_jwks_url),
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
        algorithms=settings.auth_jwt_algorithms,
        jwks_timeout_seconds=settings.auth_jwks_timeout_seconds,
        public_paths=PUBLIC_PATHS,
        protected_path_prefixes=PROTECTED_PATH_PREFIXES,
    )
    app.include_router(system_router)
    app.include_router(profile_router)
    app.add_exception_handler(ProfileConflict, profile_error)
    app.add_exception_handler(ProfileUnavailable, profile_error)
    app.add_exception_handler(RequestValidationError, profile_error)
    return app
