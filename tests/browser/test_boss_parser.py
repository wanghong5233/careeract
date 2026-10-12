import pytest

from services.browser.site_adapters.boss import (
    BossConversationSummary,
    BossJobSummary,
    BossMessageSummary,
    BossPageKind,
    BossPageState,
    parse_boss_page,
)


def test_job_list_extracts_structured_summaries_and_source_urls() -> None:
    page = parse_boss_page(
        html="""
        <main data-page="jobs">
          <article class="job-card" data-job-id="job-1">
            <a href="/job_detail/job-1.html"><span data-field="title">AI Agent Engineer</span></a>
            <span data-field="company">Example Labs</span>
            <span data-field="location">北京·朝阳</span>
            <span data-field="salary">25-40K</span>
          </article>
        </main>
        """,
        url="https://www.zhipin.com/web/geek/jobs",
        title="BOSS直聘",
    )

    assert page.kind == BossPageKind.JOB_LIST
    assert page.state == BossPageState.READY
    assert page.signals == ("job_cards",)
    assert page.jobs == (
        BossJobSummary(
            job_id="job-1",
            title="AI Agent Engineer",
            company="Example Labs",
            location="北京·朝阳",
            salary="25-40K",
            url="https://www.zhipin.com/job_detail/job-1.html",
        ),
    )


def test_security_check_is_a_risk_state_without_job_results() -> None:
    page = parse_boss_page(
        html="<main>请完成安全验证</main>",
        url="https://www.zhipin.com/web/geek/jobs?_security_check=1",
        title="BOSS直聘",
    )

    assert page.kind == BossPageKind.UNKNOWN
    assert page.state == BossPageState.RISK
    assert page.jobs == ()
    assert page.signals == ("security_check",)


def test_login_route_is_a_needs_login_state() -> None:
    page = parse_boss_page(
        html="<main>登录/注册</main>",
        url="https://www.zhipin.com/web/user/",
        title="BOSS直聘",
    )

    assert page.kind == BossPageKind.LOGIN
    assert page.state == BossPageState.NEEDS_LOGIN
    assert page.signals == ("login_required",)


def test_scripts_and_styles_do_not_supply_page_state_or_candidate_data() -> None:
    page = parse_boss_page(
        html="""<script>扫码登录 安全验证 loading</script>
        <style>.loading { content: "安全验证"; }</style>
        <article class="job-card" data-job-id="synthetic-id">
        <span class="job-name">Synthetic job</span>
        <span class="company-name">Synthetic company</span></article>""",
        url="https://www.zhipin.com/web/geek/jobs",
        title="Synthetic BOSS",
    )
    assert page.state == BossPageState.READY
    assert len(page.jobs) == 1


def test_loading_page_is_unstable_until_structure_is_available() -> None:
    page = parse_boss_page(
        html="<main>加载中，请稍候</main>",
        url="https://www.zhipin.com/web/geek/jobs",
        title="BOSS直聘",
    )

    assert page.state == BossPageState.UNSTABLE
    assert page.signals == ("page_loading",)


def test_unknown_structure_fails_loudly() -> None:
    page = parse_boss_page(
        html="<main><h1>页面已更新</h1></main>",
        url="https://www.zhipin.com/web/geek/jobs",
        title="BOSS直聘",
    )

    assert page.kind == BossPageKind.UNKNOWN
    assert page.state == BossPageState.UNKNOWN


def test_authenticated_navigation_overrides_embedded_login_prompt() -> None:
    page = parse_boss_page(
        html='<nav class="user-nav"><a href="/web/geek/chat">消息</a></nav>'
        '<div style="display:none">扫码登录 登录/注册</div>',
        url="https://www.zhipin.com/",
        title="Synthetic BOSS",
    )
    assert page.state == BossPageState.UNKNOWN
    assert page.signals == ("unrecognized_structure",)


def test_embedded_loading_label_is_not_evidence_of_unstable_page() -> None:
    page = parse_boss_page(
        html="<main>消息 <svg><title>loading</title></svg> 已读</main>",
        url="https://www.zhipin.com/web/geek/chat",
        title="Synthetic BOSS",
    )
    assert page.state == BossPageState.UNKNOWN
    assert page.signals == ("unrecognized_structure",)


