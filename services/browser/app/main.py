import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.ext.asyncio import create_async_engine

from services.browser.app.factory import create_app
from services.browser.app.settings import settings
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.profiles import PostgresBrowserProfileStore, ProfileCipher
from services.browser.sessions.site_safety import PostgresSiteSafetyStore
from services.browser.sessions.steel import SteelSessionManager
from services.browser.site_adapters.boss_lifecycle import boss_site_lifecycles
from services.browser.site_adapters.boss_login import BossLoginNavigator
from services.browser.site_adapters.boss_profile import BOSS_SCOPE, BossProfileCapture

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
    boss_safety = PostgresSiteSafetyStore(engine, BOSS_SCOPE)
    app = create_app(
        verifier=CommandVerifier(public_key),
        store=PostgresLeaseStore(engine),
        steel_client=steel_client,
        steel_sessions=SteelSessionManager(steel_client, engine),
        viewer_public_origin=settings.viewer_public_origin,
        site_lifecycles=boss_site_lifecycles(
            navigator=BossLoginNavigator(
                steel_client, settings.steel_cdp_url, risk_guard=boss_safety.action_guard
            ),
            profiles=(
                PostgresBrowserProfileStore(
                    engine, ProfileCipher.from_file(settings.browser_profile_key_file), BOSS_SCOPE
                )
                if settings.browser_profile_key_file is not None
                else None
            ),
            reader=lambda session_id: BossProfileCapture(
                steel_client,
                settings.steel_cdp_url,
                session_id,
                risk_stop=lambda reason: boss_safety.record_stop(session_id, reason),
            ),
        ),
    )
app.state.settings = settings
