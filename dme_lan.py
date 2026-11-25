import json
import logging
from pathlib import Path
import socket
from typing import Any, Dict, List, Optional, Union

_LOGGER = logging.getLogger(__name__)


class DomestiaDME:
  """Contrôleur de communication TCP avec le module Domestia DME-LAN."""

  def __init__(
      self,
      ip: str = "192.168.1.100",
      tcp_port: int = 52001,
      status_port: int = 55001,
      config_file: Optional[Union[str, Path]] = None,
      outputs: Optional[List[Dict[str, Any]]] = None,
  ):
    self.ip = ip
    self.tcp_port = tcp_port
    self.status_port = status_port
    self.output_configs: Dict[int, Dict[str, Any]] = {}
    self.states: Dict[int, bool] = {}
    self.apartment_occupied = True  # Présence par défaut

    if outputs is not None:
      self.load_outputs(outputs)
    elif config_file is not None:
      self.load_config(config_file)

  def load_outputs(self, items: List[Dict[str, Any]]) -> None:
    """Charge la configuration des sorties depuis une liste de dictionnaires."""
    for item in items:
      output_id = int(item["id"])
      profile = item.get("dimmer_profile") or item.get("profile", "non_dimmable")
      self.output_configs[output_id] = {
          "name": item.get("name", f"Output {output_id}"),
          "area": item.get("area"),
          "entity_type": item.get("entity_type", "light"),
          "profile": profile,
          "enabled": item.get("enabled", True),
          "permanent_light": item.get("permanent_light", False),
          "min_on": item.get("min_on", 11),
          "min_dim": item.get("min_dim", 9),
      }
    _LOGGER.info(
        "Configuration chargée : %d sorties configurées.",
        len(self.output_configs),
    )

  def load_config(self, filepath: Union[str, Path]) -> None:
    """Charge la configuration depuis config.json (ou un ancien tableau JSON)."""
    try:
      with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

      if isinstance(data, dict):
        ctrl = data.get("controller", {})
        if "host" in ctrl and self.ip == "192.168.1.100":
          self.ip = ctrl["host"]
        if "port" in ctrl and self.tcp_port == 52001:
          self.tcp_port = int(ctrl["port"])
        items = data.get("outputs", [])
      elif isinstance(data, list):
        items = data
      else:
        raise ValueError("Format JSON non reconnu (dict ou list attendu).")

      self.load_outputs(items)
    except Exception as e:
      _LOGGER.error(
          "Impossible de charger le fichier de configuration (%s) : %s",
          filepath,
          e,
      )

  def set_presence(self, occupied: bool) -> None:
    """Gère le mode présence/absence pour les éclairages permanents."""
    self.apartment_occupied = occupied
    if not occupied:
      _LOGGER.info("Appartement vacant : extinction des veilleuses permanentes.")
      for out_id, cfg in self.output_configs.items():
        if cfg.get("permanent_light", False):
          self._send_raw_command(0x03, [0x10, out_id, 0])
    else:
      _LOGGER.info("Appartement occupé : rallumage des veilleuses permanentes.")
      for out_id, cfg in self.output_configs.items():
        if cfg.get("permanent_light", False):
          self._send_raw_command(0x03, [0x10, out_id, 64])

  def _calculate_checksum(self, data: list) -> int:
    return sum(data) % 256

  def _build_frame(self, command: int, data: list) -> bytes:
    header = b"\xff\x00\x00"
    chk = self._calculate_checksum(data)
    return header + bytes([command] + data + [chk])

  def _send_raw_command(self, command: int, data: list) -> bytes:
    payload = self._build_frame(command, data)
    try:
      with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(3.0)
        s.connect((self.ip, self.tcp_port))
        s.sendall(payload)
        return s.recv(1024)
    except Exception as e:
      _LOGGER.error("Connexion TCP échouée (%s:%s) : %s", self.ip, self.tcp_port, e)
      return b""

  def toggle_output(self, output_id: int) -> None:
    """Bascule l'état d'une sortie."""
    self._send_raw_command(0x02, [0x0D, output_id])
    self.states[output_id] = not self.states.get(output_id, False)

  def dim_output(self, output_id: int, percentage: int) -> None:
    """Règle l'intensité selon le profil (standard, hysteresis, switch/non_dimmable)."""
    config = self.output_configs.get(
        output_id, {"name": f"Output {output_id}", "profile": "non_dimmable", "permanent_light": False}
    )

    # Protection des éclairages permanents
    if (
        config.get("permanent_light", False)
        and percentage == 0
        and self.apartment_occupied
    ):
      _LOGGER.info("Protection : La sortie '%s' reste allumée.", config["name"])
      return

    percentage = max(0, min(100, percentage))
    profile = config["profile"]

    if profile in ("switch", "non_dimmable"):
      internal_level = 64 if percentage > 0 else 0

    elif profile == "hysteresis":
      min_on = config.get("min_on", 11)
      min_dim = config.get("min_dim", 9)
      is_on = self.states.get(output_id, False)

      if percentage == 0:
        internal_level = 0
      else:
        active_min = min_dim if is_on else min_on
        target_pct = max(percentage, active_min)

        min_internal = round((active_min * 64) / 100)
        if target_pct >= 100:
          internal_level = 64
        else:
          ratio = (target_pct - active_min) / (100 - active_min)
          internal_level = round(min_internal + ratio * (64 - min_internal))

        internal_level = max(min_internal, min(64, internal_level))

    else:  # standard
      if percentage == 0:
        internal_level = 0
      else:
        internal_level = round((percentage * 64) / 100)
        internal_level = max(1, min(64, internal_level))

    self.states[output_id] = internal_level > 0

    _LOGGER.debug(
        "Sortie %s (%s) -> %s%% calculé en niveau matériel: %s/64",
        output_id,
        config["name"],
        percentage,
        internal_level,
    )

    self._send_raw_command(0x03, [0x10, output_id, internal_level])
