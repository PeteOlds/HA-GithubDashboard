"""DevOps Bridge — read-only multi-account GitHub integration.

Per ENTITY_CONTRACT.md and INTEGRATION_SPEC.md: one config entry per account,
one `DataUpdateCoordinator` per entry. All I/O is async against GitHub's REST
API using Home Assistant's shared aiohttp session. The integration is
read-only by design.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import GitHubClient
from .const import CONF_ACCOUNT, CONF_TOKEN
from .const import DOMAIN as DOMAIN
from .coordinator import DevopsBridgeCoordinator, async_get_client

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass
class DevopsBridgeRuntimeData:
    """Runtime data stored on the config entry."""

    client: GitHubClient
    coordinator: DevopsBridgeCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DevOps Bridge from a config entry."""
    token: str = entry.data[CONF_TOKEN]
    client = await async_get_client(hass, token)
    account_slug = _account_slug(entry)

    coordinator = DevopsBridgeCoordinator(hass, entry, client, account_slug)
    await coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    entry.runtime_data = DevopsBridgeRuntimeData(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle config-entry migration between schema versions."""
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the entry is reconfigured via options."""
    await hass.config_entries.async_reload(entry.entry_id)


def _account_slug(entry: ConfigEntry) -> str:
    """The {account} slug for entity ids (see ENTITY_CONTRACT.md)."""
    from .entity import slugify

    return slugify(entry.data.get(CONF_ACCOUNT, entry.title))
