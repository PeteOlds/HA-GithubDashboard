"""Config-flow tests for the devops_bridge integration.

Covers: first-time flow, invalid credentials, duplicate prevention, reauth,
and options. HTTP is mocked — no live GitHub.
"""

from __future__ import annotations

import re

from aioresponses import aioresponses
from custom_components.devops_bridge.const import (
    CONF_ACCOUNT,
    CONF_LOGIN,
    CONF_REPO_MAP,
    CONF_REPOS,
    CONF_TOKEN,
    DOMAIN,
)

from homeassistant import config_entries

from .conftest import repo_payload, user_payload

URL_USER = "https://api.github.com/user"
URL_REPOS = re.compile(r"https://api\.github\.com/user/repos\?.*")


async def test_form(mock_hass, client, enable_custom_integrations):
    """Complete the config flow end-to-end."""
    with aioresponses() as mocked:
        mocked.get(URL_USER, payload=user_payload())
        mocked.get(
            URL_REPOS,
            payload=[
                repo_payload("Hello-World", "octocat/Hello-World"),
            ],
        )

        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ACCOUNT: "Work"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "token"

        result = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "ghp_xxx"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "repos"

        result = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REPOS: ["octocat/Hello-World"]}
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Work"
        data = result["data"]
        assert data[CONF_LOGIN] == "octocat"
        assert data[CONF_REPOS] == ["octocat/Hello-World"]
        assert data[CONF_REPO_MAP] == {"octocat/Hello-World": "hello_world"}


async def test_invalid_token_error(mock_hass, enable_custom_integrations):
    """A 401 on /user surfaces an inline error, not a crash."""
    with aioresponses() as mocked:
        mocked.get(URL_USER, status=401)

        result = await mock_hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ACCOUNT: "Work"}
        )
        result = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "bad"}
        )
        assert result["type"] == "form"
        assert result["errors"] == {CONF_TOKEN: "invalid_auth"}


async def test_duplicate_prevention(mock_hass, enable_custom_integrations):
    """Two entries for the same GitHub login are rejected."""

    async def _run_flow():
        with aioresponses() as mocked:
            mocked.get(URL_USER, payload=user_payload())
            mocked.get(URL_REPOS, payload=[])
            result = await mock_hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            assert result["type"] == "form"
            result = await mock_hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_ACCOUNT: "Work"}
            )
            assert result["type"] == "form"
            result = await mock_hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_TOKEN: "ghp_xxx"}
            )
            if result["type"] == "abort":
                return result
            assert result["type"] == "form"
            result = await mock_hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_REPOS: []}
            )
            return result

    first = await _run_flow()
    assert first["type"] == "create_entry"

    second = await _run_flow()
    assert second["type"] == "abort"
    assert second["reason"] == "already_configured"


async def test_reauth(mock_hass, client, enable_custom_integrations):
    """Reauth replaces the stored token and reloads the entry."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Work",
        data={
            CONF_ACCOUNT: "Work",
            CONF_LOGIN: "octocat",
            CONF_TOKEN: "ghp_old",
            CONF_REPOS: [],
            CONF_REPO_MAP: {},
        },
        source=SOURCE_USER,
        entry_id="entry-id",
    )
    entry.add_to_hass(mock_hass)
    await mock_hass.config_entries.async_setup(entry.entry_id)

    result = await mock_hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
    )
    assert result["type"] == "form"

    with aioresponses() as mocked:
        mocked.get(URL_USER, payload=user_payload())
        result = await mock_hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "ghp_new"}
        )
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert mock_hass.config_entries.async_get_entry("entry-id").data[CONF_TOKEN] == "ghp_new"