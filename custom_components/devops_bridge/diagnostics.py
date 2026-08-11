"""Diagnostics support for the devops_bridge integration.

Fully redacted: the token is never included, and account/repo identifiers are
kept minimal. Follows the Integration Guide's requirement that credentials and
personal data never appear in diagnostics.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCOUNT,
    CONF_LOGIN,
    CONF_REPOS,
    CONF_TOKEN,
    DOMAIN,
)

REDACT = {CONF_TOKEN, CONF_LOGIN, "login", "owner", "token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (secrets redacted)."""
    coordinator = getattr(entry, "runtime_data", None)
    data = {**entry.data}
    data.pop(CONF_TOKEN, None)
    data[CONF_TOKEN] = "**REDACTED**"

    repo_states: dict[str, Any] = {}
    if coordinator is not None and coordinator.data is not None:
        for repo_key, repo in coordinator.data.repos.items():
            repo_states[repo_key] = {
                "available": repo.available,
                "ci": repo.ci,
                "stars": repo.stars,
                "open_pulls": repo.open_pulls,
                "open_issues": repo.open_issues,
                "watchers": repo.watchers,
                "pushed_at": repo.pushed_at,
            }

    return {
        "domain": DOMAIN,
        "config": async_redact_data(data, REDACT),
        "account": entry.data.get(CONF_ACCOUNT),
        "repos_configured": len(entry.data.get(CONF_REPOS, [])),
        "repo_states": repo_states,
        "last_update": (
            coordinator.last_update_success if coordinator is not None else None
        ),
    }