def test_conversation_page_extracts_unread_thread_and_messages() -> None:
    page = parse_boss_page(
        html="""
        <main data-page="chat">
          <article class="conversation-item unread"
                   data-conversation-id="conv-1" data-unread="true">
            <a href="/web/geek/chat?conversation=conv-1">
              <span data-field="recruiter">李 HR</span>
              <span data-field="company">Example Labs</span>
              <span data-field="job">AI Agent Engineer</span>
              <span data-field="last-message">方便聊一下吗？</span>
            </a>
          </article>
          <div class="message-item" data-message-id="msg-1" data-conversation-id="conv-1"
               data-sender="recruiter"
               data-sent-at="2026-10-08T10:00:00Z">方便聊一下吗？</div>
          <div class="message-item" data-message-id="msg-2" data-conversation-id="conv-1"
               data-sender="candidate">您好，可以的。</div>
        </main>
        """,
        url="https://www.zhipin.com/web/geek/chat?conversation=conv-1",
        title="BOSS直聘",
    )

    assert page.kind == BossPageKind.CONVERSATIONS
    assert page.state == BossPageState.READY
    assert page.signals == ("conversation_data",)
    assert page.conversations == (
        BossConversationSummary(
            conversation_id="conv-1",
            recruiter_name="李 HR",
            company="Example Labs",
            job_title="AI Agent Engineer",
            last_message="方便聊一下吗？",
            unread=True,
            url="https://www.zhipin.com/web/geek/chat?conversation=conv-1",
        ),
    )
    assert page.messages == (
        BossMessageSummary(
            "msg-1", "recruiter", "方便聊一下吗？", "2026-10-08T10:00:00Z", "conv-1"
        ),
        BossMessageSummary("msg-2", "candidate", "您好，可以的。", None, "conv-1"),
    )


@pytest.mark.parametrize(
    "query", ["", "?conversation=c1", "?conversation=missing", "?conversation=c1&conversation=c2"]
)
def test_messages_are_not_assigned_to_a_conversation_by_list_position(query: str) -> None:
    page = parse_boss_page(
        html='<article data-conversation-id="c1"></article>'
        '<div data-message-id="m1" data-sender="recruiter">Synthetic message</div>',
        url="https://www.zhipin.com/web/geek/chat" + query,
        title="Synthetic BOSS",
    )
    assert page.messages[0].conversation_id is None


def test_explicit_message_binding_is_preserved_and_not_parsed_as_a_thread() -> None:
    page = parse_boss_page(
        html='<article data-conversation-id="c1"></article>'
        '<div data-message-id="m1" data-conversation-id="c2" '
        'data-sender="recruiter">Synthetic message</div>',
        url="https://www.zhipin.com/web/geek/chat?conversation=c1",
        title="Synthetic BOSS",
    )
    assert [item.conversation_id for item in page.conversations] == ["c1"]
    assert page.messages[0].conversation_id == "c2"


def test_live_boss_conversation_shell_without_rows_is_not_a_successful_read() -> None:
    page = parse_boss_page(
        html="""
        <main class="chat-container">
          <aside class="friend-content friend-content-warp">
            <div class="chat-user"></div>
          </aside>
          <section class="chat-content">
            <div class="chat-conversation">
              <div class="chat-wrap"><div class="message-status"></div></div>
            </div>
          </section>
        </main>
        """,
        url="https://www.zhipin.com/web/geek/chat",
        title="BOSS直聘",
    )

    assert page.kind == BossPageKind.CONVERSATIONS
    assert page.state == BossPageState.UNKNOWN
    assert page.signals == ("conversation_structure",)
    assert page.conversations == ()
    assert page.messages == ()


@pytest.mark.parametrize("invalid", ["duplicate", "numeric_id", "message_id", "extra", "oversize"])
def test_rendered_conversation_contract_rejects_ambiguous_or_unbounded_data(invalid: str) -> None:
    import json

    from services.browser.site_adapters.boss import parse_boss_rendered_conversations

    row = {
        "conversation_id": "thread-1",
        "recruiter_name": "Synthetic HR",
        "last_message": "Synthetic preview",
        "last_message_id": "123",
        "unread": False,
    }
    if invalid == "numeric_id":
        row["conversation_id"] = 123
    elif invalid == "message_id":
        row["last_message_id"] = "0"
    elif invalid == "extra":
        row["securityId"] = "Must not enter observation"
    rows = [row, row] if invalid == "duplicate" else [row]
    value = " " * (512 * 1024 + 1) if invalid == "oversize" else json.dumps(rows)
    with pytest.raises(ValueError):
        parse_boss_rendered_conversations(value)


def test_rendered_list_preview_is_not_a_full_message_observation() -> None:
    from services.browser.site_adapters.boss import parse_boss_rendered_conversations

    previews = parse_boss_rendered_conversations(
        '[{"conversation_id":"thread-1","recruiter_name":"Synthetic HR",'
        '"last_message":"Synthetic preview","last_message_id":"123","unread":true}]'
    )
    page = parse_boss_page(
        html='<main class="chat-container"><div class="chat-content"></div>'
        '<div class="chat-conversation"></div><div class="chat-user"></div></main>',
        url="https://www.zhipin.com/web/geek/chat",
        title="Synthetic BOSS",
        rendered_conversations=previews,
    )
    assert page.conversations[0].conversation_id == "thread-1"
    assert page.conversations[0].last_message_id == "123"
    assert page.state == "unknown"
    assert page.signals == ("rendered_conversation_previews",)
    assert page.messages == ()
    login = parse_boss_page(
        html="", url="https://www.zhipin.com/web/user/", title="", rendered_conversations=previews
    )
    assert login.state == "needs_login" and login.conversations == ()
