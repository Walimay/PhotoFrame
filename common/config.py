"""Percorsi e costanti condivise fra interfaccia, web e script."""
import os
from pathlib import Path

# Codice: in produzione sola lettura. Dati: unica zona scrivibile.
BASE_DIR = Path(os.environ.get("CORNICE_BASE", "/opt/cornice"))
DATA_DIR = Path(os.environ.get("CORNICE_DATA", "/var/lib/cornice"))

PHOTO_DIR = DATA_DIR / "photos"
THUMB_DIR = DATA_DIR / "thumbs"
CACHE_DIR = DATA_DIR / "cache"
TMP_DIR = DATA_DIR / "uploads_tmp"
DB_PATH = DATA_DIR / "cornice.db"
FONT_DIR = BASE_DIR / "assets" / "fonts"

# Geometria del pannello finale. Forzata anche in cmdline.txt.
SCREEN_W = int(os.environ.get("CORNICE_W", "1024"))
SCREEN_H = int(os.environ.get("CORNICE_H", "768"))

# Valori iniziali della tabella settings: scritti solo se la chiave manca,
# cosi' una modifica da pagina web non viene sovrascritta al riavvio.
DEFAULTS = {
    "slide_seconds": "30",
    "fade_ms": "450",
    "splash_seconds": "8",
    "web_port": "8080",
    "show_clock": "1",
    "show_caption": "1",
    "photo_fit": "contain",      # contain = nessun ritaglio; cover = riempie
    "shuffle": "0",              # ordine casuale invece che per sort_order
    "pin_button_a": "24",        # pulsante principale: foto successiva
    "pin_button_b": "25",        # secondo pulsante: foto precedente
    "hold_reboot": "3",          # pulsante A tenuto: riavvio
    "hold_shutdown": "5",        # pulsante B tenuto: spegnimento
}


def ensure_dirs():
    for d in (DATA_DIR, PHOTO_DIR, THUMB_DIR, CACHE_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)
