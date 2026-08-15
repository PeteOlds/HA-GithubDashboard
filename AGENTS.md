# AGENTS.md

## What this repo is

A read-only Home Assistant custom integration (domain `devops_bridge`, display
name "GitHub Repo Monitor") that polls repository health across multiple GitHub
accounts and feeds a flex-table Lovelace dashboard. Apache-2.0. Being submitted
to the HACS default store — Validation must stay green.

## Layout

- `custom_components/devops_bridge/` — the integration: `api.py`, `coordinator.py`,
  `config_flow.py`, `sensor.py`, `binary_sensor.py`, `entity.py`, `const.py`,
  `diagnostics.py`, plus `translations/en.json` and `brand/`.
- `dashboard/` — the published copy of the Lovelace dashboard deliverable:
  `GithubDashboard.yaml` (the **authoritative entity contract**),
  `TemplateSensors.yaml`, `README.md` (install guide), `screenshots/`. Authored
  in the private Obsidian vault (`github/`), mirrored here so GitHub users can
  reach it; keep the two in sync.
- `tests/` — pytest suite using mocked HTTP (aioresponses); no live GitHub needed.
- `.github/workflows/` — `ci.yaml` (ruff + mypy + pytest) and `validate.yaml`
  (hassfest + HACS Action, strict).
- `hacs.json` — HACS metadata at repo root (display name, min HA, `render_readme`).

## Commands (from repo root, venv activated)

- Install: `pip install --config-settings editable_mode=compat -e ".[dev]"`
- Lint: `ruff check .` then `ruff format --check .`
- Typecheck: `mypy custom_components/devops_bridge`
- Tests: `python3 -m pytest` (CI gate: `--cov=custom_components.devops_bridge --cov-fail-under=75`)
- Single test: `python3 -m pytest tests/test_api.py::test_async_get_user -q`

## Hard-won gotchas

- **Python 3.14 only** (`requires-python >=3.14`, `homeassistant==2026.5.*`). Don't downgrade the matrix.
- **`editable_mode=compat` is mandatory** — plain `pip install -e .` breaks pytest collection via a broken PEP 660 `__path_hook__` finder.
- **`tests/conftest.py` ships a required aiohttp shim** — CI resolves aiohttp 3.13.5 (no `stream_writer` kwarg), local is 3.14.3 (requires it). Don't remove it.
- **Version is declared twice** — `manifest.json` and `pyproject.toml`; bump both together.
- **Releases are created manually in the GitHub web UI** — no token has release/fork/PR rights (`gh` keyring token is fine-grained). Tag `vX.Y.Z`, then draft the release *after* CI + Validation are green.
- **hassfest rules** — manifest keys sorted alphabetically after `domain`/`name`; a `homeassistant` key in `manifest.json` is invalid (that goes in `hacs.json`).
- **Brand assets live in `custom_components/devops_bridge/brand/`** (`icon.png`, `logo.png`, `@2x` variants) — not the repo root.
- **`device_class: problem` does NOT invert display.** HA renders ON as the
  problem/alert state, so `binary_sensor.*_ci_ok` is ON only when CI fails
  (`is_on = repo.ci == CI_FAIL`); a passing CI is OFF ("OK"). The original
  "PROBLEM inverts display" claim was wrong — don't reintroduce it.
- **HA caps entity state strings at 255 chars.** The `recent_activity` feed
  cannot live in the state; keep the state truncated and expose the full
  markdown via an attribute, or HA falls back to `unknown` and logs ERRORs.

## Conventions

- Display name is "GitHub Repo Monitor" but the domain stays `devops_bridge` — it's the package name and entity prefix; don't rename.
- Read-only by design; the only dashboard action is tap-through URLs to GitHub.
- Semantic commit prefixes (`feat:`, `fix:`, `docs:`).

## Dev test box

Optional Docker HA instance on port 9123 with this repo's `custom_components`
bind-mounted; the exact `docker run` command is in the README under
"Dev test box (Docker)".
