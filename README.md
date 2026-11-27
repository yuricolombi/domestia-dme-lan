# Domestia DME-LAN pour Home Assistant

Intégration personnalisée pour Home Assistant permettant de piloter et de surveiller un contrôleur domotique **Domestia DME-LAN** via le réseau local (TCP, port `52001`), avec prise en charge des éclairages (gradateurs et profils d'hystérésis), des interrupteurs et de la détection des scénarios.

Attention: faute de disposer de la documentation, le comportement de Domestia a été obervé via les échanges sur le LAN. Il est possible que ceux-ci soient mal interprètés !

## Fonctionnalités

* **Communication locale TCP** avec le contrôleur DME-LAN (`port 52001` par défaut).
* **Entités `light`** : commande marche/arrêt, variation de luminosité et gestion des profils d'hystérésis.
* **Entités `switch`** : commande marche/arrêt des sorties relais/interrupteurs.
* **Synchronisation d'état et détection de scénarios (`ScenarioDetector`)** : interrogation périodique des trames d'état (`ff 00 c0`), mise à jour des sorties et émission de l'événement `domestia_dme_scenario_detected` lors du déclenchement d'un scénario.
* **Scripts utilitaires** (`scripts/main.py`, `scripts/probe_status.py`) pour les tests et l'analyse des trames hors Home Assistant.

## Structure du dépôt

```text
.
├── custom_components/
│   └── domestia_dme/
│       ├── __init__.py
│       ├── const.py
│       ├── dme_lan.py
│       ├── light.py
│       ├── manifest.json
│       ├── scenario_detector.py
│       └── switch.py
├── scripts/
│   ├── main.py
│   └── probe_status.py
├── .gitignore
├── LICENSE
└── README.md
