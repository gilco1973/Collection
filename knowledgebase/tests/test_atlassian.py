import json

import httpx
import pytest

from kb_librarian.atlassian.client import AtlassianNotConfigured, AtlassianWriteRefused
from kb_librarian.atlassian.confluence import ConfluenceClient
from kb_librarian.atlassian.jira import JiraClient
from kb_librarian.atlassian.markdown import markdown_to_storage
from kb_librarian.atlassian.sync import page_title, sync_sections
from kb_librarian.config import LibrarianSettings
from kb_librarian.models import AuditReport
from kb_librarian.tools.atlassian_tools import build_atlassian_tools
from kb_librarian.tools.context import ToolContext
from tests.helpers import payload


class Recorder:
    def __init__(self):
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            path = request.url.path
            if path.endswith("/content/search"):
                return httpx.Response(
                    200, json={"results": [{"id": "1", "title": "Hit", "type": "page", "_links": {"webui": "/x"}}]}
                )
            if path.endswith("/content/123"):
                return httpx.Response(
                    200,
                    json={
                        "id": "123",
                        "title": "P",
                        "space": {"key": "TEST"},
                        "version": {"number": 4},
                        "body": {"storage": {"value": "<p>b</p>"}},
                    },
                )
            if path.endswith("/rest/api/content") and request.method == "GET":
                title = request.url.params.get("title")
                results = (
                    [{"id": "9", "title": title, "version": {"number": 2}}]
                    if title == "[Onboarding] Onboarding"
                    else []
                )
                return httpx.Response(200, json={"results": results})
            if path.endswith("/rest/api/content") and request.method == "POST":
                return httpx.Response(200, json={"id": "new", "title": json.loads(request.content)["title"]})
            if path.endswith("/content/9") and request.method == "PUT":
                return httpx.Response(200, json={"id": "9", "title": "t", "version": {"number": 3}})
            if path.endswith("/rest/api/3/search"):
                return httpx.Response(
                    200, json={"issues": [{"key": "T-1", "fields": {"summary": "s", "status": {"name": "Open"}}}]}
                )
            if path.endswith("/rest/api/3/issue"):
                return httpx.Response(201, json={"key": "T-2"})
            return httpx.Response(404, json={})

        return httpx.MockTransport(handle)


def _settings(**kw) -> LibrarianSettings:
    return LibrarianSettings(
        atlassian_base_url="https://t.atlassian.net",
        atlassian_email="svc@example.com",
        atlassian_api_token="tok",
        **kw,
    )


def test_from_settings_requires_configuration():
    with pytest.raises(AtlassianNotConfigured):
        ConfluenceClient.from_settings(LibrarianSettings(), dry_run=True)


def test_confluence_reads_work_and_writes_are_gated():
    rec = Recorder()
    client = ConfluenceClient.from_settings(_settings(), dry_run=True, transport=rec.transport())
    assert client.search("x")[0]["url"] == "https://t.atlassian.net/wiki/x"
    assert client.get_page("123")["version"] == 4
    with pytest.raises(AtlassianWriteRefused):
        client.publish("TEST", "Title", "<p/>")
    assert all(r.method == "GET" for r in rec.requests)
    client.close()


def test_confluence_publish_creates_or_updates_when_allowed():
    rec = Recorder()
    client = ConfluenceClient.from_settings(
        _settings(atlassian_allow_write=True), dry_run=False, transport=rec.transport()
    )
    assert client.publish("TEST", "Brand new", "<p/>")["action"] == "created"
    assert client.publish("TEST", "[Onboarding] Onboarding", "<p/>")["action"] == "updated"
    assert client.create_page("TEST", "child", "<p/>", parent_id="1")["id"] == "new"
    assert [r.method for r in rec.requests].count("PUT") == 1
    assert rec.requests[0].headers["authorization"].startswith("Basic ")


def test_confluence_write_refused_when_allow_write_but_dry_run():
    client = ConfluenceClient.from_settings(
        _settings(atlassian_allow_write=True), dry_run=True, transport=Recorder().transport()
    )
    assert client.writes_enabled is False
    with pytest.raises(AtlassianWriteRefused):
        client.update_page("9", "t", "<p/>", 2)


