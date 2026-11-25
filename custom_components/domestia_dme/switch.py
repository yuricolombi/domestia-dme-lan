"""Plateforme Switch pour Domestia DME-LAN."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN
from .dme_lan import DomestiaDME

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Crée les entités interrupteur à partir des sorties actives de config.json."""
    if discovery_info is None:
        return

    dme: DomestiaDME = hass.data[DOMAIN]["dme"]
    entities: list[DomestiaSwitch] = []

    for out_id, cfg in sorted(dme.output_configs.items()):
        if not cfg.get("enabled", True):
            continue
        if cfg.get("entity_type") != "switch":
            continue
        entities.append(DomestiaSwitch(dme, out_id, cfg))

    async_add_entities(entities)


class DomestiaSwitch(SwitchEntity):
    """Représentation d'une sortie tout-ou-rien Domestia DME-LAN."""

    _attr_should_poll = True

    def __init__(self, dme: DomestiaDME, output_id: int, cfg: dict[str, Any]) -> None:
        self._dme = dme
        self._output_id = output_id
        self._attr_name = cfg.get("name", f"Domestia Switch {output_id}")
        self._attr_unique_id = f"{DOMAIN}_switch_{output_id}"

    @property
    def is_on(self) -> bool:
        return bool(self._dme.states.get(self._output_id, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            self._dme.dim_output, self._output_id, 100
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            self._dme.dim_output, self._output_id, 0
        )
        self.async_write_ha_state()
