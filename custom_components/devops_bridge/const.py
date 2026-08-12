"""Constants for the devops_bridge integration."""

from datetime import timedelta

DOMAIN = "devops_bridge"
NAME = "GitHub Repo Monitor"

PLATFORMS = ["binary_sensor", "sensor"]

CONF_ACCOUNT = "account"
CONF_TOKEN = "token"
CONF_LOGIN = "login"
CONF_REPOS = "repos"
CONF_REPO_MAP = "repo_map"
CONF_UPDATE_INTERVAL = "update_interval"

# Options-flow choices for the poll interval (minutes).
INTERVAL_CHOICES = [5, 10, 15, 30, 60]

UPDATE_INTERVAL = timedelta(minutes=10)
CONNECTION_TIMEOUT = 10

API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "HomeAssistant/devops_bridge"

# CI states (contract `ci` attribute).
CI_OK = "ok"
CI_FAIL = "fail"
CI_RUNNING = "running"
CI_IDLE = "idle"

# How many events to keep in the per-account activity feed.
ACTIVITY_EVENT_LIMIT = 20
