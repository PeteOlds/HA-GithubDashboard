"""Binary sensor platform for the devops_bridge integration.

Implements the CI contract from ENTITY_CONTRACT.md:
- `binary_sensor.{account}_{repo}_ci_ok`
- `on` = CI passing, `off` = CI failing.
- `unavailable` while `running` or `idle` (never a false "fail").
- `idle` covers Actions absent, disabled, or not yet run.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CI_FAIL, CI_OK
from .coordinator import DevopsBridgeCoordinator
from .entity import RepoDeviceEntity


class RepoCISensor(RepoDeviceEntity, BinarySensorEntity):
    """One CI binary sensor per selected repo."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: DevopsBridgeCoordinator, repo_key: str) -> None:
        super().__init__(coordinator, repo_key)
        self.entity_id = (
            f"binary_sensor.{coordinator.account_slug}_{self._repo_slug}_ci_ok"
        )
        self._attr_unique_id = (
            f"{coordinator.account_slug}_{self._repo_slug}_ci_ok"
        )
        self._attr_name = "CI"

    @property
    def available(self) -> bool:
        """Available only for a definitive ok/fail outcome.

        `running`/`idle` -> unavailable, so the dashboard never shows a false
        failure for a repo whose CI is mid-run or unconfigured.
        """
        repo = self._repo
        if repo is None:
            return False
        return repo.ci in (CI_OK, CI_FAIL)

    @property
    def is_on(self) -> bool:
        """True (on) when CI passes. `device_class: PROBLEM` inverts display."""
        repo = self._repo
        return bool(repo and repo.ci == CI_OK)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up CI binary sensors for the account config entry."""
    coordinator: DevopsBridgeCoordinator = entry.runtime_data.coordinator
    async_add_entities(
        RepoCISensor(coordinator, repo_key) for repo_key in coordinator.repos
    )