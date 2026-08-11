"""Shared pytest fixtures for the devops_bridge integration tests."""

from __future__ import annotations

import aiohttp
import pytest
from aiohttp import ClientResponse
from custom_components.devops_bridge.api import GitHubClient
from custom_components.devops_bridge.const import (
    CONF_ACCOUNT,
    CONF_LOGIN,
    CONF_REPO_MAP,
    CONF_REPOS,
    CONF_TOKEN,
)


def _client_response_init(
    self,
    method,
    url,
    *,
    writer,
    continue100,
    timer,
    request_info,
    traces,
    loop,
    session,
    stream_writer=None,
):
    """Compat shim: aioresponses 0.7.9 predates aiohttp's stream_writer kwarg."""

    class _DummyStreamWriter:
        output_size = 0

    if stream_writer is None and writer is None:
        stream_writer = _DummyStreamWriter()
    original_init(
        self,
        method,
        url,
        writer=writer,
        continue100=continue100,
        timer=timer,
        request_info=request_info,
        traces=traces,
        loop=loop,
        session=session,
        stream_writer=stream_writer,
    )


original_init = ClientResponse.__init__
ClientResponse.__init__ = _client_response_init


@pytest.fixture(name="mock_hass")
def mock_hass_fixture(hass):
    """Alias the plugin's Home Assistant instance to the historical name."""
    return hass


USER_LOGIN = "octocat"
REPO_KEYS = ["octocat/Hello-World", "octocat/github-linguist"]


def repo_payload(name: str, full_name: str, **overrides) -> dict:
    default = {
        "id": 1,
        "full_name": full_name,
        "name": name,
        "html_url": f"https://github.com/{full_name}",
        "private": False,
        "default_branch": "main",
        "stargazers_count": 10,
        "forks_count": 2,
        "subscribers_count": 1,
        "open_issues_count": 3,
        "pushed_at": "2026-05-01T12:00:00Z",
        "owner": {"login": "octocat"},
    }
    default.update(overrides)
    return default


def user_payload(login: str = USER_LOGIN) -> dict:
    return {"login": login, "id": 42}


def ci_runs_payload(conclusion: str | None, status: str = "completed") -> dict:
    return {
        "total_count": 1,
        "workflow_runs": [
            {
                "id": 1,
                "status": status,
                "conclusion": conclusion,
                "head_branch": "main",
            }
        ],
    }


def releases_payload(tag: str = "v1.2.3") -> dict:
    return {
        "tag_name": tag,
        "published_at": "2026-05-01T12:00:00Z",
        "name": tag,
    }


def events_payload() -> list[dict]:
    return [
        {
            "type": "PushEvent",
            "created_at": "2026-05-01T12:00:00Z",
            "repo": {"name": "octocat/Hello-World"},
        },
        {
            "type": "PullRequestEvent",
            "created_at": "2026-05-01T11:00:00Z",
            "repo": {"name": "octocat/github-linguist"},
        },
    ]


def flow_options(account: str = "Work", repos: list[str] | None = None) -> dict:
    """A data dict as stored on the created config entry."""
    from custom_components.devops_bridge.config_flow import _slug

    selected = repos or REPO_KEYS
    return {
        CONF_ACCOUNT: account,
        CONF_TOKEN: "ghp_xxx",
        CONF_LOGIN: USER_LOGIN,
        CONF_REPOS: selected,
        CONF_REPO_MAP: {r: _slug(r.split("/")[-1]) for r in selected},
    }


@pytest.fixture(name="client")
async def client_fixture():
    """A GitHubClient backed by a throwaway session (responses mocked per test)."""
    session = aiohttp.ClientSession()
    yield GitHubClient(session, "ghp_xxx")
    await session.close()