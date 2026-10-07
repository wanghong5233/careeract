import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from services.api.application.ports.browser_control import (
    BrowserControlConflict,
    BrowserControlRejected,
)
from services.api.infrastructure.browser_control import BrowserCommandSigner, BrowserControlClient
from services.browser.app.factory import create_app
from services.browser.sessions.authentication import (
    BrowserCommand,
    CommandRejected,
    CommandVerifier,
)
from services.browser.sessions.lease import LeaseConflict
from services.browser.sessions.postgres import PostgresLeaseStore
from tests.api.test_browser_control import control_context
from tests.browser.test_command_authentication import command_payload

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_POSTGRES_TESTS") != "1",
    reason="Opt-in isolated Docker PostgreSQL integration",
)
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_viewer_lease_excludes_executors_and_requires_confirmed_stop(
    database_url: str,
) -> None:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    command = BrowserCommand.model_validate(command_payload() | {"action": "viewer"})
    await store.register(command.session_id, command.sub, command.task_id, command.authorization_id)
    executor = command.model_copy(update={"action": "acquire", "jti": uuid4()})
    try:
        lease = await store.acquire_viewer(command)
        with pytest.raises(LeaseConflict):
            await store.execute(executor)
        with pytest.raises(LeaseConflict):
            await store.acquire_viewer(command.model_copy(update={"jti": uuid4()}))
        await store.renew_viewer(command, lease.lease_id)
        await store.check_viewer(command, lease.lease_id)
        with pytest.raises(LeaseConflict):
            await store.drain_viewer(
                command.model_copy(update={"attempt_id": uuid4()}), lease.lease_id
            )
        await store.drain_viewer(command, lease.lease_id)
        with pytest.raises(LeaseConflict):
            await store.execute(executor)
        with pytest.raises(LeaseConflict):
            await store.renew_viewer(command, lease.lease_id)
        await store.confirm_stopped(command.session_id, lease.lease_id)
        with pytest.raises(CommandRejected):
            await store.acquire_viewer(command)
        executor_lease = await store.execute(executor)
        with pytest.raises(LeaseConflict):
            await store.authorize_viewer(command)
        with pytest.raises(LeaseConflict):
            await store.drain_viewer(command, lease.lease_id)
        await store.execute(
            executor.model_copy(
                update={"action": "stop", "lease_id": executor_lease.lease_id, "jti": uuid4()}
            )
        )
        await store.confirm_stopped(command.session_id, executor_lease.lease_id)
        replacement = command.model_copy(update={"jti": uuid4(), "attempt_id": uuid4()})
        viewer_lease = await store.acquire_viewer(replacement)
        await store.revoke(command.session_id)
        with pytest.raises(CommandRejected):
            await store.renew_viewer(replacement, viewer_lease.lease_id)
        await store.drain_viewer(replacement, viewer_lease.lease_id)
        await store.confirm_stopped(command.session_id, viewer_lease.lease_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_viewer_retains_ownership_until_disconnect(database_url: str) -> None:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    command = BrowserCommand.model_validate(command_payload() | {"action": "viewer"})
    await store.register(command.session_id, command.sub, command.task_id, command.authorization_id)
    try:
        lease = await store.acquire_viewer(command)
        expired = command.model_copy(update={"iat": 1, "exp": 61})
        with pytest.raises(CommandRejected):
            await store.renew_viewer(expired, lease.lease_id)
        with pytest.raises(LeaseConflict):
            await store.execute(command.model_copy(update={"action": "acquire", "jti": uuid4()}))
        await store.drain_viewer(expired, lease.lease_id)
        await store.confirm_stopped(command.session_id, lease.lease_id)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    container = "careeract-lease-test-" + uuid4().hex[:12]
    working = tmp_path_factory.mktemp("browser-database")
    image = next(
        line.strip().removeprefix("image: ")
        for line in (ROOT / "compose.yaml").read_text().splitlines()
        if "image: postgres:" in line
    )

    def docker(*args: str) -> str:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, check=True, timeout=60
        ).stdout.strip()

    try:
        docker(
            "run",
            "-d",
            "--name",
            container,
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "-e",
            "POSTGRES_DB=lease_test",
            "-p",
            "127.0.0.1::5432",
            image,
        )
        for attempt in range(30):
            ready = subprocess.run(
                ["docker", "exec", container, "pg_isready", "-U", "postgres"],
                capture_output=True,
                timeout=5,
            )
            if ready.returncode == 0:
                break
            if attempt == 29:
                pytest.fail("Isolated PostgreSQL did not become ready")
            time.sleep(1)
        port = docker("port", container, "5432/tcp").rsplit(":", 1)[1]
        url = f"postgresql+asyncpg://postgres@127.0.0.1:{port}/lease_test"
        environment = dict(os.environ) | {
            "PYTHONPATH": str(ROOT),
            "DATABASE_URL": url,
        }

        def migrate(*args: str) -> None:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    str(ROOT / "services/api/alembic.ini"),
                    *args,
                ],
                cwd=working,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr

        migrate("upgrade", "0001_auth_schema")

        async def auth_data(*, insert: bool) -> None:
            engine = create_async_engine(url)
            try:
                async with engine.begin() as connection:
                    if insert:
                        await connection.execute(
                            text(
                                'INSERT INTO auth."user" (id, name, email, "emailVerified") '
                                "VALUES ('migration-probe', 'Synthetic', "
                                "'probe@example.invalid', false)"
                            )
                        )
                    else:
                        assert (
                            await connection.scalar(
                                text(
                                    "SELECT count(*) FROM auth.\"user\" WHERE id='migration-probe'"
                                )
                            )
                            == 1
                        )
            finally:
                await engine.dispose()

        asyncio.run(auth_data(insert=True))
        migrate("upgrade", "head")
        migrate("downgrade", "0001_auth_schema")
        migrate("upgrade", "head")
        asyncio.run(auth_data(insert=False))
        migrate("upgrade", "head")
        yield url
    finally:
        docker("rm", "-f", container)


