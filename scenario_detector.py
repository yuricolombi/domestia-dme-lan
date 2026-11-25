import json
import logging
from pathlib import Path
import socket
import time
from typing import Any, Callable, Dict, Optional, Union

try:
  from .dme_lan import DomestiaDME
except ImportError:
  from dme_lan import DomestiaDME

_LOGGER = logging.getLogger(__name__)


def load_scenarios_from_config(
    config_path: Union[str, Path]
) -> Dict[int, dict]:
  """Charge la section 'scenarios' depuis un fichier config.json."""
  path = Path(config_path)
  if not path.exists():
    _LOGGER.warning("Fichier de configuration introuvable : %s", path)
    return {}

  with path.open("r", encoding="utf-8") as f:
    data = json.load(f)

  raw_scenarios = data.get("scenarios", {})
  triggers: Dict[int, dict] = {}

  for out_id_str, cfg in raw_scenarios.items():
    try:
      out_id = int(out_id_str)
      triggers[out_id] = {
          "scenario": cfg["name"],
          "expected_on": bool(cfg["expected_on"]),
          "offset": int(cfg["offset"]),
      }
    except (KeyError, ValueError, TypeError) as err:
      _LOGGER.error(
          "Configuration de scénario invalide pour '%s' dans %s : %s",
          out_id_str,
          path,
          err,
      )

  return triggers


class ScenarioDetector:
  """Détecte les scénarios muraux en interrogeant périodiquement le contrôleur

  Domestia DME-LAN et en analysant les trames d'état 'ff 00 c0' reçues.
  """

  DEFAULT_SCENARIO_TRIGGERS: Dict[int, dict] = {}

  FRAME_HEADER = b"\xff\x00\xc0"
  POLL_PAYLOAD = b"\xff\x00\x00\x01\x9c\x9c\x00"

  def __init__(
      self,
      dme: DomestiaDME,
      triggers: Optional[Dict[int, dict]] = None,
      config_path: Optional[Union[str, Path]] = None,
      poll_interval: float = 1.5,
      reconnect_delay: float = 3.0,
      on_scenario_detected: Optional[Callable[[str, int, bool], None]] = None,
  ):
    self.dme = dme
    if triggers is not None:
      self.triggers = {int(k): v for k, v in triggers.items()}
    elif config_path is not None:
      self.triggers = load_scenarios_from_config(config_path)
    else:
      self.triggers = self.DEFAULT_SCENARIO_TRIGGERS.copy()

    self.poll_interval = poll_interval
    self.reconnect_delay = reconnect_delay
    self.on_scenario_detected = on_scenario_detected or self._default_handler
    self._last_values: Dict[int, int] = {}
    self._running = False

  def _default_handler(self, scenario_name: str, output_id: int, state: bool):
    etat_str = "ON" if state else "OFF"
    _LOGGER.info(
        "[SCÉNARIO DÉTECTÉ] '%s' (Sortie %s -> %s)",
        scenario_name,
        output_id,
        etat_str,
    )

  def process_frame(self, frame: bytes):
    """Analyse une trame complète commençant par FF 00 C0."""
    if not frame.startswith(self.FRAME_HEADER) or len(frame) < 30:
      return

    for out_id, cfg in self.triggers.items():
      offset = cfg.get("offset")
      if offset is None or offset >= len(frame):
        continue

      raw_val = frame[offset]
      prev_val = self._last_values.get(out_id)

      # Initialisation silencieuse à la première trame reçue
      if prev_val is None:
        self._last_values[out_id] = raw_val
        continue

      if raw_val != prev_val:
        is_on = raw_val > 0
        self._last_values[out_id] = raw_val
        if is_on == cfg["expected_on"]:
          self.on_scenario_detected(cfg["scenario"], out_id, is_on)

  def start(self):
    """Interroge en continu le contrôleur DME-LAN et analyse les trames 'ff 00 c0'."""
    if not self.triggers:
      _LOGGER.warning("Aucun scénario configuré dans ScenarioDetector.")

    self._running = True
    _LOGGER.info(
        "Écoute/interrogation DME-LAN sur %s:%s (intervalle=%ss)...",
        self.dme.ip,
        self.dme.tcp_port,
        self.poll_interval,
    )

    buffer = bytearray()

    while self._running:
      try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
          sock.settimeout(1.0)
          sock.connect((self.dme.ip, self.dme.tcp_port))
          _LOGGER.info("Connecté au contrôleur DME-LAN.")
          buffer.clear()
          last_poll = 0.0

          while self._running:
            now = time.monotonic()
            if now - last_poll >= self.poll_interval:
              sock.sendall(self.POLL_PAYLOAD)
              last_poll = now

            try:
              chunk = sock.recv(1024)
              if not chunk:
                _LOGGER.warning("Connexion fermée par le contrôleur.")
                break
              buffer.extend(chunk)

              while True:
                idx = buffer.find(self.FRAME_HEADER)
                if idx == -1:
                  if len(buffer) > 2:
                    del buffer[:-2]
                  break

                if idx > 0:
                  del buffer[:idx]

                next_idx = buffer.find(self.FRAME_HEADER, len(self.FRAME_HEADER))
                if next_idx != -1:
                  frame = bytes(buffer[:next_idx])
                  del buffer[:next_idx]
                  self.process_frame(frame)
                elif len(buffer) >= 195:
                  frame_len = 196 if len(buffer) >= 196 else 195
                  frame = bytes(buffer[:frame_len])
                  del buffer[:frame_len]
                  self.process_frame(frame)
                else:
                  break

            except TimeoutError:
              continue

      except KeyboardInterrupt:
        _LOGGER.info("Arrêt demandé par l'utilisateur.")
        self.stop()
        break
      except Exception as e:
        if self._running:
          _LOGGER.warning(
              "Erreur de connexion (%s), nouvelle tentative dans %ss...",
              e,
              self.reconnect_delay,
          )
          time.sleep(self.reconnect_delay)

  def stop(self):
    self._running = False
