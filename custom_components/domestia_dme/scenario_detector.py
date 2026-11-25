"""Détection des scénarios et synchronisation d'état via trames Domestia DME-LAN."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Optional, Union

_LOGGER = logging.getLogger(__name__)

# Trame d'interrogation d'état des 36 sorties (7 octets)
STATUS_QUERY_FRAME = bytes.fromhex("ff 00 00 01 9c 9c 00")
STATUS_RESPONSE_HEADER = b"\xff\x00\xc0"


def load_scenarios_from_config(config_path: Union[str, Path]) -> dict[str, dict[str, Any]]:
    """Charge les définitions de scénarios depuis config.json."""
    path = Path(config_path)
    if not path.exists():
        _LOGGER.warning("Fichier de configuration introuvable pour les scénarios : %s", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as err:
        _LOGGER.error("Erreur lors de la lecture des scénarios dans %s : %s", path, err)
        return {}

    raw_scenarios = data.get("scenarios", {})
    triggers: dict[str, dict[str, Any]] = {}

    if isinstance(raw_scenarios, dict):
        for name, cfg in raw_scenarios.items():
            if not isinstance(cfg, dict) or "trigger_output" not in cfg:
                continue
            triggers[name] = {
                "trigger_output": int(cfg["trigger_output"]),
                "trigger_state": bool(cfg.get("trigger_state", True)),
                "reset_after_trigger": bool(cfg.get("reset_after_trigger", False)),
            }
    elif isinstance(raw_scenarios, list):
        for item in raw_scenarios:
            if not isinstance(item, dict) or "name" not in item or "trigger_output" not in item:
                continue
            triggers[item["name"]] = {
                "trigger_output": int(item["trigger_output"]),
                "trigger_state": bool(item.get("trigger_state", True)),
                "reset_after_trigger": bool(item.get("reset_after_trigger", False)),
            }

    _LOGGER.info("%d scénario(s) chargé(s) depuis %s.", len(triggers), path.name)
    return triggers


class ScenarioDetector:
    """Interroge périodiquement le DME-LAN, met à jour les états et détecte les scénarios."""

    def __init__(
        self,
        dme: Any,
        triggers: Optional[dict[str, dict[str, Any]]] = None,
        poll_interval: float = 1.5,
        on_scenario_detected: Optional[Callable[[str, int, bool], None]] = None,
    ) -> None:
        self.dme = dme
        self.triggers = triggers or {}
        self.poll_interval = max(0.5, float(poll_interval))
        self.on_scenario_detected = on_scenario_detected

        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_states: dict[int, bool] = {}
        self._initialized = False

    def _query_status_frame(self) -> bytes:
        """Envoie la trame d'interrogation d'état et retourne la réponse brute."""
        try:
            # _send_raw_command(0x01, [0x9C, 0x9C]) construit b"\xff\x00\x00\x01\x9c\x9c\x00"
            return self.dme._send_raw_command(0x01, [0x9C, 0x9C])
        except Exception as err:
            _LOGGER.debug("Échec de la lecture d'état DME-LAN : %s", err)
            return b""

    def process_frame(self, frame: bytes) -> None:
        """Analyse une trame de réponse ff 00 c0, met à jour les sorties et vérifie les déclencheurs."""
        if not frame or len(frame) < 39 or not frame.startswith(STATUS_RESPONSE_HEADER):
            return

        current_states: dict[int, bool] = {}
        for out_id in range(1, 37):
            # Octets 3..38 correspondent aux sorties 1..36 (0 = OFF, >0 = ON)
            raw_val = frame[2 + out_id]
            is_on = raw_val > 0
            current_states[out_id] = is_on

        with self._lock:
            # Synchronisation des états réels vers l'instance DomestiaDME
            if hasattr(self.dme, "states"):
                self.dme.states.update(current_states)

            # Au premier tour, on mémorise l'état initial sans déclencher de faux événements
            if not self._initialized:
                self._last_states = current_states.copy()
                self._initialized = True
                return

            for scenario_name, rule in self.triggers.items():
                out_id = rule["trigger_output"]
                target_state = rule["trigger_state"]

                prev_state = self._last_states.get(out_id, False)
                curr_state = current_states.get(out_id, False)

                # Détection sur front (changement vers l'état attendu)
                if curr_state == target_state and prev_state != target_state:
                    _LOGGER.debug(
                        "Déclenchement scénario '%s' via sortie %s -> %s",
                        scenario_name,
                        out_id,
                        curr_state,
                    )
                    if self.on_scenario_detected:
                        try:
                            self.on_scenario_detected(scenario_name, out_id, curr_state)
                        except Exception as cb_err:
                            _LOGGER.error(
                                "Erreur dans le callback scénario '%s' : %s",
                                scenario_name,
                                cb_err,
                            )

                    # Remise à zéro optionnelle de la sortie virtuelle après déclenchement
                    if rule.get("reset_after_trigger", False) and curr_state:
                        try:
                            self.dme.dim_output(out_id, 0)
                            current_states[out_id] = False
                            if hasattr(self.dme, "states"):
                                self.dme.states[out_id] = False
                        except Exception as rst_err:
                            _LOGGER.warning(
                                "Impossible de réinitialiser la sortie virtuelle %s : %s",
                                out_id,
                                rst_err,
                            )

            self._last_states = current_states.copy()

    def start(self) -> None:
        """Boucle bloquante de polling (à exécuter dans un thread dédié)."""
        _LOGGER.info(
            "Démarrage de la surveillance DME-LAN (intervalle : %.1fs, %d scénario(s)).",
            self.poll_interval,
            len(self.triggers),
        )
        self._stop_event.clear()

        while not self._stop_event.is_set():
            frame = self._query_status_frame()
            if frame:
                self.process_frame(frame)
            self._stop_event.wait(self.poll_interval)

        _LOGGER.info("Surveillance DME-LAN arrêtée.")

    def stop(self) -> None:
        """Arrête proprement la boucle de surveillance."""
        self._stop_event.set()
