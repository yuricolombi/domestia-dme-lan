from dme_lan import DomestiaDME

dme = DomestiaDME()

# Test de différentes commandes de lecture possibles sur le port TCP (52001)
for cmd, data in [
    (0x01, [0x00]),
    (0x01, [0x10]),
    (0x02, [0x00]),
    (0x04, [0x00]),
    (0x05, [0x00]),
]:
  resp = dme._send_raw_command(cmd, data)
  print(f"CMD={cmd:#04x} DATA={data} -> len={len(resp)}")
  if resp:
    print("  HEX :", resp.hex(" ").upper())
    print("  DEC :", list(resp))
