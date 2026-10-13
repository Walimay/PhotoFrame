#!/usr/bin/env python3
"""Importa foto nell'archivio da riga di comando.

Stessa elaborazione dell'upload da pagina web: entrambi passano da
common/images.py.

    python3 scripts/import_photos.py ~/foto/
    python3 scripts/import_photos.py ~/foto/*.jpg --fit cover
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import db, images  # noqa: E402
from common.config import ensure_dirs  # noqa: E402


def raccogli(percorsi):
    trovati = []
    for voce in percorsi:
        percorso = Path(voce).expanduser()
        if percorso.is_dir():
            trovati += [p for p in sorted(percorso.rglob("*"))
                        if p.suffix.lower() in images.ESTENSIONI]
        elif percorso.suffix.lower() in images.ESTENSIONI:
            trovati.append(percorso)
    return trovati


def main():
    parser = argparse.ArgumentParser(description="Importa foto nella cornice")
    parser.add_argument("percorsi", nargs="+", help="file o cartelle")
    parser.add_argument("--fit", choices=["contain", "cover"],
                        help="sovrascrive l'impostazione salvata")
    argomenti = parser.parse_args()

    ensure_dirs()
    con = db.init()
    modalita = argomenti.fit or db.get_setting(con, "photo_fit", "contain")

    file_trovati = raccogli(argomenti.percorsi)
    if not file_trovati:
        print("Nessuna immagine trovata.")
        return 1

    importate = 0
    inizio = time.monotonic()
    for percorso in file_trovati:
        avvio = time.monotonic()
        try:
            dati = images.importa(percorso, percorso.name, modalita)
        except Exception as errore:                       # noqa: BLE001
            print(f"  salto {percorso.name}: {errore}")
            continue
        db.add_photo(con, **dati)
        importate += 1
        didascalia = dati["caption"] or "(nessuna didascalia)"
        print(f"  {percorso.name}  ->  {didascalia}  "
              f"[{time.monotonic() - avvio:.1f}s]")

    durata = time.monotonic() - inizio
    print(f"\n{importate} foto importate in {durata:.0f}s. "
          f"Totale in archivio: {db.count_active(con)}.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
