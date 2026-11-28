"""Plateforme Light pour Domestia DME-LAN."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
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
  """Crée les entités lumière à partir des sorties actives de config.json."""
  if discovery_info is None:
    return

  dme: DomestiaDME = hass.data[DOMAIN]["dme"]
  entities: list[DomestiaLight] = []

  for out_id, cfg in sorted(dme.output_configs.items()):
    if not cfg.get("enabled", True):
      continue
    if cfg.get("entity_type", "light") != "light":
      continue
    entities.append(DomestiaLight(dme, out_id, cfg))

  _LOGGER.debug("Domestia lights créées : %s", [e.unique_id for e in entities])
  async_add_entities(entities)


class DomestiaLight(LightEntity):
  """Représentation d'une sortie d'éclairage Domestia DME-LAN."""

  _attr_should_poll = True

  def __init__(
      self, dme: DomestiaDME, output_id: int, cfg: dict[str, Any]
  ) -> None:
    self._dme = dme
    self._output_id = output_id
    self._cfg = cfg

    self._attr_name = cfg.get("name", f"Domestia Light {output_id}")
    self._attr_unique_id = f"{DOMAIN}_light_{output_id}"
    self._attr_brightness = 255

    profile = cfg.get("dimmer_profile") or cfg.get("profile", "non_dimmable")
    if profile in ("standard", "hysteresis"):
      self._attr_color_mode = ColorMode.BRIGHTNESS
      self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    else:
      self._attr_color_mode = ColorMode.ONOFF
      self._attr_supported_color_modes = {ColorMode.ONOFF}

    _LOGGER.debug(
        "Init light %s (id=%s, profile=%s, color_mode=%s, state_init=%s)",
        self._attr_name,
        self._output_id,
        profile,
        self._attr_color_mode,
        self._dme.states.get(self._output_id),
    )

  @property
  def is_on(self) -> bool:
    return bool(self._dme.states.get(self._output_id, False))

  async def async_turn_on(self, **kwargs: Any) -> None:
    current_state = self.is_on
    raw_state = self._dme.states.get(self._output_id)

    if (
        ATTR_BRIGHTNESS in kwargs
        and ColorMode.BRIGHTNESS in self.supported_color_modes
    ):
      brightness = int(kwargs[ATTR_BRIGHTNESS])
      self._attr_brightness = brightness
      pct = max(1, round((brightness / 255) * 100))
      _LOGGER.debug(
          "Light %s (id=%s) turn_on avec luminosité: brightness=%s -> pct=%s"
          " (is_on=%s, raw_state=%s)",
          self._attr_name,
          self._output_id,
          brightness,
          pct,
          current_state,
          raw_state,
      )
      await self.hass.async_add_executor_job(
          self._dme.dim_output, self._output_id, pct
      )
    else:
      _LOGGER.debug(
          "Light %s (id=%s) turn_on simple (sans brightness): is_on=%s,"
          " raw_state=%s, kwargs=%s",
          self._attr_name,
          self._output_id,
          current_state,
          raw_state,
          kwargs,
      )
      if not current_state:
        _LOGGER.debug(
            "Light %s (id=%s) envoi toggle_output (is_on était False)",
            self._attr_name,
            self._output_id,
        )
        await self.hass.async_add_executor_job(
            self._dme.toggle_output, self._output_id
        )
      else:
        _LOGGER.debug(
            "Light %s (id=%s) déjà marquée ON (is_on=True), toggle_output"
            " ignoré",
            self._attr_name,
            self._output_id,
        )

    self.async_write_ha_state()

  async def async_turn_off(self, **kwargs: Any) -> None:
    current_state = self.is_on
    raw_state = self._dme.states.get(self._output_id)
    _LOGGER.debug(
        "Light %s (id=%s) turn_off: is_on=%s, raw_state=%s",
        self._attr_name,
        self._output_id,
        current_state,
        raw_state,
    )
    if current_state:
      _LOGGER.debug(
          "Light %s (id=%s) envoi toggle_output (is_on était True)",
          self._attr_name,
          self._output_id,
      )
      await self.hass.async_add_executor_job(
          self._dme.toggle_output, self._output_id
      )
    else:
      _LOGGER.debug(
          "Light %s (id=%s) déjà marquée OFF (is_on=False), toggle_output"
          " ignoré",
          self._attr_name,
          self._output_id,
      )

    self.async_write_ha_state()
