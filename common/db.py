"""Accesso a SQLite.

WAL piu' synchronous=FULL: il WAL permette letture durante le scritture
(interfaccia e web girano in processi separati), FULL fa in modo che una
transazione confermata sia davvero su scheda prima di tornare. E' la
combinazione che serve a sopravvivere a uno stacco di corrente.
"""
import sqlite3
from datetime import datetime

from .config import DB_PATH, DEFAULTS, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id            INTEGER PRIMARY KEY,
    filename      TEXT NOT NULL UNIQUE,
    original_name TEXT,
    caption       TEXT,
    taken_at      TEXT,
    added_at      TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    lum_topleft     REAL,
    lum_bottomright REAL
);

CREATE INDEX IF NOT EXISTS idx_photos_active ON photos(active, sort_order, id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS list_items (
    id         INTEGER PRIMARY KEY,
    list       TEXT NOT NULL,
    text       TEXT NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


def connect():
    ensure_dirs()
    con = sqlite3.connect(str(DB_PATH), timeout=15.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    return con


def init():
    """Crea schema e valori iniziali. Idempotente."""
    con = connect()
    with con:
        con.executescript(SCHEMA)
        for key, value in DEFAULTS.items():
            con.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (key, value),
            )
    return con


def get_setting(con, key, default=None):
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is not None:
        return row["value"]
    return DEFAULTS.get(key, default)


def get_int(con, key, default=0):
    try:
        return int(get_setting(con, key, default))
    except (TypeError, ValueError):
        return default


def get_bool(con, key, default=True):
    value = get_setting(con, key)
    if value is None:
        return default
    return str(value).strip() not in ("0", "", "false", "no")


def set_setting(con, key, value):
    with con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def active_photos(con):
    return con.execute(
        "SELECT * FROM photos WHERE active = 1 ORDER BY sort_order, id"
    ).fetchall()


def count_active(con):
    row = con.execute("SELECT COUNT(*) AS n FROM photos WHERE active = 1").fetchone()
    return row["n"]


def add_photo(con, filename, original_name=None, caption=None, taken_at=None,
              lum_topleft=None, lum_bottomright=None):
    with con:
        riga = con.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS prossimo FROM photos"
        ).fetchone()
        con.execute(
            "INSERT OR REPLACE INTO photos "
            "(filename, original_name, caption, taken_at, added_at, "
            " sort_order, lum_topleft, lum_bottomright) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (filename, original_name, caption, taken_at,
             datetime.now().isoformat(timespec="seconds"),
             riga["prossimo"], lum_topleft, lum_bottomright),
        )


def add_photo_dict(con, dati):
    add_photo(con, **dati)


def all_photos(con):
    """Tutte le foto, anche quelle nascoste: per la pagina di gestione."""
    return con.execute(
        "SELECT * FROM photos ORDER BY sort_order, id").fetchall()


def get_photo(con, photo_id):
    return con.execute(
        "SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()


def update_photo(con, photo_id, **campi):
    ammessi = {"caption", "active", "sort_order"}
    campi = {k: v for k, v in campi.items() if k in ammessi}
    if not campi:
        return
    assegnazioni = ", ".join(f"{k} = ?" for k in campi)
    with con:
        con.execute(f"UPDATE photos SET {assegnazioni} WHERE id = ?",
                    (*campi.values(), photo_id))


def delete_photo(con, photo_id):
    """Rimuove la riga e restituisce il nome del file da cancellare."""
    riga = get_photo(con, photo_id)
    if riga is None:
        return None
    with con:
        con.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    return riga["filename"]


def move_photo(con, photo_id, direzione):
    """Scambia la posizione con la foto precedente o successiva."""
    righe = all_photos(con)
    posizioni = [r["id"] for r in righe]
    if photo_id not in posizioni:
        return
    indice = posizioni.index(photo_id)
    vicino = indice + (-1 if direzione == "up" else 1)
    if not 0 <= vicino < len(righe):
        return
    with con:
        for nuovo_ordine, riga in enumerate(righe):
            con.execute("UPDATE photos SET sort_order = ? WHERE id = ?",
                        (nuovo_ordine, riga["id"]))
        con.execute("UPDATE photos SET sort_order = ? WHERE id = ?",
                    (vicino, photo_id))
        con.execute("UPDATE photos SET sort_order = ? WHERE id = ?",
                    (indice, righe[vicino]["id"]))
