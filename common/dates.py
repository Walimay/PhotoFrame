"""Nomi di giorni e mesi in italiano.

Scritti a mano invece di usare locale: su Raspberry Pi OS Lite la locale
it_IT spesso non e' generata, e setlocale fallirebbe silenziosamente
lasciando date in inglese.
"""

GIORNI = ["lunedi", "martedi", "mercoledi", "giovedi",
          "venerdi", "sabato", "domenica"]

GIORNI_ACCENTATI = ["lunedì", "martedì", "mercoledì", "giovedì",
                    "venerdì", "sabato", "domenica"]

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]


def long_date(dt):
    """mercoledì 9 settembre"""
    return f"{GIORNI_ACCENTATI[dt.weekday()]} {dt.day} {MESI[dt.month - 1]}"


def short_date(dt):
    """9 settembre 2026"""
    return f"{dt.day} {MESI[dt.month - 1]} {dt.year}"


def weekday_title(dt):
    """Mercoledì 9"""
    name = GIORNI_ACCENTATI[dt.weekday()]
    return f"{name[0].upper()}{name[1:]} {dt.day}"
