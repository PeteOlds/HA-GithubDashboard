"""Config flow for the devops_bridge integration.

Flow: account name -> token -> (test connection via GET /user, capture GitHub
login as the duplicate key) -> repo allowlist. Supports reauth and options
(repo re-selection) without deleting the entry.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GitHubApiError, GitHubAuthenticationError, GitHubClient, GitHubError
from .const import (
    CONF_ACCOUNT,
    CONF_LOGIN,
    CONF_REPO_MAP,
    CONF_REPOS,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    INTERVAL_CHOICES,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): str,
    }
)

STEP_TOKEN_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): str,
    }
)


def build_client(hass: HomeAssistant, token: str) -> GitHubClient:
    """Build a GitHub client on Home Assistant's shared web session."""
    return GitHubClient(async_get_clientsession(hass), token)


async def _test_and_get_login(
    hass: HomeAssistant, token: str
) -> tuple[str, GitHubClient]:
    """Validate the token via GET /user and return (login, client)."""
    client = build_client(hass, token)
    login = await client.async_get_user()
    return login, client


class DevopsBridgeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DevOps Bridge."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._account: str = ""
        self._login: str = ""
        self._token: str = ""
        self._client: GitHubClient | None = None
        self._repos: dict[str, str] = {}
        self._repo_map: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the account-name step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._account = user_input[CONF_ACCOUNT].strip()
            if not self._account:
                errors[CONF_ACCOUNT] = "required"
            else:
                return await self.async_step_token()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the token step, testing the connection and capturing login."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._token = user_input[CONF_TOKEN].strip()
            try:
                self._login, self._client = await _test_and_get_login(
                    self.hass, self._token
                )
            except GitHubAuthenticationError:
                errors[CONF_TOKEN] = "invalid_auth"
            except GitHubApiError:
                errors[CONF_TOKEN] = "cannot_connect"
            except Exception:  # noqa: BLE001 - unknown failure surfaces to HA
                errors[CONF_TOKEN] = "unknown"
            else:
                # Duplicate prevention: one entry per GitHub login.
                for entry in self._async_current_entries():
                    if entry.data.get(CONF_LOGIN) == self._login:
                        return self.async_abort(reason="already_configured")
                self._repos = await self._async_load_repos()
                return await self.async_step_repos()

        return self.async_show_form(
            step_id="token", data_schema=STEP_TOKEN_SCHEMA, errors=errors
        )

    async def async_step_repos(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle selection of repositories to monitor."""
        if user_input is not None:
            selected = list(user_input[CONF_REPOS])
            allowed = set(self._repos)
            self._repo_map = self._build_repo_map(selected)
            return self.async_create_entry(
                title=self._account,
                data={
                    CONF_ACCOUNT: self._account,
                    CONF_TOKEN: self._token,
                    CONF_LOGIN: self._login,
                    CONF_REPOS: [r for r in selected if r in allowed],
                    CONF_REPO_MAP: self._repo_map,
                },
            )

        return self.async_show_form(
            step_id="repos",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REPOS): cv.multi_select(self._repos),
                }
            ),
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reauth: provide a fresh token for the existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry_id = self.context.get("entry_id")
        if not isinstance(entry_id, str):
            return self.async_abort(reason="reauth_missing_entry")
        existing = self.hass.config_entries.async_get_entry(entry_id)
        if existing is None:
            return self.async_abort(reason="reauth_missing_entry")
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            try:
                login, _ = await _test_and_get_login(self.hass, token)
            except GitHubAuthenticationError:
                errors[CONF_TOKEN] = "invalid_auth"
            except GitHubApiError:
                errors[CONF_TOKEN] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors[CONF_TOKEN] = "unknown"
            else:
                data = {**existing.data, CONF_TOKEN: token, CONF_LOGIN: login}
                self.hass.config_entries.async_update_entry(existing, data=data)
                await self.hass.config_entries.async_reload(existing.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_TOKEN_SCHEMA,
            description_placeholders={"name": existing.title},
            errors=errors,
        )

    async def _async_load_repos(self) -> dict[str, str]:
        """Load selectable repos as {full_name: description-ish name}."""
        if self._client is None:
            return {}
        try:
            repos = await self._client.async_get_repos()
        except GitHubApiError:
            return {}
        return {str(repo["full_name"]): str(repo["full_name"]) for repo in repos}

    def _build_repo_map(self, selected: list[str]) -> dict[str, str]:
        """Resolve entity-slug collisions across selected repos (contract rule)."""
        seen: dict[str, str] = {}
        repo_map: dict[str, str] = {}
        for repo in selected:
            base = repo.split("/")[-1].lower()
            candidate = _slug(base)
            slug = candidate
            ordinal = 2
            while slug in seen.values():
                slug = f"{candidate}_{ordinal}"
                ordinal += 1
            seen[slug] = slug
            repo_map[repo] = slug
        return repo_map

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow for this integration."""
        return DevopsBridgeOptionsFlow(config_entry)


def _slug(value: str) -> str:
    """Deterministic repo slug: lowercase, `-` -> `_`, other non-alnum -> `_`."""
    import re

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


class DevopsBridgeOptionsFlow(OptionsFlow):
    """Options flow: change monitored repos and the poll schedule."""

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__()
        self._entry = entry
        self._repos: dict[str, str] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            selected = list(user_input[CONF_REPOS])
            interval = user_input[CONF_UPDATE_INTERVAL]
            return self.async_create_entry(
                data={
                    CONF_REPOS: selected,
                    CONF_REPO_MAP: self._build_map(selected),
                    CONF_UPDATE_INTERVAL: interval,
                }
            )
        await self._async_load_repos()
        if not self._repos:
            # Token-visible lookup failed (e.g. token scoped elsewhere): fall
            # back to the currently monitored set so options stay usable.
            self._repos = {repo: repo for repo in self._entry.data.get(CONF_REPOS, [])}
        current = list(self._entry.data.get(CONF_REPOS, []))
        current_interval = self._entry.options.get(
            CONF_UPDATE_INTERVAL, INTERVAL_CHOICES[1]
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REPOS, default=current): cv.multi_select(
                        self._repos
                    ),
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.In(INTERVAL_CHOICES),
                }
            ),
        )

    async def _async_load_repos(self) -> None:
        """Load the token-visible repos for the entry (best-effort)."""
        token = self._entry.data.get(CONF_TOKEN, "")
        try:
            client = build_client(self.hass, token)
            repos = await client.async_get_repos()
        except GitHubError:
            self._repos = {}
            return
        self._repos = {str(repo["full_name"]): str(repo["full_name"]) for repo in repos}

    def _build_map(self, selected: list[str]) -> dict[str, str]:
        seen: set[str] = set()
        repo_map: dict[str, str] = {}
        for repo in selected:
            base = _slug(repo.split("/")[-1])
            slug = base
            ordinal = 2
            while slug in seen:
                slug = f"{base}_{ordinal}"
                ordinal += 1
            seen.add(slug)
            repo_map[repo] = slug
        return repo_map
