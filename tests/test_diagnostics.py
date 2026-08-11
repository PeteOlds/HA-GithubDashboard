"""Diagnostics tests: output is structured and secrets stay redacted."""

from __future__ import annotations

from custom_components.devops_bridge.const import (
    CONF_LOGIN,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.devops_bridge.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import flow_options


async def test_diagnostics_redacts_token(mock_hass, client):
    """The token never appears; a redacted placeholder is shown instead."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.config_entries import SOURCE_USER

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Work",
        data=flow_options(),
        source=SOURCE_USER,
        entry_id="entry-diag",
    )
    entry.add_to_hass(mock_hass)

    diag = await async_get_config_entry_diagnostics(mock_hass, entry)

    assert diag["domain"] == DOMAIN
    assert diag["config"][CONF_TOKEN] == "**REDACTED**"
    assert diag["config"][CONF_LOGIN] == "**REDACTED**"
    assert diag["account"] == "Work"
    assert diag["repos_configured"] == 2
    # No real token value anywhere; the login field is redacted. (Repo full
    # names legitimately contain the owner as part of "owner/name".)
    assert "ghp_xxx" not in str(diag)
    assert diag["config"][CONF_LOGIN] == "**REDACTED**"


async def test_diagnostics_reports_repo_states(mock_hass, client):
    """With coordinator data, per-repo states are included."""
    from custom_components.devops_bridge.api import CI_OK, RepoData
    from custom_components.devops_bridge.coordinator import (
        DevopsBridgeCoordinator,
        DevopsBridgeData,
    )
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from homeassistant.config_entries import SOURCE_USER

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Work",
        data=flow_options(repos=["octocat/Hello-World"]),
        source=SOURCE_USER,
        entry_id="entry-diag-data",
    )
    entry.add_to_hass(mock_hass)
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    coordinator.data = DevopsBridgeData(
        repos={
            "octocat/Hello-World": RepoData(
                owner="octocat",
                repository="Hello-World",
                url="https://github.com/octocat/Hello-World",
                stars=10,
                forks=2,
                watchers=1,
                open_issues=3,
                open_pulls=1,
                ci=CI_OK,
                latest_release="v1.0.0",
                release_date="2026-05-01T12:00:00Z",
                pushed_at="2026-05-01T12:00:00Z",
            )
        }
    )
    entry.runtime_data = coordinator

    diag = await async_get_config_entry_diagnostics(mock_hass, entry)

    state = diag["repo_states"]["octocat/Hello-World"]
    assert state["ci"] == CI_OK
    assert state["available"] is True
    assert state["stars"] == 10
    assert state["open_pulls"] == 1
