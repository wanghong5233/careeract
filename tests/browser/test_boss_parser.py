from services.browser.site_adapters.boss import (
    BossJobSummary,
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
    assert page.signals == ("unrecognized_structure",)
