"""Shared entity base classes for the devops_bridge integration."""

from __future__ import annotations

import re

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RepoData
from .const import DOMAIN
from .coordinator import DevopsBridgeCoordinator


def slugify(value: str) -> str:
    """Turn a free-text account/repo name into the contract `{account}`/_`{repo}` slug.

    Lowercased; any run of non-`[a-z0-9]` collapses to a single underscore.
    Mirrors ENTITY_CONTRACT.md "Slug derivation".
    """
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


class DevopsBridgeEntity(CoordinatorEntity[DevopsBridgeCoordinator]):
    """Base entity linked to the per-account coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DevopsBridgeCoordinator,
        repo_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._repo_key = repo_key

    @property
    def _repo_slug(self) -> str:
        return self.coordinator.repo_slug(self._repo_key)

    @property
    def available(self) -> bool:
        """Entity is available only when the repo data is present and online."""
        if self.coordinator.data is None:
            return False
        repo: RepoData | None = self.coordinator.data.repos.get(self._repo_key)
        return repo is not None and repo.available


class RepoDeviceEntity(DevopsBridgeEntity):
    """Entity with DeviceInfo for the per-repo device."""

    def __init__(self, coordinator: DevopsBridgeCoordinator, repo_key: str) -> None:
        super().__init__(coordinator, repo_key)
        owner, _, repo_name = repo_key.partition("/")
        self.repo_name = repo_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.account_slug}_{self._repo_slug}")},
            name=repo_name,
            manufacturer="GitHub",
            model=coordinator.account_slug,
        )

    @property
    def _repo(self) -> RepoData | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.repos.get(self._repo_key)
