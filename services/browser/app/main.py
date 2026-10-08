import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.ext.asyncio import create_async_engine

from services.browser.app.factory import create_app
from services.browser.app.settings import settings
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.profiles import PostgresBrowserProfileStore, ProfileCipher
from services.browser.sessions.steel import SteelSessionManager
from services.browser.site_adapters.boss_context import BOSS_SCOPE, BossContextReader
from services.browser.site_adapters.boss_login import BossLoginNavigator

if settings.browser_database_url is None and settings.browser_command_public_key_file is None:
    app = create_app()
elif settings.browser_database_url is None or settings.browser_command_public_key_file is None:
    raise RuntimeError("Browser control requires both database and public key configuration")
else:
    public_key = serialization.load_pem_public_key(
        settings.browser_command_public_key_file.read_bytes()
    )
    if not isinstance(public_key, Ed25519PublicKey):
        raise RuntimeError("Browser command public key must be Ed25519")
    engine = create_async_engine(
        settings.browser_database_url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"timeout": 5, "command_timeout": 10},
    )
    steel_client = httpx.AsyncClient(
        base_url=str(settings.steel_base_url),
        follow_redirects=False,
        timeout=40,
    )
    app = create_app(
        verifier=CommandVerifier(public_key),
        store=PostgresLeaseStore(engine),
        steel_client=steel_client,
        steel_sessions=SteelSessionManager(steel_client, engine),
        viewer_public_origin=settings.viewer_public_origin,
        login_navigator=BossLoginNavigator(steel_client, settings.steel_cdp_url),
        profiles=(
            PostgresBrowserProfileStore(
                engine, ProfileCipher.from_file(settings.browser_profile_key_file), BOSS_SCOPE
            )
            if settings.browser_profile_key_file is not None
            else None
        ),
        context_reader=lambda session_id: BossContextReader(
            steel_client, settings.steel_cdp_url, session_id
        ),
    )
app.state.settings = settings
