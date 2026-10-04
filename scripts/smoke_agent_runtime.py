import argparse
import json
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx


def checked(response: httpx.Response, status: int = 200) -> dict:
    if response.status_code != status:
        raise RuntimeError(f"{response.request.url.path}: HTTP {response.status_code}")
    return response.json()


def payload(session_id: str, content: str) -> dict:
    return {
        "threadId": session_id,
        "runId": str(uuid4()),
        "messages": [{"id": str(uuid4()), "role": "user", "content": content}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


def stream_events(response: httpx.Response):
    for line in response.iter_lines():
        if line.startswith("data:"):
            yield json.loads(line[5:])


def history(client: httpx.Client, session_id: str) -> dict:
    return checked(client.get("/api/agent/history", params={"session_id": session_id}))


def wait_terminal(client: httpx.Client, session_id: str, run_id: str) -> dict:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        snapshot = history(client, session_id)
        run = next(item for item in snapshot["runs"] if item["run_id"] == run_id)
        if run["status"] in {"COMPLETED", "CANCELLED", "ERROR", "REGENERATED"}:
            return snapshot
        time.sleep(0.25)
    raise RuntimeError("Run did not reach a stored terminal state; do not replay")


def send(client: httpx.Client, session_id: str, content: str) -> tuple[str, dict]:
    request = payload(session_id, content)
    reply = ""
    terminal = None
    chunks = 0
    with client.stream("POST", "/api/agent", json=request) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Text run HTTP {response.status_code}")
        for event in stream_events(response):
            if event["type"] == "TEXT_MESSAGE_CONTENT":
                reply += event["delta"]
                chunks += 1
            if event["type"] in {"RUN_FINISHED", "RUN_ERROR"}:
                terminal = event["type"]
    if terminal != "RUN_FINISHED":
        raise RuntimeError(f"Unexpected stream terminal {terminal}; do not replay")
    snapshot = wait_terminal(client, session_id, request["runId"])
    assert (
        next(run for run in snapshot["runs"] if run["run_id"] == request["runId"])["status"]
        == "COMPLETED"
    )
    checked(client.post("/api/agent", json=request), 409)
    print(f"PASS: stored COMPLETED, SSE text chunks={chunks}, replay rejected", flush=True)
    return reply, snapshot


def check(base_url: str) -> None:
    address = urlsplit(base_url)
    if address.scheme != "http" or address.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("Use a local HTTP development server")
    with (
        httpx.Client(
            base_url=base_url, headers={"Origin": base_url}, timeout=90, trust_env=False
        ) as first,
        httpx.Client(
            base_url=base_url, headers={"Origin": base_url}, timeout=90, trust_env=False
        ) as second,
    ):
        for client in (first, second):
            checked(
                client.post(
                    "/api/auth/sign-up/email",
                    json={
                        "name": "Synthetic Agent Runtime",
                        "email": f"runtime-{uuid4().hex}@example.invalid",
                        "password": secrets.token_urlsafe(24),
                    },
                )
            )
        checked(
            first.put(
                "/api/profile",
                json={
                    "version": None,
                    "confirmed": True,
                    "content": {"display_name": "合成用户", "goals": "SYNTHETIC_GOAL_ORBIT"},
                },
            )
        )
        projects = [
            checked(first.post("/api/projects", json={"id": str(uuid4()), "title": title}), 201)
            for title in ("合成项目 A", "合成项目 B")
        ]

        def rule(title: str, project_id: str | None = None) -> dict:
            return checked(
                first.post(
                    "/api/memories",
                    json={
                        "kind": "rule",
                        "title": title,
                        "content": "仅用于合成验收，不改变外部操作权限。",
                        "project_id": project_id,
                    },
                ),
                201,
            )

        rules = [
            rule("SYNTHETIC_RULE_A", projects[0]["id"]),
            rule("SYNTHETIC_RULE_B", projects[1]["id"]),
        ]
        for index, item in enumerate(rules):
            rules[index] = checked(
                first.post(f"/api/memories/{item['id']}/confirm", json={"version": item["version"]})
            )
        personal = rule("SYNTHETIC_PERSONAL_RULE")
        conversations = [
            checked(
                first.post(
                    "/api/agent/conversations",
                    json={"id": str(uuid4()), "title": "合成验收", "project_id": projects[0]["id"]},
                ),
                201,
            )
            for _ in range(2)
        ]
        session_id = conversations[0]["session_id"]
        checked(second.get("/api/agent/history", params={"session_id": session_id}), 404)
        checked(
            second.post(
                f"/api/agent/conversations/{session_id}/cancel", json={"run_id": "unknown"}
            ),
            404,
        )
        query = (
            "调用 read_career_context，输出职业目标及当前 confirmed_rules 的标题，"
            "候选和历史旧规则不列入。"
        )
        reply, _ = send(
            first, session_id, query + "本对话合成校验词是 SYNTHETIC_CHAT_COMET，请记住。"
        )
        assert "SYNTHETIC_GOAL_ORBIT" in reply and "SYNTHETIC_RULE_A" in reply
        assert "SYNTHETIC_RULE_B" not in reply and "SYNTHETIC_PERSONAL_RULE" not in reply
        reply, _ = send(first, session_id, "只输出上一轮提供的本对话合成校验词，不调用工具。")
        assert "SYNTHETIC_CHAT_COMET" in reply
        reply, isolated = send(
            first, conversations[1]["session_id"], query + "若没有当前对话校验词，请勿猜测。"
        )
        assert "SYNTHETIC_GOAL_ORBIT" in reply and "SYNTHETIC_CHAT_COMET" not in reply
        assert all("SYNTHETIC_CHAT_COMET" not in item["content"] for item in isolated["messages"])
        print(
            "PASS: multi-turn, separate conversations, shared owned profile, candidate excluded",
            flush=True,
        )
        personal = checked(
            first.post(
                f"/api/memories/{personal['id']}/confirm", json={"version": personal["version"]}
            )
        )
        reply, _ = send(first, session_id, query)
        assert "SYNTHETIC_PERSONAL_RULE" in reply
        checked(
            first.post(
                f"/api/memories/{personal['id']}/retire", json={"version": personal["version"]}
            )
        )
        conversations[0] = checked(
            first.patch(
                f"/api/agent/conversations/{session_id}",
                json={"version": conversations[0]["version"], "project_id": projects[1]["id"]},
            )
        )
        reply, _ = send(first, session_id, query)
        assert "SYNTHETIC_RULE_B" in reply and "SYNTHETIC_RULE_A" not in reply
        assert "SYNTHETIC_PERSONAL_RULE" not in reply
        print("PASS: next-run confirm/retire and project switch scope", flush=True)

        request = payload(
            session_id, "合成停止测试，请逐行列出 1 到 500，每行写一条说明，不调用工具。"
        )
        with first.stream("POST", "/api/agent", json=request) as response:
            assert response.status_code == 200
            for event in stream_events(response):
                if event["type"] != "TEXT_MESSAGE_CONTENT":
                    continue
                snapshot = history(first, session_id)
                assert any(
                    item["run_id"] == request["runId"] and item["status"] in {"RUNNING", "PENDING"}
                    for item in snapshot["runs"]
                )
                checked(first.post("/api/agent", json=request), 409)
                checked(
                    first.post(
                        f"/api/agent/conversations/{session_id}/cancel",
                        json={"run_id": request["runId"]},
                    )
                )
                break
        cancelled = wait_terminal(first, session_id, request["runId"])
        assert (
            next(item for item in cancelled["runs"] if item["run_id"] == request["runId"])["status"]
            == "CANCELLED"
        )
        assert all(
            item["run_status"] == "CANCELLED"
            for item in cancelled["messages"]
            if item["run_id"] == request["runId"]
        )
        print(
            "PASS: running status, duplicate rejection, server cancel, retained CANCELLED history",
            flush=True,
        )
        request = payload(session_id, "合成断流测试，只输出从 1 到 30 的数字。")
        with first.stream("POST", "/api/agent", json=request) as response:
            assert response.status_code == 200
            for event in stream_events(response):
                if event["type"] == "TEXT_MESSAGE_CONTENT":
                    break
        completed = wait_terminal(first, session_id, request["runId"])
        assert (
            next(item for item in completed["runs"] if item["run_id"] == request["runId"])["status"]
            == "COMPLETED"
        )
        checked(first.post("/api/agent", json=request), 409)
        print(
            "PASS: closed HTTP stream continues in live API process; saved terminal can be re-read",
            flush=True,
        )
        for client in (first, second):
            checked(client.post("/api/auth/sign-out", json={}))
    print(
        "HTTP integration only: does not replace visible browser or process-restart acceptance",
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:3100")
    check(parser.parse_args().base_url)
