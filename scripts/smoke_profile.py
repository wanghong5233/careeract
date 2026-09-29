import argparse
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


def check(base_url: str) -> None:
    address = urlsplit(base_url)
    if address.scheme != "http" or address.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Use a local HTTP development or isolated smoke server")
    origin = f"{address.scheme}://{address.netloc}"
    with (
        httpx.Client(base_url=origin, timeout=30, trust_env=False) as first,
        httpx.Client(base_url=origin, timeout=30, trust_env=False) as second,
    ):
        assert first.get("/api/profile").status_code == 401
        for client in (first, second):
            response = client.post(
                "/api/auth/sign-up/email",
                headers={"Origin": origin},
                json={
                    "name": "Synthetic profile test",
                    "email": "profile-smoke-" + uuid4().hex + "@example.invalid",
                    "password": secrets.token_urlsafe(32),
                },
            )
            assert response.status_code == 200, "Synthetic signup failed"
        content = {
            "display_name": "虚构档案",
            "education": [{"title": "测试学位", "organization": "测试学校"}],
            "experience": [{"title": "测试实习", "details": "合成数据"}],
            "projects": [{"title": "测试项目", "evidence": "合成报告"}],
            "skills": "Python",
            "goals": "平台开发",
            "constraints": "测试城市",
        }
        payload = {"content": content, "version": None, "confirmed": True}
        assert first.put("/api/profile", json=payload).status_code == 403
        assert (
            first.put(
                "/api/profile", json=payload, headers={"Origin": "http://untrusted.invalid"}
            ).status_code
            == 403
        )
        saved = first.put("/api/profile", json=payload, headers={"Origin": origin})
        assert saved.status_code == 200, "Profile save failed"
        assert saved.headers["cache-control"] == "no-store"
        version = saved.json()["version"]
        assert first.get("/api/profile").json() == saved.json(), "Reload lost saved profile"
        assert second.get("/api/profile").json()["version"] is None
        assert (
            second.put(
                "/api/profile", json=payload | {"version": version}, headers={"Origin": origin}
            ).status_code
            == 409
        )
        assert (
            first.put(
                "/api/profile",
                json=payload | {"user_id": "someone-else"},
                headers={"Origin": origin},
            ).status_code
            == 422
        )
        updated = first.put(
            "/api/profile",
            json=payload | {"content": content | {"goals": "新目标"}, "version": version},
            headers={"Origin": origin},
        )
        assert updated.status_code == 200
        assert updated.json()["version"] != version
        assert (
            first.put(
                "/api/profile", json=payload | {"version": version}, headers={"Origin": origin}
            ).status_code
            == 409
        )
        assert first.get("/api/profile").json() == updated.json()
        assert (
            first.post("/api/auth/sign-out", headers={"Origin": origin}, json={}).status_code == 200
        )
        assert first.get("/api/profile").status_code == 401
        assert (
            second.post("/api/auth/sign-out", headers={"Origin": origin}, json={}).status_code
            == 200
        )
    print(
        "PASS: real signup/session/BFF/JWT/API/PostgreSQL profile save, reload, "
        "ownership, stale writes, Origin checks and signout"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the local career profile vertical slice")
    parser.add_argument("--base-url", default="http://localhost:3100")
    args = parser.parse_args()
    check(args.base_url)
