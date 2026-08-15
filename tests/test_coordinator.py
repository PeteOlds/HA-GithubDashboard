"""Tests for the per-account coordinator (mocked HTTP, no live GitHub)."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses
from custom_components.devops_bridge.api import (
    CI_OK,
)
from custom_components.devops_bridge.const import (
    CONF_ACCOUNT,
    CONF_LOGIN,
    CONF_REPO_MAP,
    CONF_REPOS,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.devops_bridge.coordinator import DevopsBridgeCoordinator

from .conftest import (
    REPO_KEYS,
    ci_runs_payload,
    events_payload,
    releases_payload,
    repo_payload,
)

URL_EVENTS = re.compile(r"https://api\.github\.com/users/octocat/events/public.*")


def make_entry(mock_hass, repos=None, options=None):
    from homeassistant.config_entries import ConfigEntry

    data = {
        CONF_ACCOUNT: "Work",
        CONF_LOGIN: "octocat",
        CONF_TOKEN: "ghp_xxx",
        CONF_REPOS: repos or REPO_KEYS,
        CONF_REPO_MAP: {r: r.split("/")[-1].lower() for r in (repos or REPO_KEYS)},
    }
    return ConfigEntry(
        version=1,
        domain=DOMAIN,
        title="Work",
        data=data,
        source="user",
        entry_id="test-entry",
        options=options or {},
        minor_version=1,
        discovery_keys={},
        subentries_data=None,
        unique_id="octocat",
    )


async def test_coordinator_refresh_repo(mock_hass, client):
    """A full refresh produces repo data for each selected repo."""
    entry = make_entry(mock_hass, ["octocat/Hello-World"])
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")

    with aioresponses() as mocked:
        mocked.get(
            "https://api.github.com/repos/octocat/Hello-World",
            payload=repo_payload("Hello-World", "octocat/Hello-World"),
        )
        mocked.get(
            re.compile(r"https://api\.github\.com/repos/octocat/Hello-World/pulls.*"),
            payload=[{"number": 1}],
        )
        mocked.get(
            re.compile(
                r"https://api\.github\.com/repos/octocat/Hello-World/actions/runs.*"
            ),
            payload=ci_runs_payload(conclusion="success"),
        )
        mocked.get(
            "https://api.github.com/repos/octocat/Hello-World/releases/latest",
            payload=releases_payload("v1.0.0"),
        )
        mocked.get(
            URL_EVENTS,
            payload=events_payload(),
        )

        data = await coordinator._async_update_data()

    repo = data.repos["octocat/Hello-World"]
    assert repo.ci == CI_OK
    assert repo.open_pulls == 1
    assert repo.latest_release == "v1.0.0"
    assert "PushEvent" in data.activity


async def test_coordinator_options_repos_take_precedence(mock_hass, client):
    """Repos set via the options flow (entry.options) override entry.data.

    Regression: the options flow writes the new repo selection to entry.options,
    so the coordinator must prefer options over the initial data list, or
    adding a repo via Options is never reflected in the UI.
    """
    entry = make_entry(
        mock_hass,
        repos=["octocat/Hello-World"],
        options={
            CONF_REPOS: ["octocat/Hello-World", "octocat/github-linguist"],
            CONF_REPO_MAP: {
                "octocat/Hello-World": "hello_world",
                "octocat/github-linguist": "github_linguist",
            },
        },
    )
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    assert coordinator.repos == [
        "octocat/Hello-World",
        "octocat/github-linguist",
    ]
    assert coordinator.repo_slug("octocat/github-linguist") == "github_linguist"


async def test_coordinator_rate_limit(mock_hass, client):
    """A 429 surfaces as UpdateFailed with retry_after."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    entry = make_entry(mock_hass, ["octocat/Hello-World"])
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")

    with aioresponses() as mocked:
        mocked.get(
            "https://api.github.com/repos/octocat/Hello-World",
            status=429,
            headers={"Retry-After": "60"},
        )
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


async def test_coordinator_missing_repo_marks_unavailable(mock_hass, client):
    """A 404 on one repo must not kill the coordinator."""
    entry = make_entry(mock_hass, ["octocat/Hello-World"])
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")

    with aioresponses() as mocked:
        mocked.get("https://api.github.com/repos/octocat/Hello-World", status=404)
        data = await coordinator._async_update_data()

    repo = data.repos["octocat/Hello-World"]
    assert repo.available is False


async def test_coordinator_auth_failed(mock_hass, client):
    """Authentication errors raise ConfigEntryAuthFailed (triggers reauth)."""
    from homeassistant.exceptions import ConfigEntryAuthFailed

    entry = make_entry(mock_hass, ["octocat/Hello-World"])
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")

    with aioresponses() as mocked:
        mocked.get("https://api.github.com/repos/octocat/Hello-World", status=401)
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
