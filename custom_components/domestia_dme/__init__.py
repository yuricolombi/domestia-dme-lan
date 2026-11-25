"""Initialisation de l'intégration Domestia DME-LAN."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    DEFAULT_CONFIG_FILE,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    EVENT_SCENARIO_DETECTED,
    PLATFORMS,
)
from .dme_lan import DomestiaDME
from .scenario_detector import ScenarioDetector, load_scenarios_from_config

_LOGGER = logging.getLogger(__name__)


def _read_config(path: Path) -> dict[str, Any]:
    """Lit le fichier config.json (exécuté hors boucle événementielle)."""
    if not path.exists():
        _LOGGER.error("Fichier de configuration introuvable : %s", path)
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Configure le composant Domestia DME-LAN depuis configuration.yaml + config.json."""
    if DOMAIN not in config:
        return True

    config_path = Path(hass.config.path("custom_components", DOMAIN, DEFAULT_CONFIG_FILE))
    local_cfg = await hass.async_add_executor_job(_read_config, config_path)

    if not local_cfg:
        _LOGGER.error("Impossible de démarrer %s sans config.json valide.", DOMAIN)
        return False

    ctrl = local_cfg.get("controller", {})
    host = ctrl.get(CONF_HOST)
    if not host:
        _LOGGER.error("Paramètre 'controller.host' manquant dans %s.", config_path)
        return False

    port = int(ctrl.get(CONF_PORT, DEFAULT_PORT))
    poll_interval = float(ctrl.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
    outputs = local_cfg.get("outputs", [])

    dme = DomestiaDME(ip=host, tcp_port=port, outputs=outputs)

    triggers = await hass.async_add_executor_job(
        load_scenarios_from_config, config_path
    )

    def on_scenario_detected(scenario_name: str, output_id: int, state: bool) -> None:
        """Relaye les scénarios détectés vers le bus d'événements Home Assistant."""
        _LOGGER.info(
            "Événement scénario '%s' (sortie %s -> %s)",
            scenario_name,
            output_id,
            "ON" if state else "OFF",
        )
        hass.bus.async_fire(
            EVENT_SCENARIO_DETECTED,
            {
                "scenario": scenario_name,
                "output_id": output_id,
                "state": state,
            },
        )

    detector = ScenarioDetector(
        dme,
        triggers=triggers,
        poll_interval=poll_interval,
        on_scenario_detected=on_scenario_detected,
    )

    hass.data[DOMAIN] = {
        "dme": dme,
        "detector": detector,
        "config": local_cfg,
    }

    # Démarrage de la boucle de détection dans un thread dédié
    hass.async_add_executor_job(detector.start)

    async def _stop_detector(_event: Any) -> None:
        detector.stop()

    hass.bus.async_listen_once("homeassistant_stop", _stop_detector)

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, {}, config)
        )

    return True
