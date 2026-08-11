"""Per-account DataUpdateCoordinator for the devops_bridge integration.

One coordinator per config entry (per account). It batches all GitHub API calls
for the selected repos into a single refresh and distributes the payload to the
entity platforms. Entities never poll independently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GitHubApiError,
    GitHubAuthenticationError,
    GitHubClient,
    GitHubError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    RepoData,
)
from .const import (
    CONF_LOGIN,
    CONF_REPO_MAP,
    CONF_REPOS,
    DOMAIN,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class DevopsBridgeData:
    """Payload distributed to all entity platforms for one account."""

    repos: dict[str, RepoData] = field(default_factory=dict)
    activity: str = ""


class DevopsBridgeCoordinator(DataUpdateCoordinator[DevopsBridgeData]):
    """Fetch aggregated per-repo snapshots for one account."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: GitHubClient,
        account_slug: str,
    ) -> None:
        self.client = client
        self.account_slug = account_slug
        self.repos: list[str] = list(entry.data.get(CONF_REPOS, []))
        self._repo_slugs: dict[str, str] = dict(entry.data.get(CONF_REPO_MAP, {}))
        self._login: str = entry.data.get(CONF_LOGIN, "")
        interval: timedelta = entry.options.get("update_interval", UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {account_slug}",
            update_interval=interval,
            config_entry=entry,
        )

    def repo_slug(self, repo_key: str) -> str:
        """Return the deterministic entity slug for a repo (collision-resolved)."""
        return self._repo_slugs.get(repo_key, repo_key.replace("/", "_"))

    async def _async_update_data(self) -> DevopsBridgeData:
        """Poll GitHub for every selected repo, batched and error-isolated."""
        try:
            repos = await self._async_refresh_all()
        except GitHubAuthenticationError as err:
            raise ConfigEntryAuthFailed("GitHub token invalid or expired") from err
        except GitHubRateLimitError as err:
            raise UpdateFailed(
                "GitHub rate limit reached",
                retry_after=err.retry_after,
            ) from err
        except GitHubApiError as err:
            raise UpdateFailed(f"GitHub API error: {err}") from err
        activity = await self._async_refresh_activity()
        return DevopsBridgeData(repos=repos, activity=activity)

    async def _async_refresh_activity(self) -> str:
        """Compose the per-account markdown feed (best-effort, never fatal)."""
        try:
            pairs = [
                (repo.partition("/")[0], repo.partition("/")[2])
                for repo in self.repos
            ]
            return await self.client.async_get_activity_markdown(
                self._login, repos=pairs
            )
        except GitHubError:
            return ""

    async def _async_refresh_all(self) -> dict[str, RepoData]:
        result: dict[str, RepoData] = {}
        for repo in self.repos:
            owner, _, repo_name = repo.partition("/")
            try:
                result[repo] = await self._async_update_repo(owner, repo_name)
            except (GitHubAuthenticationError, GitHubRateLimitError):
                # Account-wide conditions: bail out so the whole entry can
                # transition to reauth / backoff. Never mark individual repos.
                raise
            except GitHubNotFoundError:
                # Renamed/deleted repo: mark it unavailable, keep the rest alive.
                _LOGGER.warning(
                    "GitHub repo %s no longer exists; marking unavailable",
                    repo,
                )
                result[repo] = _unavailable_repo(owner, repo_name)
            except GitHubError as err:
                _LOGGER.warning("Failed to update repo %s: %s", repo, err)
                result[repo] = _unavailable_repo(owner, repo_name)
        self._log_unavailable_transitions(result)
        return result

    async def _async_update_repo(self, owner: str, repo_name: str) -> RepoData:
        repo_data = await self.client.async_get_repo(owner, repo_name)
        branch = repo_data.get("default_branch") or "main"
        open_pulls = await self.client.async_get_open_pulls(owner, repo_name)
        ci = await self.client.async_get_ci_status(owner, repo_name, branch)
        tag, published = await self.client.async_get_latest_release(owner, repo_name)
        return RepoData(
            owner=owner,
            repository=repo_name,
            url=str(repo_data.get("html_url") or ""),
            stars=int(repo_data.get("stargazers_count") or 0),
            forks=int(repo_data.get("forks_count") or 0),
            watchers=int(repo_data.get("subscribers_count") or 0),
            open_issues=int(repo_data.get("open_issues_count") or 0),
            open_pulls=open_pulls,
            ci=ci,
            latest_release=tag,
            release_date=published,
            pushed_at=str(repo_data.get("pushed_at") or ""),
        )

    def _log_unavailable_transitions(self, result: dict[str, RepoData]) -> None:
        """Log availability transitions once, never on every poll."""
        previous = self.data.repos if self.data else {}
        for repo, data in result.items():
            was_unavailable = previous.get(repo) is None or not previous[repo].available
            if was_unavailable and data.available:
                _LOGGER.info("GitHub repo %s is back online", repo)
            if not was_unavailable and not data.available:
                _LOGGER.warning("GitHub repo %s is unavailable", repo)


def _unavailable_repo(owner: str, repo_name: str) -> RepoData:
    """A RepoData marked unavailable (repo deleted, renamed, or errored)."""
    return RepoData(
        owner=owner,
        repository=repo_name,
        url="",
        stars=0,
        forks=0,
        watchers=0,
        open_issues=0,
        open_pulls=0,
        ci="idle",
        latest_release="",
        release_date="",
        pushed_at="",
        available=False,
    )


async def async_get_client(hass: HomeAssistant, token: str) -> GitHubClient:
    """Build a GitHub client using Home Assistant's shared web session."""
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(hass)
    return GitHubClient(session, token)


__all__ = ["DevopsBridgeCoordinator", "DevopsBridgeData", "RepoData"]