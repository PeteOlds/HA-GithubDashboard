"""Sensor platform for the devops_bridge integration.

Implements the entity contract from ENTITY_CONTRACT.md:
- `sensor.{account}_{repo}_repo` — summary sensor; attributes drive the
  flex-table.
- `sensor.{account}_{repo}_{metric}` — per-metric sensors for tiles.
- `sensor.{account}_recent_activity` — per-account markdown feed.

Entities are read-only; the only action in the dashboard is `tap_action: url`.
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import DevopsBridgeCoordinator
from .entity import DevopsBridgeEntity, RepoDeviceEntity

_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="open_pulls", icon="mdi:source-pull"
    ),
    SensorEntityDescription(
        key="open_issues", icon="mdi:alert-circle"
    ),
    SensorEntityDescription(
        key="stars", icon="mdi:star"
    ),
    SensorEntityDescription(
        key="forks", icon="mdi:source-fork"
    ),
    SensorEntityDescription(
        key="watchers", icon="mdi:eye-outline"
    ),
    SensorEntityDescription(
        key="latest_release", icon="mdi:tag"
    ),
    SensorEntityDescription(
        key="release_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key="pushed_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
    ),
)

_DESCRIPTION_NAMES: dict[str, str] = {
    "open_pulls": "Open pull requests",
    "open_issues": "Open issues",
    "stars": "Stars",
    "forks": "Forks",
    "watchers": "Watchers",
    "latest_release": "Latest release",
    "release_date": "Release date",
    "pushed_at": "Last pushed",
}

_TIMESTAMP_KEYS = {"release_date", "pushed_at"}


def _parse_timestamp(value: str) -> datetime | None:
    """Parse an ISO timestamp from the API (may be empty)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class RepoSummarySensor(RepoDeviceEntity, SensorEntity):
    """Per-repo summary sensor driving the flex-table (`sensor.{a}_{r}_repo`)."""

    def __init__(self, coordinator: DevopsBridgeCoordinator, repo_key: str) -> None:
        super().__init__(coordinator, repo_key)
        self.entity_id = f"sensor.{coordinator.account_slug}_{self._repo_slug}_repo"
        self._attr_unique_id = f"{coordinator.account_slug}_{self._repo_slug}_repo"
        self._attr_name = "Repository"
        self._attr_icon = "mdi:github"

    @property
    def native_value(self) -> str:
        """State is the repository short name (device provides context)."""
        repo = self._repo
        return repo.repository if repo else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """The flex-table contract attributes."""
        repo = self._repo
        if repo is None:
            return {}
        return {
            "account": self.coordinator.account_slug,
            "repository": repo.repository,
            "url": repo.url,
            "stars": repo.stars,
            "forks": repo.forks,
            "watchers": repo.watchers,
            "open_issues": repo.open_issues,
            "open_pulls": repo.open_pulls,
            "ci": repo.ci,
            "latest_release": repo.latest_release,
            "release_date": repo.release_date,
            "pushed_at": repo.pushed_at,
        }


class RepoMetricSensor(RepoDeviceEntity, SensorEntity):
    """A single small metric sensor for tiles/glances."""

    def __init__(
        self,
        coordinator: DevopsBridgeCoordinator,
        repo_key: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, repo_key)
        self.entity_id = (
            f"sensor.{coordinator.account_slug}_{self._repo_slug}_{description.key}"
        )
        self._attr_unique_id = (
            f"{coordinator.account_slug}_{self._repo_slug}_{description.key}"
        )
        self._attr_name = _DESCRIPTION_NAMES[description.key]
        self._attr_device_class = description.device_class
        self._attr_icon = description.icon
        self._description = description

    @property
    def native_value(self) -> int | str | datetime | None:
        repo = self._repo
        if repo is None:
            return None
        raw = getattr(repo, self._description.key)
        if isinstance(raw, str) and self._description.key in _TIMESTAMP_KEYS:
            return _parse_timestamp(raw)
        return raw if isinstance(raw, (int, str, datetime)) else None


class AccountActivitySensor(DevopsBridgeEntity, SensorEntity):
    """Per-account recent activity feed (`sensor.{account}_recent_activity`)."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: DevopsBridgeCoordinator, account_slug: str) -> None:
        super().__init__(coordinator, repo_key="")
        self._account_slug = account_slug
        self.entity_id = f"sensor.{account_slug}_recent_activity"
        self._attr_unique_id = f"{account_slug}_recent_activity"
        self._attr_name = "Recent activity"
        self._attr_icon = "mdi:history"

    @property
    def available(self) -> bool:
        """The feed is available whenever the account coordinator is."""
        return bool(self.coordinator.data)

    @property
    def native_value(self) -> str:
        if self.coordinator.data is None:
            return ""
        return self.coordinator.data.activity or ""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for the account config entry."""
    coordinator: DevopsBridgeCoordinator = entry.runtime_data.coordinator
    account_slug: str = coordinator.account_slug

    entities: list = []
    for repo_key in coordinator.repos:
        entities.append(RepoSummarySensor(coordinator, repo_key))
        for description in _DESCRIPTIONS:
            entities.append(RepoMetricSensor(coordinator, repo_key, description))
    entities.append(AccountActivitySensor(coordinator, account_slug))

    async_add_entities(entities)