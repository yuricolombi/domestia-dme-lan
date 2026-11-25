import json
from pathlib import Path
import sys

# Permet d'exécuter le script depuis la racine du projet ou depuis scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

try:
  from custom_components.domestia_dme.dme_lan import DomestiaDME
except ImportError:
  from dme_lan import DomestiaDME

CONFIG_PATH = PROJECT_ROOT / "custom_components" / "domestia_dme" / "config.json"


def load_controller_params(config_path: Path) -> tuple[str, int]:
  """Lit l'IP et le port du contrôleur depuis config.json."""
  if not config_path.exists():
    raise FileNotFoundError(
        f"Fichier de configuration introuvable : {config_path}\n"
        "Copiez config.example.json vers config.json et renseignez votre IP."
    )
  with config_path.open("r", encoding="utf-8") as f:
    cfg = json.load(f)
  ctrl = cfg.get("controller", {})
  return ctrl.get("host", "192.168.1.100"), int(ctrl.get("port", 52001))


def main():
  host, port = load_controller_params(CONFIG_PATH)
  # Adaptez les arguments si votre DomestiaDME attend un chemin de config spécifique
  dme = DomestiaDME(ip=host, tcp_port=port)

  while True:
    print("\n=== DOMESTIA DME-LAN MODULAIRE ===")
    print("1. Inverser une sortie (Toggle)")
    print("2. Contrôler un variateur (Dimmer)")
    print("3. Afficher l'état de toutes les sorties")
    print("4. Quitter")

    choix = input("Choisissez une option (1-4) : ").strip()

    if choix == "1":
      try:
        num = int(input("Numéro de sortie (1-36) : "))
        if 1 <= num <= 36:
          dme.toggle_output(num)
          print(f"[ACTION] Commande toggle envoyée pour la sortie {num}")
        else:
          print("[ERREUR] Le numéro de sortie doit être compris entre 1 et 36.")
      except ValueError:
        print("[ERREUR] Veuillez entrer un nombre valide.")

    elif choix == "2":
      try:
        num = int(input("Numéro de sortie (1-36) : "))
        if 1 <= num <= 36:
          niveau_pct = int(input("Niveau en pourcentage (0 à 100) : "))
          dme.dim_output(num, niveau_pct)
          print(
              f"[ACTION] Sortie {num} réglée à {niveau_pct}% (avec prise en"
              " compte du profil)"
          )
        else:
          print("[ERREUR] Le numéro de sortie doit être compris entre 1 et 36.")
      except ValueError:
        print("[ERREUR] Veuillez entrer des valeurs numériques valides.")

    elif choix == "3":
      print("\n--- ÉTAT DES SORTIES ---")
      for out_id, config in sorted(dme.output_configs.items()):
        etat = "ON" if dme.states.get(out_id, False) else "OFF"
        perm = " (Permanent)" if config.get("permanent_light", False) else ""
        area = config.get("area") or "-"
        profile = config.get("dimmer_profile") or config.get("profile", "-")
        print(
            f"Sortie {out_id:2d} | {config['name']:<25} | Zone: "
            f"{area:<20} | Profil: {profile:<12} | État: {etat}{perm}"
        )

    elif choix == "4":
      print("Fermeture du programme. Au revoir !")
      break
    else:
      print("[ERREUR] Option invalide, veuillez choisir entre 1 et 4.")


if __name__ == "__main__":
  main()
