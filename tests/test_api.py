"""Tests for the GitHub API client (mocked aiohttp responses)."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses
from custom_components.devops_bridge.api import (
    CI_FAIL,
    CI_IDLE,
    CI_OK,
    CI_RUNNING,
    GitHubAuthenticationError,
)

from .conftest import (
    ci_runs_payload,
    events_payload,
    releases_payload,
    repo_payload,
    user_payload,
)


async def test_async_get_user(client):
    with aioresponses() as mocked:
        mocked.get(
            "https://api.github.com/user",
            payload=user_payload(),
        )
        login = await client.async_get_user()
    assert login == "octocat"


async def test_async_get_user_auth_failure(client):
    with aioresponses() as mocked:
        mocked.get("https://api.github.com/user", status=401)
        with pytest.raises(GitHubAuthenticationError):
            await client.async_get_user()


async def test_async_get_repos_paginated(client):
    repo = repo_payload("Hello-World", "octocat/Hello-World")
    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"https://api\.github\.com/user/repos\?.*"),
            payload=[repo, repo_payload("linguist", "octocat/github-linguist")],
        )
        repos = await client.async_get_repos()
    assert len(repos) == 2


async def test_async_get_ci_ok(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(
                r"https://api\.github\.com/repos/octocat/Hello-World/actions/runs.*"
            ),
            payload=ci_runs_payload(conclusion="success"),
        )
        status = await client.async_get_ci_status("octocat", "Hello-World", "main")
    assert status == CI_OK


async def test_async_get_ci_fail(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(
                r"https://api\.github\.com/repos/octocat/Hello-World/actions/runs.*"
            ),
            payload=ci_runs_payload(conclusion="failure"),
        )
        status = await client.async_get_ci_status("octocat", "Hello-World", "main")
    assert status == CI_FAIL


async def test_async_get_ci_running(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(
                r"https://api\.github\.com/repos/octocat/Hello-World/actions/runs.*"
            ),
            payload=ci_runs_payload(conclusion=None, status="in_progress"),
        )
        status = await client.async_get_ci_status("octocat", "Hello-World", "main")
    assert status == CI_RUNNING


async def test_async_get_ci_no_runs_is_idle(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(
                r"https://api\.github\.com/repos/octocat/Hello-World/actions/runs.*"
            ),
            payload={"total_count": 0, "workflow_runs": []},
        )
        status = await client.async_get_ci_status("octocat", "Hello-World", "main")
    assert status == CI_IDLE


async def test_async_get_ci_actions_absent_is_idle(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(
                r"https://api\.github\.com/repos/octocat/Hello-World/actions/runs.*"
            ),
            status=404,
        )
        status = await client.async_get_ci_status("octocat", "Hello-World", "main")
    assert status == CI_IDLE


async def test_async_get_latest_release(client):
    with aioresponses() as mocked:
        mocked.get(
            "https://api.github.com/repos/octocat/Hello-World/releases/latest",
            payload=releases_payload("v1.2.3"),
        )
        tag, published = await client.async_get_latest_release("octocat", "Hello-World")
    assert tag == "v1.2.3"
    assert published == "2026-05-01T12:00:00Z"


async def test_async_get_latest_release_none(client):
    with aioresponses() as mocked:
        mocked.get(
            "https://api.github.com/repos/octocat/Hello-World/releases/latest",
            status=404,
        )
        tag, published = await client.async_get_latest_release("octocat", "Hello-World")
    assert tag == ""
    assert published == ""


async def test_async_get_open_pulls(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"https://api\.github\.com/repos/octocat/Hello-World/pulls.*"),
            payload=[{"number": 1}, {"number": 2}],
        )
        count = await client.async_get_open_pulls("octocat", "Hello-World")
    assert count == 2


async def test_async_get_activity_markdown(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"https://api\.github\.com/users/octocat/events/public.*"),
            payload=events_payload(),
        )
        text = await client.async_get_activity_markdown(
            "octocat", repos=[("octocat", "Hello-World")]
        )
    assert "PushEvent" in text
    assert "octocat/Hello-World" in text


async def test_async_get_activity_markdown_error_returns_empty(client):
    with aioresponses() as mocked:
        mocked.get(
            re.compile(r"https://api\.github\.com/users/octocat/events/public.*"),
            status=500,
        )
        text = await client.async_get_activity_markdown(
            "octocat", repos=[("octocat", "Hello-World")]
        )
    assert text == ""
