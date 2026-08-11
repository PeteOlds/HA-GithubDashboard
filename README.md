# DevOps Bridge

A read-only [Home Assistant](https://www.home-assistant.io/) custom integration
for GitHub that polls repository health across **multiple accounts** and feeds a
Lovelace dashboard (`GithubDashboard.yaml`).

Works with [flex-table-card](https://github.com/custom-cards/flex-table-card) to
render one row per repository with click-through to GitHub.

**This is a design-first deliverable.** The entity contract the dashboard
expects is specified in the project's design vault (see the Integration Guide,
`ENTITY_CONTRACT.md`, `INTEGRATION_SPEC.md`, and `dashboard/GithubDashboard.yaml`
for the authoritative agreement the code must match).

## Features

- Multiple GitHub accounts; one config entry per account.
- One `DataUpdateCoordinator` per account (batched polling, no per-entity
  requests).
- Per-repository summary sensor with attributes driving the flex-table
  (account, repository, url, stars, forks, watchers, open_issues, open_pulls,
  ci, latest_release, release_date, pushed_at).
- Metric sensors for tiles, plus a `binary_sensor` for CI on/off.
- Per-account "recent activity" feed (markdown text as state).
- Configurable poll interval (5–60 min) and repo allowlist via Options.
- Read-only by design: the only action in the Dashboard is `tap_action: url`.

## Installation

Requires **Home Assistant Core 2026.5 or later**.

1. Copy `custom_components/devops_bridge/` into your
   `config/custom_components/devops_bridge/` (or install via HACS).
2. Add the dashboard via the raw config editor
   (`dashboard/GithubDashboard.yaml`) and merge
   `dashboard/TemplateSensors.yaml` into `configuration.yaml` for the overview
   aggregates.
3. Settings → Devices & services → Add integration → **DevOps Bridge**.
4. Enter an account name (a friendly label, e.g. `Work`), then a read-only PAT.

### Token scopes

Use a **fine-grained Personal Access Token**, read-only:

- **Actions:** Read
- **Contents:** Read
- **Issues:** Read
- **Metadata:** Read (always on)
- **Pull requests:** Read

Restrict it to the repositories you want to monitor. The token is stored in the
config entry and never logged or committed.

### Creating the token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens**
   → **Fine-grained tokens** → **Generate new token**.
2. Name it (e.g. `Home Assistant (Work)`), set a short expiry, and choose
   **Only select repositories** for the repos you want to monitor.
3. Under **Permissions** set exactly these to **Read-only** (all others stay at
   *No access*): Actions, Contents, Issues, Pull requests, Metadata.
4. **Generate token** and copy it immediately — GitHub shows it only once.
5. In HA: Settings → Devices & services → **Add integration** → **DevOps
   Bridge**, enter the account name, paste the token, select repos.

### Adjusting later

From Settings → Devices & services → DevOps Bridge → **Options** you can:

- Change which repositories are monitored (add or remove from the ones the
  token can see).
- Change the poll interval (default 10 minutes; 5–60 minutes available).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy custom_components/devops_bridge
pytest
```

Tests use mocked HTTP fixtures — no live GitHub account required.

### Dev test box (Docker)

A dedicated Home Assistant container on port **9123** (separate from any live
instance), with this repo's `custom_components` bind-mounted in so edits appear
without rebuilding:

```bash
docker run -d \
  --name ha-dev --restart unless-stopped \
  -p 9123:8123 \
  -v /mnt/General/ha-dev/config:/config \
  -v /mnt/General/OpenCode/HA-GithubDashboard/custom_components/devops_bridge:/config/custom_components/devops_bridge \
  -e TZ=Pacific/Auckland \
  ghcr.io/home-assistant/home-assistant:stable
```

Open `http://localhost:9123` to complete onboarding. The integration shows up
under Add integration → **DevOps Bridge**; a smoke test with a throwaway
read-only PAT is the release gate.

## Documentation

The entity contract, integration architecture, and dashboard design live in the
project's Obsidian vault under `github/` and are referenced from `AGENTS.md`
there. This repository is the code home for `custom_components/devops_bridge/`.

## Licence

Apache-2.0 — see [LICENSE](LICENSE).