@pytest.mark.asyncio
async def test_signed_http_commands_and_durable_handoff(database_url: str) -> None:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    key = Ed25519PrivateKey.generate()
    verifier = CommandVerifier(key.public_key())
    payload = command_payload()
    session_id = UUID(str(payload["session_id"]))
    await store.register(
        session_id,
        str(payload["sub"]),
        UUID(str(payload["task_id"])),
        UUID(str(payload["authorization_id"])),
    )

    async def send(client: httpx.AsyncClient, **changes: object) -> httpx.Response:
        values = payload | {"jti": str(uuid4())} | changes
        token = jwt.encode(values, key, algorithm="EdDSA")
        return await client.post(
            f"/internal/v1/sessions/{session_id}/lease/{values['action']}",
            headers={"Authorization": "Bearer " + token},
        )

    try:
        app = create_app(verifier=verifier, store=store)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (
                await client.post(f"/internal/v1/sessions/{session_id}/lease/acquire")
            ).status_code == 401
            for claim in ["sub", "task_id", "authorization_id"]:
                assert (await send(client, **{claim: str(uuid4())})).status_code == 403
            acquired = await send(client, jti=payload["jti"])
            assert acquired.status_code == 200
            lease_id = acquired.json()["lease_id"]
            assert (await send(client, jti=payload["jti"])).status_code == 403
            assert (await send(client)).status_code == 409
            await engine.dispose()
            assert (await send(client)).status_code == 409
            assert (await send(client, action="check", lease_id=lease_id)).status_code == 200
            assert (
                await send(client, action="renew", lease_id=lease_id, attempt_id=str(uuid4()))
            ).status_code == 409
            assert (await send(client, action="renew", lease_id=lease_id)).status_code == 200
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE browser.sessions "
                        "SET expires_at=clock_timestamp()-interval '1 second' "
                        "WHERE session_id=:session"
                    ),
                    {"session": session_id},
                )
            assert (await send(client, action="check", lease_id=lease_id)).status_code == 409
            assert (await send(client, action="renew", lease_id=lease_id)).status_code == 409
            assert (await send(client)).status_code == 409
            with pytest.raises(LeaseConflict):
                await store.confirm_stopped(session_id, UUID(lease_id))
            assert (await send(client, action="stop", lease_id=lease_id)).status_code == 200
            assert (await send(client)).status_code == 409
            await store.confirm_stopped(session_id, UUID(lease_id))
            assert (await send(client, jti=payload["jti"])).status_code == 403
            replacement = await send(client)
            assert replacement.status_code == 200
            assert replacement.json()["lease_id"] != lease_id
            assert (await send(client, action="stop", lease_id=lease_id)).status_code == 409
            await store.revoke(session_id)
            assert (
                await send(client, action="check", lease_id=replacement.json()["lease_id"])
            ).status_code == 403
            assert (await send(client)).status_code == 403
            await engine.dispose()
            assert (await send(client)).status_code == 403
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_api_signer_to_live_browser_and_revoke_before_register(
    database_url: str, tmp_path: Path
) -> None:
    from dataclasses import replace

    private_key = Ed25519PrivateKey.generate()
    public_key_file = tmp_path / "command-public.pem"
    public_key_file.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    environment = dict(os.environ) | {
        "PYTHONPATH": str(ROOT),
        "BROWSER_DATABASE_URL": database_url,
        "BROWSER_COMMAND_PUBLIC_KEY_FILE": str(public_key_file),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "services.browser.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
            for attempt in range(60):
                if process.poll() is not None:
                    pytest.fail("Isolated Browser process exited during startup")
                try:
                    if (await client.get("/health")).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                if attempt == 59:
                    pytest.fail("Isolated Browser process did not become ready")
                await asyncio.sleep(0.1)
            adapter = BrowserControlClient(client, BrowserCommandSigner(private_key))
            context = control_context()
            await adapter.send(context, "register")
            with pytest.raises(BrowserControlConflict):
                await adapter.send(context, "register")
            with pytest.raises(BrowserControlRejected):
                await adapter.send(replace(context, user_id="another-user"), "revoke")
            lease = await adapter.send(context, "acquire")
            assert lease is not None
            assert await adapter.send(context, "check", lease.lease_id) is not None
            old_token = adapter.signer.sign(context, "renew", lease.lease_id)
            await adapter.send(context, "revoke")
            await adapter.send(context, "revoke")
            result = await client.post(
                f"/internal/v1/sessions/{context.session_id}/lease/renew",
                headers={"Authorization": "Bearer " + old_token},
            )
            assert result.status_code == 403
            with pytest.raises(BrowserControlConflict):
                await adapter.send(context, "register")
            late = control_context()
            delayed_registration = adapter.signer.sign(late, "register")
            await adapter.send(late, "revoke")
            delayed_result = await client.post(
                f"/internal/v1/sessions/{late.session_id}/register",
                headers={"Authorization": "Bearer " + delayed_registration},
            )
            assert delayed_result.status_code == 409
            with pytest.raises(BrowserControlConflict):
                await adapter.send(late, "register")
            with pytest.raises(BrowserControlRejected):
                await adapter.send(late, "acquire")
            racing = control_context()
            registration, revocation = await asyncio.gather(
                adapter.send(racing, "register"),
                adapter.send(racing, "revoke"),
                return_exceptions=True,
            )
            assert registration is None or isinstance(registration, BrowserControlConflict)
            assert revocation is None
            with pytest.raises(BrowserControlRejected):
                await adapter.send(racing, "acquire")
            wrong_signer = BrowserControlClient(
                client, BrowserCommandSigner(Ed25519PrivateKey.generate())
            )
            with pytest.raises(BrowserControlRejected):
                await wrong_signer.send(control_context(), "register")
    finally:
        process.terminate()
        try:
            await asyncio.to_thread(process.wait, timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait, timeout=5)


@pytest.mark.asyncio
async def test_two_processes_compete_and_restart_keeps_owner(database_url: str) -> None:
    engine = create_async_engine(database_url)
    store = PostgresLeaseStore(engine)
    key = Ed25519PrivateKey.generate()
    payload = command_payload()
    session_id = UUID(str(payload["session_id"]))
    await store.register(
        session_id,
        str(payload["sub"]),
        UUID(str(payload["task_id"])),
        UUID(str(payload["authorization_id"])),
    )
    code = """
import asyncio, json, sys, time
from uuid import UUID
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from sqlalchemy.ext.asyncio import create_async_engine
from services.browser.sessions.authentication import CommandVerifier
from services.browser.sessions.postgres import PostgresLeaseStore
from services.browser.sessions.lease import LeaseConflict
data = json.load(sys.stdin)
async def run():
    engine = create_async_engine(data["url"])
    command = CommandVerifier(load_pem_public_key(data["key"].encode())).verify(
        data["token"], UUID(data["session"]), "acquire")
    await asyncio.sleep(max(0, data["start"]-time.time()))
    try:
        await PostgresLeaseStore(engine).execute(command)
        print("acquired")
    except LeaseConflict:
        print("conflict")
    finally:
        await engine.dispose()
asyncio.run(run())
"""
    public_key = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    start = time.time() + 3

    def compete(owner: str) -> str:
        token = jwt.encode(
            payload | {"owner_id": owner, "jti": str(uuid4())}, key, algorithm="EdDSA"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            input=json.dumps(
                {
                    "url": database_url,
                    "key": public_key,
                    "token": token,
                    "session": str(session_id),
                    "start": start,
                }
            ),
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=20,
            check=True,
        )
        return result.stdout.strip()

    try:
        results = await asyncio.gather(
            asyncio.to_thread(compete, "executor-a"), asyncio.to_thread(compete, "executor-b")
        )
        assert sorted(results) == ["acquired", "conflict"]
        assert await asyncio.to_thread(compete, "new-process") == "conflict"
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM browser.commands WHERE session_id=:session"),
                    {"session": session_id},
                )
                == 1
            )
        await store.revoke(session_id)
        token = jwt.encode(payload, key, algorithm="EdDSA")
        with pytest.raises(CommandRejected):
            await store.execute(
                CommandVerifier(key.public_key()).verify(token, session_id, "acquire")
            )
    finally:
        await engine.dispose()