def test_jira_search_and_gated_create():
    rec = Recorder()
    gated = JiraClient.from_settings(_settings(), dry_run=False, transport=rec.transport())
    assert gated.search("project = T")[0]["key"] == "T-1"
    with pytest.raises(AtlassianWriteRefused):
        gated.create_issue("T", "s", "d")
    live = JiraClient.from_settings(_settings(atlassian_allow_write=True), dry_run=False, transport=rec.transport())
    created = live.create_issue("T", "Stale page", "please review", labels=["kb"])
    assert created == {"key": "T-2", "url": "https://t.atlassian.net/browse/T-2"}
    body = json.loads(rec.requests[-1].content)
    assert body["fields"]["labels"] == ["kb"] and body["fields"]["description"]["type"] == "doc"


def test_markdown_to_storage_handles_core_constructs():
    out = markdown_to_storage(
        "# H1\n\nPara with `code` and **bold** and [a](http://x).\n\n- one\n- two\n\n```\nx < y\n```\n"
    )
    assert "<h1>H1</h1>" in out and "<code>code</code>" in out and "<strong>bold</strong>" in out
    assert '<a href="http://x">a</a>' in out and "<ul>\n<li>one</li>\n<li>two</li>\n</ul>" in out
    assert "<![CDATA[x < y]]>" in out
    assert markdown_to_storage("line one\nline two\n") == "<p>line one line two</p>"


def test_markdown_to_storage_escapes_quotes_so_a_link_target_cannot_break_out_of_href():
    out = markdown_to_storage('[x](http://h/a"onclick="1) and "quoted" text\n')
    assert 'onclick="1' not in out and "&quot;" in out and '<a href="http://h/a&quot;onclick=&quot;1">x</a>' in out
    unsafe = markdown_to_storage("[run](javascript:alert(1)) and [rel](../page.md)\n")
    assert '<a href="javascript' not in unsafe and "run (javascript:alert(1))" in unsafe
    assert '<a href="../page.md">rel</a>' in unsafe


def test_sync_reports_would_publish_when_gated_and_publishes_when_live(catalog, kb_config):
    gated = ConfluenceClient.from_settings(_settings(), dry_run=True, transport=Recorder().transport())
    results = sync_sections(catalog, kb_config, gated)
    assert {r.action for r in results} == {"would-publish"}
    assert page_title(catalog.get("onboarding/README.md"), kb_config) == "[Onboarding] Onboarding"
    rec = Recorder()
    live = ConfluenceClient.from_settings(
        _settings(atlassian_allow_write=True), dry_run=False, transport=rec.transport()
    )
    results = sync_sections(catalog, kb_config, live, sections=["onboarding"])
    assert sorted(r.action for r in results) == ["created", "updated"]
    drafts = sync_sections(catalog, kb_config, live, sections=["governance"])
    assert drafts[0].action == "skipped"


async def test_atlassian_tools(catalog, kb_root, kb_config):
    rec = Recorder()
    report = AuditReport(audit_type="agent", dry_run=False)
    ctx = ToolContext(root=kb_root, config=kb_config, catalog=catalog, report=report)
    live = _settings(atlassian_allow_write=True)
    tools = {
        t.name: t.handler
        for t in build_atlassian_tools(
            ctx,
            ConfluenceClient.from_settings(live, dry_run=False, transport=rec.transport()),
            JiraClient.from_settings(live, dry_run=False, transport=rec.transport()),
        )
    }
    assert payload(await tools["confluence_search"]({"query": 'a "quoted" q'}))[0]["id"] == "1"
    assert payload(await tools["confluence_get_page"]({"page_id": "123"}))["id"] == "123"
    published = payload(await tools["confluence_publish_page"]({"path": "onboarding/stale.md", "reason": "r"}))
    assert published["action"] == "created"
    assert (await tools["confluence_publish_page"]({"path": "nope.md", "reason": "r"}))["is_error"]
    issue = payload(await tools["jira_create_issue"]({"summary": "s", "description": "d", "reason": "r"}))
    assert issue["key"] == "T-2"
    assert [a.action_type for a in report.fixes_applied] == ["confluence_publish_page", "jira_create_issue"]
    gated = {
        t.name: t.handler
        for t in build_atlassian_tools(
            ctx,
            ConfluenceClient.from_settings(_settings(), dry_run=True),
            JiraClient.from_settings(_settings(), dry_run=True),
        )
    }
    assert (await gated["confluence_publish_page"]({"path": "onboarding/stale.md", "reason": "r"}))["is_error"]
    assert (await gated["jira_create_issue"]({"summary": "s", "description": "d", "reason": "r"}))["is_error"]
