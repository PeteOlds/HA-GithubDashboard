"""Async GitHub REST API client for the devops_bridge integration.

Read-only, authenticated with a fine-grained PAT, using Home Assistant's shared
aiohttp session. All errors map to a small typed hierarchy so the coordinator
can translate them into the correct HA failure behaviour (see the Integration
Guide section 2 "Lifecycle and error handling").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    ACTIVITY_EVENT_LIMIT,
    API_BASE,
    API_VERSION,
    CI_FAIL,
    CI_IDLE,
    CI_OK,
    CI_RUNNING,
    CONNECTION_TIMEOUT,
    USER_AGENT,
)


class GitHubError(Exception):
    """Base error for all GitHub API failures."""


class GitHubAuthenticationError(GitHubError):
    """Token invalid, expired, or lacking required scopes (401/403)."""


class GitHubRateLimitError(GitHubError):
    """Rate limited (429, or 403 with exhausted quota)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class GitHubNotFoundError(GitHubError):
    """A resource (repo, workflow) does not exist; scope to one repo only."""


class GitHubApiError(GitHubError):
    """All other non-success responses or transport failures."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class RepoData:
    """Normalized per-repository snapshot consumed by entities.

    Mirrors the summary-sensor attributes defined in ENTITY_CONTRACT.md.
    """

    def __init__(
        self,
        *,
        owner: str,
        repository: str,
        url: str,
        stars: int,
        forks: int,
        watchers: int,
        open_issues: int,
        open_pulls: int,
        ci: str,
        latest_release: str,
        release_date: str,
        pushed_at: str,
        available: bool = True,
    ) -> None:
        self.owner = owner
        self.repository = repository
        self.url = url
        self.stars = stars
        self.forks = forks
        self.watchers = watchers
        self.open_issues = open_issues
        self.open_pulls = open_pulls
        self.ci = ci
        self.latest_release = latest_release
        self.release_date = release_date
        self.pushed_at = pushed_at
        self.available = available

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable attribute dict consumed by the summary sensor."""
        return {
            "stars": self.stars,
            "forks": self.forks,
            "watchers": self.watchers,
            "open_issues": self.open_issues,
            "open_pulls": self.open_pulls,
            "ci": self.ci,
            "latest_release": self.latest_release,
            "release_date": self.release_date,
            "pushed_at": self.pushed_at,
            "available": self.available,
        }


