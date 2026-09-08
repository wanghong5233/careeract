import asyncio
from collections.abc import Collection

import jwt
from jwt import (
    InvalidTokenError,
    PyJWKClient,
    PyJWKClientConnectionError,
    PyJWKClientError,
)
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class JwtAuthenticationMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        algorithms: Collection[str],
        jwks_timeout_seconds: float,
        public_paths: Collection[str],
        protected_path_prefixes: Collection[str],
    ) -> None:
        self.app = app
        self.jwks_client = PyJWKClient(jwks_url, timeout=jwks_timeout_seconds)
        self.issuer = issuer
        self.audience = audience
        self.algorithms = list(algorithms)
        self.public_paths = frozenset(public_paths)
        self.protected_path_prefixes = tuple(protected_path_prefixes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.public_paths:
            await self.app(scope, receive, send)
            return

        if not scope["path"].startswith(self.protected_path_prefixes):
            response = JSONResponse({"error": "Not found"}, status_code=404)
            await response(scope, receive, send)
            return

        headers = Headers(scope=scope)
        scheme, _, token = headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            await self._unauthorized(scope, receive, send)
            return

        try:
            signing_key = await asyncio.to_thread(
                self.jwks_client.get_signing_key_from_jwt,
                token,
            )
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=self.algorithms,
                audience=self.audience,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
        except PyJWKClientConnectionError:
            response = JSONResponse(
                {"error": "Authentication service unavailable"},
                status_code=503,
                headers={"Retry-After": "5"},
            )
            await response(scope, receive, send)
            return
        except (InvalidTokenError, PyJWKClientError, ValueError):
            await self._unauthorized(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        state["user_id"] = payload["sub"]
        state["user_isolation_enabled"] = True
        state["scopes"] = []
        state["dependencies"] = {"email": payload.get("email")}
        state["session_state"] = {}
        state["audience"] = self.audience
        await self.app(scope, receive, send)

    @staticmethod
    async def _unauthorized(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse({"error": "Unauthorized"}, status_code=401)
        await response(scope, receive, send)
