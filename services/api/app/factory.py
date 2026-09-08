from collections.abc import Callable
from typing import Protocol

from fastapi import FastAPI

from services.api.app.settings import Settings
from services.api.infrastructure.agent_runtime import build_agent_os
from services.api.infrastructure.authentication import JwtAuthenticationMiddleware
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
    return app