class GitHubClient:
    """Thin async wrapper around the GitHub REST API (read-only)."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> tuple[int, Any]:
        url = f"{API_BASE}{path}"
        timeout = aiohttp.ClientTimeout(total=CONNECTION_TIMEOUT)
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                headers=self._headers(),
                timeout=timeout,
            ) as resp:
                status = resp.status
                if status in (401, 403):
                    await resp.read()
                    # 403 can mean token lacks scope OR rate limit in the new
                    # "secondary rate limit" style; 429 is the explicit one.
                    raise GitHubAuthenticationError(
                        f"Authentication failed with status {status}"
                    )
                if status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    await resp.read()
                    raise GitHubRateLimitError(
                        "GitHub rate limit reached",
                        retry_after=float(retry_after) if retry_after else None,
                    )
                if status == 404:
                    await resp.read()
                    raise GitHubNotFoundError(f"Resource not found: {path}")
                if status >= 500:
                    await resp.read()
                    raise GitHubApiError(
                        f"GitHub server error (status {status})", status=status
                    )
                if status >= 300:
                    await resp.read()
                    raise GitHubApiError(
                        f"GitHub error (status {status})", status=status
                    )
                try:
                    return status, await resp.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise GitHubApiError("Invalid JSON from GitHub") from err
        except TimeoutError as err:
            raise GitHubApiError("Timeout talking to GitHub") from err
        except aiohttp.ClientError as err:
            raise GitHubApiError(f"Network error talking to GitHub: {err}") from err

    async def async_get_user(self) -> str:
        """Return the authenticated account's GitHub login (duplicate key)."""
        _, data = await self._request("GET", "/user")
        login = data.get("login")
        if not login:
            raise GitHubApiError("GitHub /user response missing login")
        return str(login)

    async def async_get_repos(self) -> list[dict[str, Any]]:
        """List repositories the token can read (owner + collaborator)."""
        repos: list[dict[str, Any]] = []
        params = {"per_page": 100, "affiliation": "owner,collaborator"}
        page = 1
        while True:
            page_params = {**params, "page": page}
            _, data = await self._request("GET", "/user/repos", params=page_params)
            if not isinstance(data, list):
                raise GitHubApiError("GitHub /user/repos returned unexpected data")
            repos.extend(data)
            if len(data) < 100:
                break
            page += 1
        return repos

    async def async_get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Fetch core repo metadata."""
        _, data = await self._request("GET", f"/repos/{quote(owner)}/{quote(repo)}")
        return dict(data)

    async def async_get_open_pulls(self, owner: str, repo: str) -> int:
        """Count open pull requests (paginated count)."""
        params = {"state": "open", "per_page": 100}
        count = 0
        page = 1
        while True:
            _, data = await self._request(
                "GET",
                f"/repos/{quote(owner)}/{quote(repo)}/pulls",
                params={**params, "page": page},
            )
            if not isinstance(data, list):
                raise GitHubApiError("GitHub /pulls returned unexpected data")
            count += len(data)
            if len(data) < 100:
                break
            page += 1
        return count

    async def async_get_ci_status(self, owner: str, repo: str, branch: str) -> str:
        """Return ok/fail/running/idle for the default-branch workflow runs.

        Absent or disabled Actions -> idle (a distinct state, not a fail).
        """
        params = {"per_page": 1, "branch": branch}
        try:
            _, data = await self._request(
                "GET",
                f"/repos/{quote(owner)}/{quote(repo)}/actions/runs",
                params=params,
            )
        except GitHubNotFoundError:
            # No Actions at all (403 when disabled arrives as auth error below).
            return CI_IDLE
        except GitHubAuthenticationError:
            # Actions disabled -> fine-grained token gets 403.
            return CI_IDLE

        runs = data.get("workflow_runs") or []
        if not runs:
            return CI_IDLE
        latest = runs[0]
        status = latest.get("status")
        if status in ("queued", "in_progress", "waiting"):
            return CI_RUNNING
        if status == "completed":
            conclusion = latest.get("conclusion")
            if conclusion == "success":
                return CI_OK
            if conclusion is not None:
                return CI_FAIL
        return CI_IDLE

    async def async_get_latest_release(self, owner: str, repo: str) -> tuple[str, str]:
        """Return (tag, published_at). (\"\", \"\") when no release exists."""
        try:
            _, data = await self._request(
                "GET",
                f"/repos/{quote(owner)}/{quote(repo)}/releases/latest",
            )
        except GitHubNotFoundError:
            return "", ""
        tag = data.get("tag_name") or ""
        published = data.get("published_at") or ""
        return str(tag), str(published)

    async def async_get_activity_markdown(
        self,
        login: str,
        *,
        repos: list[tuple[str, str]],
    ) -> str:
        """Compose a bounded markdown feed of recent public events.

        Uses the per-account public events endpoint. Falls back gracefully to an
        empty string if that endpoint is unavailable (it can be for very new
        accounts) — a missing feed must never kill the coordinator.
        """
        if not repos:
            return ""
        params = {"per_page": ACTIVITY_EVENT_LIMIT}
        try:
            _, data = await self._request(
                "GET", f"/users/{quote(login)}/events/public", params=params
            )
        except GitHubError:
            return ""

        lines: list[str] = []
        for event in data if isinstance(data, list) else []:
            repo_name = (event.get("repo") or {}).get("name") or ""
            etype = event.get("type") or "PushEvent"
            created = _format_isodate(event.get("created_at"))
            if not repo_name:
                continue
            lines.append(f"- `{repo_name}` · {etype} · {created}")
        if not lines:
            return ""
        return "\n".join(lines)


def _format_isodate(value: Any) -> str:
    """Return a compact datetime string, or empty when unparseable."""
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(
            "%Y-%m-%d %H:%M"
        )
    except ValueError, TypeError:
        return str(value)
