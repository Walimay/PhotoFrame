#!/usr/bin/env python3
"""Ricalcola le didascalie delle foto gia' in archivio.

Serve dopo aver migliorato le regole di deduzione: ripassa i nomi
originali e aggiorna solo le didascalie che coincidono ancora con quelle
dedotte in automatico, lasciando intatte quelle scritte a mano.

    python3 scripts/fix_captions.py            mostra cosa cambierebbe
    python3 scripts/fix_captions.py --applica  esegue
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import db, images  # noqa: E402


def dedotta_in_passato(caption, nome_originale):
    """Vero se la didascalia sembra generata dal nome del file e non
    scritta a mano. Confronta con lo stem grezzo, che e' quello che le
    vecchie versioni usavano."""
    if not caption:
        return False
    stem = os.path.splitext(os.path.basename(nome_originale or ""))[0]
    return caption.strip() in (stem, stem.replace("_", " ").strip())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--applica", action="store_true",
                        help="scrive le modifiche invece di mostrarle")
    argomenti = parser.parse_args()

    con = db.init()
    cambiamenti = []

    for riga in db.all_photos(con):
        if not dedotta_in_passato(riga["caption"], riga["original_name"]):
            continue
        nuova = images.didascalia_da_nome(riga["original_name"] or "")
        if (nuova or None) != (riga["caption"] or None):
            cambiamenti.append((riga["id"], riga["caption"], nuova))

    if not cambiamenti:
        print("Nessuna didascalia da correggere.")
        return 0

    for photo_id, vecchia, nuova in cambiamenti:
        print(f"  {vecchia!r}  ->  {nuova!r}")
        if argomenti.applica:
            db.update_photo(con, photo_id, caption=nuova)

    if argomenti.applica:
        print(f"\n{len(cambiamenti)} didascalie aggiornate.")
    else:
        print(f"\n{len(cambiamenti)} da aggiornare. "
              f"Rilancia con --applica per eseguire.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
