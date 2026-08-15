"""Entity tests: summary/metric sensors and the CI binary sensor.

Uses the HA test harness (`mock_hass`) plus `aioresponses` against the shared
session. No real GitHub account is touched.
"""

from __future__ import annotations

from custom_components.devops_bridge.api import CI_FAIL, CI_IDLE, CI_OK, CI_RUNNING
from custom_components.devops_bridge.binary_sensor import RepoCISensor
from custom_components.devops_bridge.const import DOMAIN
from custom_components.devops_bridge.coordinator import (
    DevopsBridgeCoordinator,
    DevopsBridgeData,
)
from custom_components.devops_bridge.entity import slugify
from custom_components.devops_bridge.sensor import RepoSummarySensor

from .conftest import REPO_KEYS


def build_repo(ci: str = CI_OK, *, available: bool = True):
    from custom_components.devops_bridge.api import RepoData

    return RepoData(
        owner="octocat",
        repository="Hello-World",
        url="https://github.com/octocat/Hello-World",
        stars=10,
        forks=2,
        watchers=1,
        open_issues=3,
        open_pulls=1,
        ci=ci,
        latest_release="v1.0.0",
        release_date="2026-05-01T12:00:00Z",
        pushed_at="2026-05-01T12:00:00Z",
        available=available,
    )


async def test_slugify():
    assert slugify("My Work") == "my_work"
    assert slugify("hello-world") == "hello_world"
    assert slugify("  Foo--Bar  ") == "foo_bar"


async def test_summary_sensor_attributes(mock_hass, client):
    entry = _entry(mock_hass)
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    # Seed coordinator data directly (no HTTP needed).
    coordinator.data = DevopsBridgeData(repos={REPO_KEYS[0]: build_repo()})

    sensor = RepoSummarySensor(coordinator, REPO_KEYS[0])
    assert sensor.entity_id == "sensor.work_hello_world_repo"
    assert sensor.state == "Hello-World"
    attrs = sensor.extra_state_attributes
    assert attrs["account"] == "work"
    assert attrs["stars"] == 10
    assert attrs["ci"] == CI_OK
    assert attrs["open_pulls"] == 1
    assert sensor.available is True


async def test_ci_binary_sensor_ok(mock_hass, client):
    """A passing CI is OFF — device_class:problem renders OFF as "OK"."""
    entry = _entry(mock_hass)
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    coordinator.data = DevopsBridgeData(repos={REPO_KEYS[0]: build_repo(ci=CI_OK)})

    sensor = RepoCISensor(coordinator, REPO_KEYS[0])
    assert sensor.entity_id == "binary_sensor.work_hello_world_ci_ok"
    assert sensor.is_on is False
    assert sensor.available is True


async def test_ci_binary_sensor_fail(mock_hass, client):
    """A failing CI is ON — the problem state."""
    entry = _entry(mock_hass)
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    coordinator.data = DevopsBridgeData(repos={REPO_KEYS[0]: build_repo(ci=CI_FAIL)})

    sensor = RepoCISensor(coordinator, REPO_KEYS[0])
    assert sensor.is_on is True
    assert sensor.available is True


async def test_ci_binary_sensor_unavailable_while_running(mock_hass, client):
    """Running must mean unavailable, never a false fail."""
    entry = _entry(mock_hass)
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    coordinator.data = DevopsBridgeData(repos={REPO_KEYS[0]: build_repo(ci=CI_RUNNING)})

    sensor = RepoCISensor(coordinator, REPO_KEYS[0])
    assert sensor.available is False


async def test_ci_binary_sensor_unavailable_while_idle(mock_hass, client):
    entry = _entry(mock_hass)
    coordinator = DevopsBridgeCoordinator(mock_hass, entry, client, "work")
    coordinator.data = DevopsBridgeData(repos={REPO_KEYS[0]: build_repo(ci=CI_IDLE)})

    sensor = RepoCISensor(coordinator, REPO_KEYS[0])
    assert sensor.available is False


def _entry(mock_hass):
    from homeassistant.config_entries import ConfigEntry

    from .conftest import flow_options

    return ConfigEntry(
        version=1,
        domain=DOMAIN,
        title="Work",
        data=flow_options(),
        source="user",
        entry_id="test-entry",
        options={},
        minor_version=1,
        discovery_keys={},
        subentries_data=None,
        unique_id="octocat",
    )
