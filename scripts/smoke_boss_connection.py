import argparse
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


def check(base_url: str) -> None:
    address = urlsplit(base_url)
    if address.scheme != "http" or address.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Use a local HTTP development server")
    origin = f"{address.scheme}://{address.netloc}"
    with (
        httpx.Client(base_url=origin, timeout=30, trust_env=False) as first,
        httpx.Client(base_url=origin, timeout=30, trust_env=False) as second,
    ):
        assert first.get("/api/connections/boss").status_code == 401
        for client in (first, second):
            signup = client.post(
                "/api/auth/sign-up/email",
                headers={"Origin": origin},
                json={
                    "name": "Synthetic BOSS connection test",
                    "email": "boss-smoke-" + uuid4().hex + "@example.invalid",
                    "password": secrets.token_urlsafe(32),
                },
            )
            assert signup.status_code == 200, "Synthetic signup failed"
        try:
            key = str(uuid4())
            headers = {"Origin": origin, "Idempotency-Key": key}
            assert first.get("/api/connections/boss").json() is None
            assert first.post("/api/connections/boss", json={}).status_code == 403
            created = first.post("/api/connections/boss", headers=headers, json={})
            assert created.status_code == 201, "Product connection request failed"
            current = created.json()
            assert current["status"] == "pending" and current["browser_session_id"] is None
            assert created.headers["cache-control"] == "no-store"
            assert first.get("/api/connections/boss").json() == current
            assert first.post("/api/connections/boss", headers=headers, json={}).json() == current
            assert second.get("/api/connections/boss").json() is None
            path = "/api/connections/boss/" + current["id"]
            payload = {"version": current["version"]}
            assert (
                second.request("DELETE", path, headers={"Origin": origin}, json=payload).status_code
                == 404
            )
            assert (
                first.request(
                    "DELETE", path, headers={"Origin": origin}, json={"version": str(uuid4())}
                ).status_code
                == 409
            )
            revoked = first.request("DELETE", path, headers={"Origin": origin}, json=payload)
            assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
            assert first.get("/api/connections/boss").json() == revoked.json()
            assert (
                first.post("/api/connections/boss", headers=headers, json={}).json()
                == revoked.json()
            )
        finally:
            for client in (first, second):
                assert (
                    client.post(
                        "/api/auth/sign-out", headers={"Origin": origin}, json={}
                    ).status_code
                    == 200
                )
        assert first.get("/api/connections/boss").status_code == 401
    print(
        "PASS: real Better Auth/BFF/JWT/API/PostgreSQL request, persistence, "
        "idempotency, isolation, version checks and revoke; no BOSS access"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate local BOSS connection request lifecycle")
    parser.add_argument("--base-url", default="http://localhost:43110")
    check(parser.parse_args().base_url)
