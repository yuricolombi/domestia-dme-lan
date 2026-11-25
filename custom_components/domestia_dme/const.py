"""Constantes pour l'intégration Domestia DME-LAN."""

DOMAIN = "domestia_dme"
PLATFORMS = ["light", "switch"]

CONF_HOST = "host"
CONF_PORT = "port"
CONF_POLL_INTERVAL = "poll_interval"

DEFAULT_PORT = 52001
DEFAULT_POLL_INTERVAL = 1.5
DEFAULT_CONFIG_FILE = "config.json"

EVENT_SCENARIO_DETECTED = f"{DOMAIN}_scenario_detected"
